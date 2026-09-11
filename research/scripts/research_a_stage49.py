"""Offline A conviction sizing x rebalance hysteresis search; no live changes."""
import inspect,json
from datetime import datetime,timezone
import replay_mdd30 as a
import research_adaptive_exits_stage27 as e
H=3600000
OUT=a.RESULT_DIR/'a_stage49'

def runner(threshold):
    src=inspect.getsource(e.a_replay)
    old="abs(pos[s]['weight']-w)>1e-9"
    assert old in src
    if threshold:
        src=src.replace(old,f"(pos[s]['weight']*w<=0 or abs(pos[s]['weight']-w)>abs(pos[s]['weight'])*{threshold})")
    env=dict(e.__dict__);exec(src,env)
    return env['a_replay']

def main():
    OUT.mkdir(exist_ok=True)
    lo=int(datetime(2021,8,28,tzinfo=timezone.utc).timestamp()*1000)
    hi=int(datetime(2026,8,29,tzinfo=timezone.utc).timestamp()*1000)
    rows={s:[r for r in a.read_candles(a.DATA_DIR/f'{s}USDT_1h.csv') if lo<=r['t']<hi] for s in a.CONFIG}
    trees=a.load_trees();maps={};fs={}
    for s,rs in rows.items():
        maps[s]=a.targets(s,rs,trees[s],0);fs[s]=e.features(rs);print('prepared',s,flush=True)
    series={s:{r['t']:r for r in rs} for s,rs in rows.items()}
    first=max(min(m) for m in maps.values())
    times=[t for t in sorted(set.intersection(*(set(x) for x in series.values()))) if t>=first]
    cuts=[times[0]+(times[-1]+H-times[0])*k//3 for k in range(4)]
    results=[]
    for power in (1,1.5,2,3):
        mp={s:{} for s in maps}
        for t in sorted(set.intersection(*(set(m) for m in maps.values()))):
            ws={s:(1 if m[t]>0 else -1)*a.CONFIG[s][0]*(abs(m[t])/a.CONFIG[s][0])**power if m[t] else 0 for s,m in maps.items()}
            scale=min(1,1.6/sum(abs(w) for w in ws.values())) if any(ws.values()) else 1
            for s,w in ws.items():mp[s][t]=w*scale
        for threshold in (0,.1,.25,.5,1):
            fn=runner(threshold);full=fn(series,mp,fs,times,'baseline')
            item={'power':power,'threshold':threshold,'full':e.compact(full),
                  'double_cost':e.compact(fn(series,mp,fs,times,'baseline',cost_mult=2))}
            results.append(item)
            (OUT/f'p{power}_t{threshold}.json').write_text(json.dumps({'summary':item,'ledger':full['ledger']},indent=2),encoding='utf8')
            print(power,threshold,full['return_pct'],item['double_cost']['return_pct'],flush=True)
    base=results[0]
    assert abs(base['full']['end_usd']-32443.63287894639)<1e-7
    leaders=sorted(results,key=lambda x:x['double_cost']['return_pct'],reverse=True)[:3]
    for item in [base]+[x for x in leaders if x is not base]:
        power=item['power'];mp={s:{} for s in maps}
        for t in sorted(set.intersection(*(set(m) for m in maps.values()))):
            ws={s:(1 if m[t]>0 else -1)*a.CONFIG[s][0]*(abs(m[t])/a.CONFIG[s][0])**power if m[t] else 0 for s,m in maps.items()}
            scale=min(1,1.6/sum(abs(w) for w in ws.values())) if any(ws.values()) else 1
            for s,w in ws.items():mp[s][t]=w*scale
        fn=runner(item['threshold'])
        item['thirds']=[e.compact(fn(series,mp,fs,times,'baseline',start=cuts[k],end=cuts[k+1])) for k in range(3)]
    report={'results':results,'range_ms':[times[0],times[-1]+H],'live_changes':False,'independent_validation':False,
      'limitations':['Same research engine and costs as Stage48; not a fully audited live clone',
      'Hysteresis keeps entry quantity: target cap 1.6 is not guaranteed actual gross exposure cap; cannot deploy without live exposure enforcement',
      '90% isolated margin loss proxy remains; not actual BingX liquidation/funding/mark data',
      'All data used for discovery; three thirds are not independent holdout',
      'No historic constant-weight headline supplied for hysteresis because it would ignore retained quantity semantics']}
    (OUT/'results.json').write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':main()
