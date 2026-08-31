"""Chronological simulated supplemental close-confirmation -> B entry handoff. No live writes."""
import json,urllib.request,urllib.parse,math,sys,bisect
from datetime import datetime,timezone
import research_b_sparse_stage20 as p
s=p.s;H=3600000;M=60000

def prepare():
    series,base,times=s.b.prepare();entries={t:[{**x,'group':'B'} for x in ps] for t,ps in base.items()};busy=set();minutes={}
    for t,ps in base.items():
        for x in ps:busy.update(range(t,x['exit_bar']+H,H))
    best=json.loads((p.OUT/'combinations.json').read_text())['results'][0]
    for ident in best['patterns']:
        sym,name=ident.split(':');rows=s.core.read_candles(s.core.DATA_DIR/f'{sym}USDT_1h.csv')
        for row in rows:row['symbol']=sym
        series[sym]={r['t']:r for r in rows}
        for x in s.opportunities(rows,dict(p.signals(rows))[name],1,3,busy):
            if not times[0]<=x['entry_ts']<=times[-1]:continue
            entries.setdefault(x['entry_ts'],[]).append({**x,'group':'supplement'})
            path=p.OUT/'minute_windows'/f"{sym}_{x['entry_ts']}.json"
            for r in json.loads(path.read_text()):minutes[(sym,int(r[0]))]=float(r[1])
    collisions=json.loads((p.OUT/'delay_stage24.json').read_text())['exit_diagnostics'][1]['collisions']
    for sym,t in sorted({(x['b_symbol'],x['b_entry']) for x in collisions}):
        path=p.OUT/'minute_windows'/f'{sym}_{t}_handoff.json'
        if not path.exists():
            if '--fetch' not in sys.argv:raise RuntimeError('Run --fetch to retrieve public B collision minute windows')
            q=urllib.parse.urlencode(dict(symbol=sym+'USDT',interval='1m',startTime=t,endTime=t+15*M,limit=20))
            with urllib.request.urlopen('https://api.binance.com/api/v3/klines?'+q,timeout=15) as response:rows=json.load(response)
            assert len(rows)==16 and all(int(r[0])==t+i*M for i,r in enumerate(rows))
            path.write_text(json.dumps(rows),encoding='utf8')
        for r in json.loads(path.read_text()):minutes[(sym,int(r[0]))]=float(r[1])
    return series,base,entries,times,minutes,best

