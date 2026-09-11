"""Offline A sizing search and explicit historical-accounting bridge. No live writes."""
import inspect
import json
from datetime import datetime, timezone
import replay_mdd30 as a
import research_adaptive_exits_stage27 as e

H=3600000
OUT=a.RESULT_DIR/'a_stage48'

def accounting(fee,slip,fund,proxy):
    src=inspect.getsource(e.a_replay)
    old='fee=.0005*cost_mult;slip=.0002*cost_mult;fund=.0000125*cost_mult'
    assert old in src
    src=src.replace(old,f'fee={fee}*cost_mult;slip={slip}*cost_mult;fund={fund}*cost_mult')
    if not proxy:
        src=src.replace('if worst<=limit and (exit_net is None or exit_net<=limit):','if False:')
    env=dict(e.__dict__);exec(src,env)
    return env['a_replay']

def main():
    OUT.mkdir(exist_ok=True)
    lo=int(datetime(2021,8,28,tzinfo=timezone.utc).timestamp()*1000)
    hi=int(datetime(2026,8,29,tzinfo=timezone.utc).timestamp()*1000)
    rows={s:[r for r in a.read_candles(a.DATA_DIR/f'{s}USDT_1h.csv') if lo<=r['t']<hi] for s in a.CONFIG}
    trees=a.load_trees();maps={};fs={}
    for s,rs in rows.items():
        maps[s]=a.targets(s,rs,trees[s],0);fs[s]=e.features(rs)
        print('prepared',s,flush=True)
    series={s:{r['t']:r for r in rs} for s,rs in rows.items()}
    first=max(min(m) for m in maps.values())
    times=[t for t in sorted(set.intersection(*(set(x) for x in series.values()))) if t>=first]
    bridge=[]
    for label,fee,slip,fund,proxy in [('fee_only',.0004,0,0,False),('fees_slippage',.0005,.0002,0,False),('plus_funding',.0005,.0002,.0000125,False),('plus_proxy',.0005,.0002,.0000125,True)]:
        result=e.compact(accounting(fee,slip,fund,proxy)(series,maps,fs,times,'baseline'))
        bridge.append({'name':label,**result});print(label,result['return_pct'],flush=True)
    configs=[('baseline',None,None),('equal_active',.2,None),('flat_original',1,None)]
    configs += [(f'tier_power_{p}',None,p) for p in (0.25,.5,1.5,2,3)]
    configs += [(f'normalized_{v}',v,'normalize') for v in (.8,1.0,1.3,1.6)]
    results=[]
    for name,value,power in configs:
        mp={s:{} for s in maps}
        for t in sorted(set.intersection(*(set(m) for m in maps.values()))):
            wants={s:maps[s][t] for s in maps}
            if name=='equal_active':wants={s:(value if w>0 else -value if w<0 else 0) for s,w in wants.items()}
            elif name=='flat_original':wants={s:(a.CONFIG[s][0]*(1 if w>0 else -1) if w else 0) for s,w in wants.items()}
            elif power=='normalize':
                total=sum(abs(w) for w in wants.values())
                wants={s:w*value/total if total else 0 for s,w in wants.items()}
            elif power is not None:wants={s:(1 if w>0 else -1)*a.CONFIG[s][0]*(abs(w)/a.CONFIG[s][0])**power if w else 0 for s,w in wants.items()}
            total=sum(abs(w) for w in wants.values());scale=min(1,1.6/total) if total else 1
            for s,w in wants.items():mp[s][t]=w*scale
        full=e.a_replay(series,mp,fs,times,'baseline')
        item={'name':name,'full':e.compact(full),'historical_accounting':a.replay(rows,mp,.0004)}
        if name in ('baseline','tier_power_3'):
            cuts=[times[0]+(times[-1]+H-times[0])*k//3 for k in range(4)]
            item['double_cost']=e.compact(e.a_replay(series,mp,fs,times,'baseline',cost_mult=2))
            item['thirds']=[e.compact(e.a_replay(series,mp,fs,times,'baseline',start=cuts[k],end=cuts[k+1])) for k in range(3)]
        results.append(item)
        (OUT/f'{name}.json').write_text(json.dumps({'summary':item,'ledger':full['ledger']},indent=2),encoding='utf8')
        print(name,item['full']['return_pct'],flush=True)
    old=json.loads((a.RESULT_DIR/'a_stage47/results.json').read_text())['results'][0]['full']
    assert abs(results[0]['full']['end_usd']-old['end_usd'])<1e-7
    report={'range_ms':[times[0],times[-1]+H],'bridge':bridge,'results':results,'live_changes':False,'independent_validation':False,
      'limitations':['Same A direction/decision times/assets; sizing candidates only, cap 1.6; 10x proxy unchanged',
      'Historical hourly accounting is constant-weight with uncharged implicit hourly resizing, not fixed-quantity live execution',
      'Proxy-disabled bridge is attribution only, NOT a deployable candidate or removal of exchange liquidation risk',
      'Research costs/proxy are assumptions, not historical BingX futures funding and mark price',
      'All data used for discovery; no independent holdout; no live minimum-quantity/margin-reservation certification']}
    (OUT/'results.json').write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':main()
