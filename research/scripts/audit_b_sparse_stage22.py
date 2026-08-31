"""Separate signal/fill/collateral accounting audit and cost/exit sensitivity. Offline."""
import json,inspect,math,hashlib
from datetime import datetime,timezone
import research_b_sparse_stage20 as p
s=p.s
H=3600000

def direct_signal(symbol, rows, i):
    bar=rows[i];span=max(bar['h']-bar['l'],1e-12)
    lower=(min(bar['o'],bar['c'])-bar['l'])/span
    upper=(bar['h']-max(bar['o'],bar['c']))/span
    average=sum(x['v'] for x in rows[i-48:i])/48
    if symbol=='ALGO':
        change=bar['c']/rows[i-3]['c']-1
        return 1 if change<-.08 and lower>.5 and bar['v']>average*1.5 else -1 if change>.08 and upper>.5 and bar['v']>average*1.5 else 0
    low=min(x['l'] for x in rows[i-24:i]);high=max(x['h'] for x in rows[i-24:i])
    excess,vol=(.015,1.5) if symbol=='ETH' else (.03,3.)
    return 1 if bar['l']<low*(1-excess) and bar['c']>low and lower>.4 and bar['v']>average*vol else -1 if bar['h']>high*(1+excess) and bar['c']<high and upper>.4 and bar['v']>average*vol else 0

def audit(series,entries,times,full):
    # Rebuild all fees, fixed-quantity cashflows and expected allocations from bars.
    # No replay() call or copied replay body in this accounting verifier.
    fills={(x['symbol'],x['entry_ts']):x for x in full['ledger']}
    cash=100.;active={};max_error=0.;count=0
    for t in times:
        equity=cash+sum(x['quantity']*x['side']*(series[sym][t]['o']-x['price']) for sym,x in active.items())
        reserved=sum(x['margin'] for x in active.values())
        free=max(0,min(cash-reserved,equity-reserved)-.05*max(equity,0))
        proposals=[x for x in entries.get(t,[]) if x['symbol'] not in active and x['exit_bar']<=times[-1]]
        wants=[max(0,equity)*1.15*x.get('weight_scale',1) for x in proposals]
        demands=[w*(1+x['lev']*(.001+.0000125*((x['exit_bar']-t)/H+1))) for w,x in zip(wants,proposals)]
        shrink=min(1,free/sum(demands)) if sum(demands)>0 else 0
        assert sum(demands)*shrink<=free+1e-7
        for x,w in zip(proposals,wants):
            key=(x['symbol'],t);margin=w*shrink
            if margin<1e-9:assert key not in fills;continue
            f=fills[key];price=series[x['symbol']][t]['o']*(1+x['side']*.0002)
            assert math.isclose(f['margin'],margin,rel_tol=1e-10,abs_tol=1e-7)
            assert math.isclose(f['quantity'],margin*x['lev']/price,rel_tol=1e-10)
            entry_fee=f['quantity']*price*.0005
            cash-=entry_fee
            active[x['symbol']]={**f,'side':x['side'],'price':price,'entry_fee':entry_fee,'funding':0}
        for sym,x in list(active.items()):
            funding=x['quantity']*series[sym][t]['o']*.0000125
            cash-=funding;x['funding']+=funding
            if t+H==x['exit_ts']:
                assert not x['proxy']
                close=series[sym][t]['c']*(1-x['side']*.0002)
                gross=x['quantity']*x['side']*(close-x['price']);exit_fee=x['quantity']*close*.0005
                net=gross-exit_fee-x['entry_fee']-x['funding']
                max_error=max(max_error,abs(net-x['net_pnl']))
                assert math.isclose(net,x['net_pnl'],abs_tol=1e-7,rel_tol=1e-10)
                cash+=gross-exit_fee;del active[sym];count+=1
    assert not active and count==full['trades']
    assert math.isclose(cash,full['end_usd'],abs_tol=1e-6)
    return dict(trades_checked=count,end_usd=cash,max_trade_pnl_error=max_error,collateral_checks_pass=True)

def main():
    saved=json.loads((p.OUT/'combinations.json').read_text());best=saved['results'][0]
    series,base,times=s.b.prepare();entries={t:[dict(x) for x in ps] for t,ps in base.items()};busy=set()
    for t,ps in base.items():
        for x in ps:busy.update(range(t,x['exit_bar']+H,H))
    direct_checked=0;hashes={}
    for ident in best['patterns']:
        sym,name=ident.split(':');path=s.core.DATA_DIR/f'{sym}USDT_1h.csv';rows=s.core.read_candles(path)
        hashes[sym]=hashlib.sha256(path.read_bytes()).hexdigest()
        for row in rows:row['symbol']=sym
        series[sym]={r['t']:r for r in rows};index={r['t']:i for i,r in enumerate(rows)}
        signals=dict(p.signals(rows))[name]
        # Scalar reimplementation checks EVERY eligible historical signal bar.
        for i in range(169,len(rows)-1):
            assert direct_signal(sym,rows,i)==signals[i];direct_checked+=1
        for x in s.opportunities(rows,signals,1,3,busy):
            t=x['entry_ts'];i=index[t]-1
            assert direct_signal(sym,rows,i)==x['side']
            # Gate independently checks only B signals confirmed by entry, never future B decisions.
            assert not any(bt<=t<z['exit_bar']+H for bt,ps in base.items() if bt<=t for z in ps)
            entries.setdefault(t,[]).append({**x,'weight_scale':best['target_fraction_per_signal']/1.15})
    src=inspect.getsource(s.b.replay).replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
    env=dict(s.b.__dict__);exec(src,env);run=env['replay']
    full=run(series,entries,times,1.15)
    assert abs(full['end_usd']-best['full']['end_usd'])<1e-6
    accounting=audit(series,entries,times,full)
    scenarios=[]
    for cost in (1,1.25,1.5,2):
        scenarios.append(dict(cost_multiplier=cost,baseline=s.compact(run(series,base,times,1.15,cost_mult=cost)),combination=s.compact(run(series,entries,times,1.15,cost_mult=cost))))
    # Exit at first next-hour OPEN rather than previous hourly CLOSE (same boundary).
    nxt=src.replace("close = bar['c']*(1-p['side']*slip)","close = series[s].get(t+3600000, bar)['o']*(1-p['side']*slip) if t+3600000 in series[s] else bar['c']*(1-p['side']*slip)")
    assert nxt!=src
    env2=dict(s.b.__dict__);exec(nxt,env2)
    boundary=dict(baseline=s.compact(env2['replay'](series,base,times,1.15)),combination=s.compact(env2['replay'](series,entries,times,1.15)))
    output=dict(generated_at=datetime.now(timezone.utc).isoformat(),direct_signal_bars_checked=direct_checked,data_sha256=hashes,accounting=accounting,cost_scenarios=scenarios,next_boundary_open_exit=boundary,independent_market_validation=False,notes=['Independent scalar signal/accounting implementations, NOT independent historical sample','No 5-minute data available for all three supplemental coins; intrahour entry delay untested','No live/deployment/state changes'])
    (p.OUT/'audit_stage22.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    print(json.dumps(output),flush=True)

if __name__=='__main__':main()
