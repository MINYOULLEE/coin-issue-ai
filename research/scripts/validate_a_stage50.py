"""Offline actual-gross admission limit and hourly risk-exit sensitivity."""
import inspect,json
from datetime import datetime,timezone
import replay_mdd30 as a
import research_adaptive_exits_stage27 as e
H=3600000
OUT=a.RESULT_DIR/'a_stage50'

def runner(threshold,mode):
    src=inspect.getsource(e.a_replay)
    src=src.replace('    fee=.0005', '    clipped=0; risk_exits=0; max_open_gross=0.; max_after_entry=0.\n    fee=.0005')
    old="abs(pos[s]['weight']-w)>1e-9"
    if threshold:src=src.replace(old,f"(pos[s]['weight']*w<=0 or abs(pos[s]['weight']-w)>abs(pos[s]['weight'])*{threshold})")
    hook="        wants={s:mp[t] for s,mp in maps.items() if t in mp}"
    block="""        gross=sum(p['qty']*series[s][t]['o'] for s,p in pos.items())
        max_open_gross=max(max_open_gross,gross/max(equity,1e-9))
"""
    if mode=='hourly_flatten':
        block+="""        if gross>1.6*equity+1e-9:
            risk_exits+=1
            for s in list(pos):close(s,t,series[s][t]['o'],'hourly_gross_risk_exit')
"""
    src=src.replace(hook,block+hook)
    oldqty="                qty=max(0,equity)*abs(w)/entry;entryfee=qty*entry*fee;cash-=entryfee"
    assert oldqty in src
    src=src.replace(oldqty,"""                equity=cash+sum(p['qty']*p['side']*(series[k][t]['o']-p['entry']) for k,p in pos.items())
                gross=sum(p['qty']*series[k][t]['o'] for k,p in pos.items())
                wanted=max(0,equity)*abs(w)
                mark_per_notional=series[s][t]['o']/entry
                entry_equity_cost=fee+side*(1-mark_per_notional)
                available=max(0,1.6*equity-gross)/(mark_per_notional+1.6*entry_equity_cost)
                notional=min(wanted,available)
                if notional<wanted-1e-9:clipped+=1
                if notional<1e-9:continue
                qty=notional/entry;entryfee=qty*entry*fee;cash-=entryfee""")
    marker="        for s,p in list(pos.items()):"
    src=src.replace(marker,"""        eq_now=cash+sum(p['qty']*p['side']*(series[s][t]['o']-p['entry']) for s,p in pos.items())
        ratio=sum(p['qty']*series[s][t]['o'] for s,p in pos.items())/max(eq_now,1e-9)
        max_after_entry=max(max_after_entry,ratio)
        if mode_name=='hourly_flatten':assert ratio<=1.6+1e-8
"""+marker)
    src=src.replace("'start_usd':100", "'clipped_entries':clipped,'hourly_risk_exits':risk_exits,'max_open_gross':max_open_gross,'max_after_actions_gross':max_after_entry,'start_usd':100")
    env=dict(e.__dict__);env['mode_name']=mode;exec(src,env)
    return env['a_replay']

def main():
    OUT.mkdir(exist_ok=True)
    lo=int(datetime(2021,8,28,tzinfo=timezone.utc).timestamp()*1000);hi=int(datetime(2026,8,29,tzinfo=timezone.utc).timestamp()*1000)
    rows={s:[r for r in a.read_candles(a.DATA_DIR/f'{s}USDT_1h.csv') if lo<=r['t']<hi] for s in a.CONFIG}
    trees=a.load_trees();maps={};fs={}
    for s,rs in rows.items():maps[s]=a.targets(s,rs,trees[s],0);fs[s]=e.features(rs);print('prepared',s,flush=True)
    series={s:{r['t']:r for r in rs} for s,rs in rows.items()}
    first=max(min(m) for m in maps.values());times=[t for t in sorted(set.intersection(*(set(x) for x in series.values()))) if t>=first]
    cuts=[times[0]+(times[-1]+H-times[0])*k//3 for k in range(4)];results=[]
    for name,power,threshold in [('base',1,0),('candidate',3,1)]:
        mp={s:{} for s in maps}
        for t in sorted(set.intersection(*(set(m) for m in maps.values()))):
            ws={s:(1 if m[t]>0 else -1)*a.CONFIG[s][0]*(abs(m[t])/a.CONFIG[s][0])**power if m[t] else 0 for s,m in maps.items()}
            scale=min(1,1.6/sum(abs(w) for w in ws.values())) if any(ws.values()) else 1
            for s,w in ws.items():mp[s][t]=w*scale
        for mode in ('entry_only','hourly_flatten'):
            fn=runner(threshold,mode);full=fn(series,mp,fs,times,'baseline')
            item={'name':name,'mode':mode,'full':e.compact(full),'double_cost':e.compact(fn(series,mp,fs,times,'baseline',cost_mult=2)),
                  'thirds':[e.compact(fn(series,mp,fs,times,'baseline',start=cuts[k],end=cuts[k+1])) for k in range(3)]}
            results.append(item);print(name,mode,json.dumps(item['full']),flush=True)
            (OUT/f'{name}_{mode}.json').write_text(json.dumps({'summary':item,'ledger':full['ledger']},indent=2),encoding='utf8')
    (OUT/'results.json').write_text(json.dumps({'results':results,'live_changes':False,'range_ms':[times[0],times[-1]+H],
      'limitations':['Hourly risk exits flatten ALL positions and await next scheduled signal; diagnostic alternative, not current live policy',
      'Entry-only never adds notional beyond available gross budget, but cannot correct prior drift',
      'Hourly controls cannot guarantee intrabar cap; pre-action overshoot reported',
      'Sequential entry allocation in symbol order; quantity precision/minimum order/margin reservation not modeled',
      '10x isolated proxy and assumed funding retained; no independent holdout or BingX mark-price validation']},indent=2),encoding='utf8')

if __name__=='__main__':main()