def simulate(series,entries,times,minutes,delay,confirm_delay=0):
    cash=100.;positions={};pending=[];locks=[];ledger=[];missed=[];waited=[];peak=100.;mdd=0.;peak_closed=100.;closed_mdd=0.;rejected=0
    events=set(times+[times[-1]+H])
    for t,ps in entries.items():
        for x in ps:
            if x['group']=='supplement':events.update([t+H+delay*M,t+H+(delay+confirm_delay)*M,t+H+5*M])
    def price(sym,t,mark=False):
        if t%H==0:
            # Match the frozen simulator's previous available common hourly sample at data gaps.
            bar_t=times[max(0,bisect.bisect_left(times,t)-1)] if mark else t
            if bar_t in series[sym]:return series[sym][bar_t]['c' if mark else 'o']
        if (sym,t) in minutes:return minutes[(sym,t)]
        raise RuntimeError(f'missing price {sym} {t}')
    for t in sorted(events):
        if t<times[0] or t>times[-1]+H+15*M:continue
        # Confirmed closes happen before releasing reservations and retrying waiting B entries.
        for sym,x in list(positions.items()):
            if t!=x['close_time']:continue
            raw=price(sym,t,mark=x['group']=='B' or delay==0)
            close=raw*(1-x['side']*.0002)
            extra_funding=x['qty']*raw*.0000125*delay/60 if x['group']=='supplement' else 0
            cash-=extra_funding;x['funding']+=extra_funding
            gross=x['qty']*x['side']*(close-x['entry']);fee=x['qty']*close*.0005;cash+=gross-fee
            ledger.append(dict(symbol=sym,group=x['group'],entry_ts=x['actual_entry'],signal_ts=x['entry_ts'],exit_ts=t,net_pnl=gross-fee-x['entry_fee']-x['funding']))
            peak_closed=max(peak_closed,cash);closed_mdd=min(closed_mdd,cash/peak_closed-1)
            if x['group']=='supplement' and confirm_delay:locks.append(dict(until=t+confirm_delay*M,margin=x['margin']))
            del positions[sym]
        locks=[x for x in locks if x['until']>t]
        if t%H==0:
            equity=cash+sum(x['qty']*x['side']*(price(sym,t,True)-x['entry']) for sym,x in positions.items())
            peak=max(peak,equity);mdd=min(mdd,equity/peak-1)
        # Only signals already observed at this event may become pending.
        for x in entries.get(t,[]):
            if x['exit_bar']>times[-1] or x['symbol'] in positions:continue
            pending.append(x)
        ready=[];keep=[]
        for x in pending:
            if t-x['entry_ts']>=5*M:
                missed.append(dict(symbol=x['symbol'],signal_ts=x['entry_ts'],reason='expired_waiting_confirmation'));continue
            if x['group']=='B' and (locks or any(v['group']=='supplement' for v in positions.values())):keep.append(x);continue
            if x['group']=='supplement' and (locks or any(v['group']=='B' for v in positions.values()) or any(v['group']=='B' for v in ready)):
                keep.append(x);continue
            if x['group']=='B' and t>x['entry_ts']:
                reference=series[x['symbol']][x['entry_ts']-H]['c']
                adverse=(price(x['symbol'],t)/reference-1)*100*x['side']
                if adverse>.35:
                    missed.append(dict(symbol=x['symbol'],signal_ts=x['entry_ts'],reason='adverse_price_over_0.35_pct'));continue
            ready.append(x)
        pending=keep
        if ready:
            # At delayed handoff there must be no supplement position or reserved lock.
            if any(x['group']=='B' for x in ready):assert not locks and not any(x['group']=='supplement' for x in positions.values())
            equity=cash+sum(x['qty']*x['side']*(price(sym,t)-x['entry']) for sym,x in positions.items())
            reserved=sum(x['margin'] for x in positions.values())+sum(x['margin'] for x in locks)
            available=max(0,min(cash-reserved,equity-reserved)-.05*max(equity,0))
            wants=[max(equity,0)*(1.15 if x['group']=='B' else .9) for x in ready]
            demands=[w*(1+x['lev']*(.001+.0000125*((x['exit_bar']-x['entry_ts'])/H+1))) for w,x in zip(wants,ready)]
            shrink=min(1,available/sum(demands)) if sum(demands)>0 else 0
            assert sum(demands)*shrink<=available+1e-7
            for x,w in zip(ready,wants):
                margin=w*shrink
                if margin<1e-9:rejected+=1;continue
                sym=x['symbol'];raw=price(sym,t);entry=raw*(1+x['side']*.0002);qty=margin*x['lev']/entry;fee=qty*entry*.0005;cash-=fee
                positions[sym]={**x,'margin':margin,'entry':entry,'qty':qty,'entry_fee':fee,'funding':0.,'actual_entry':t,'close_time':x['exit_bar']+H+(delay*M if x['group']=='supplement' else 0)}
                if t>x['entry_ts']:waited.append(dict(symbol=sym,wait_minutes=(t-x['entry_ts'])/M))
                # Original first-hour funding charge retained even for late B entries.
                if t%H!=0:
                    funding=qty*raw*.0000125;cash-=funding;positions[sym]['funding']+=funding
        if t%H==0 and t<=times[-1]:
            for sym,x in positions.items():
                if x['group']=='supplement' and t>=x['entry_ts']+H:continue
                funding=x['qty']*price(sym,t)*.0000125;cash-=funding;x['funding']+=funding
        assert not (any(x['group']=='B' for x in positions.values()) and any(x['group']=='supplement' for x in positions.values())), 'B/supplement holdings overlap'
    assert not positions and not locks and not pending
    return dict(start_usd=100,end_usd=cash,return_pct=(cash/100-1)*100,trades=len(ledger),win_rate_pct=100*sum(x['net_pnl']>0 for x in ledger)/len(ledger),hourly_mark_mdd_pct=mdd*100,closed_trade_mdd_pct=closed_mdd*100,missed=missed,waited=waited,rejected=rejected,holding_overlap_count=0,ledger=ledger)

def main():
    series,base,entries,times,minutes,best=prepare()
    check=simulate(series,entries,times,minutes,0)
    assert math.isclose(check['end_usd'],best['full']['end_usd'],rel_tol=1e-10), (check['end_usd'],best['full']['end_usd'])
    assert abs(check['hourly_mark_mdd_pct']-best['full']['hourly_mark_mdd_pct'])<1e-7
    results=[]
    for delay,confirm in [(0,0),(1,0),(3,0),(5,0),(10,0),(1,4)]:
        r=simulate(series,entries,times,minutes,delay,confirm)
        results.append(dict(close_fill_delay_minutes=delay,confirmation_extra_minutes=confirm,**{k:v for k,v in r.items() if k!='ledger'}));print(json.dumps(results[-1]),flush=True)
    output=dict(generated_at=datetime.now(timezone.utc).isoformat(),results=results,baseline=best['full'],notes=['Chronological simulated fill and confirmation gate, not deployed execution code','B waits strictly less than five minutes from its original signal; then expires','Supplement signals remain frozen; do not invent replacements when B is missed','All supplementary closes delayed in each scenario, not just collision days','Hourly mark MDD only; no full intraminute liquidation/maintenance simulation','Fixed fee .05%, slip .02%, hourly funding assumption; Binance spot prices, not BingX fills'])
    (p.OUT/'handoff_stage25.json').write_text(json.dumps(output,indent=2),encoding='utf8')

if __name__=='__main__':main()
