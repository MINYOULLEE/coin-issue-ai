"""Offline A-only causal filter screening. Never imports an exchange client."""
import json
import hashlib
from datetime import datetime, timezone
import replay_mdd30 as a
import research_adaptive_exits_stage27 as engine

OUT = a.RESULT_DIR / 'a_stage46'
H = 3600000

def main():
    OUT.mkdir(exist_ok=True)
    rows = {s:a.read_candles(a.DATA_DIR/f'{s}USDT_1h.csv') for s in a.CONFIG}
    start = int(datetime(2021,8,28,tzinfo=timezone.utc).timestamp()*1000)
    end = int(datetime(2026,8,29,tzinfo=timezone.utc).timestamp()*1000)
    rows = {s:[r for r in rs if start <= r['t'] < end] for s,rs in rows.items()}
    trees = a.load_trees(); maps={}; facts={}; fs={}
    for s,rs in rows.items():
        maps[s]={};facts[s]={};fs[s]=engine.features(rs)
        weight,low,high,lo,mid,hi=a.CONFIG[s]
        for i in range(720,len(rs)):
            if (rs[i]['t']//H)%24:continue
            vector=a.feature_vector(rs[:i+1])
            side,confidence,node=a.evaluate(trees[s],vector)
            t=rs[i]['t']+H
            maps[s][t]=side*weight*(lo if confidence<low else mid if confidence<high else hi)
            facts[s][t]={'confidence':confidence,'r24':vector[4],'r72':vector[5],'atr':vector[26]}
        print('prepared',s,len(maps[s]),flush=True)
    series={s:{r['t']:r for r in rs} for s,rs in rows.items()}
    times=sorted(set.intersection(*(set(v) for v in series.values())))
    first=max(min(m) for m in maps.values());times=[t for t in times if t>=first]
    cuts=[times[0]+(times[-1]+H-times[0])*k//3 for k in range(4)]
    variants=[('baseline','baseline'),('atr_stop','atr_stop'),('horizon_stop','horizon_stop')]
    variants += [(f'confidence_{v}','baseline') for v in (.6,.7,.8,.9)]
    variants += [(v,'baseline') for v in ('align24','align72','contrary24','long_only','short_only','vol_reduce')]
    results=[]
    for name,exit_rule in variants:
        candidate={s:{} for s in maps}
        for s,mp in maps.items():
            for t,w in mp.items():
                f=facts[s][t];v=w
                if name.startswith('confidence_') and f['confidence']<float(name.split('_')[1]):v=0
                if name=='align24' and w*f['r24']<0:v=0
                if name=='align72' and w*f['r72']<0:v=0
                if name=='contrary24' and w*f['r24']>0:v=0
                if name=='long_only' and w<0:v=0
                if name=='short_only' and w>0:v=0
                if name=='vol_reduce':v*=min(1,.015/max(f['atr'],1e-9))
                candidate[s][t]=v
        run=lambda **kw:engine.a_replay(series,candidate,fs,times,exit_rule,**kw)
        full=run();stress=run(cost_mult=2)
        thirds=[engine.compact(run(start=cuts[k],end=cuts[k+1])) for k in range(3)]
        by_symbol={s:{'trades':sum(x['symbol']==s for x in full['ledger']),'net_pnl_usd':sum(x['net_pnl'] for x in full['ledger'] if x['symbol']==s)} for s in maps}
        result={'name':name,'full':engine.compact(full),'double_cost':engine.compact(stress),'thirds':thirds,'by_symbol':by_symbol}
        results.append(result)
        (OUT/f'{name}.json').write_text(json.dumps({'result':result,'ledger':full['ledger']},indent=2),encoding='utf8')
        print(name,json.dumps(engine.compact(full)),flush=True)
    output={'range':[datetime.fromtimestamp(times[0]/1000,timezone.utc).isoformat(),datetime.fromtimestamp((times[-1]+H)/1000,timezone.utc).isoformat()],
      'nominal_requested_range':['2021-08-28','2026-08-29'],'warmup_hours':720,'results':results,
      'third_winners':[max(results,key=lambda x:x['thirds'][k]['return_pct'])['name'] for k in range(3)],
      'limitations':['All thirds are discovery, not independent holdout; original tree training provenance is not independently certified',
      'Uses existing fixed-entry quantity research engine, not an audited live clone; hourly stops and liquidation proxy',
      'Spot OHLC proxy; assumed fee .05% per side, slip .02% per side, funding .00125% per hour; no actual funding series',
      '720-hour warmup reduces evaluated span below full five years; closed-trade MDD and hourly-mark MDD are distinct',
      'No production changes; no new strategy adoption'],
      'data_sha256':{s:hashlib.sha256((a.DATA_DIR/f'{s}USDT_1h.csv').read_bytes()).hexdigest() for s in maps}}
    (OUT/'results.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    print('saved',OUT,flush=True)

if __name__=='__main__':main()
