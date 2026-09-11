"""A-only execution-mechanics research. No live writes or new signal filters."""
import inspect,json,hashlib
from datetime import datetime,timezone
import replay_mdd30 as a
import research_adaptive_exits_stage27 as e
H=3600000
OUT=a.RESULT_DIR/'a_stage47'

def runner(leverage,mode):
    src=inspect.getsource(e.a_replay)
    assert "limit=-.9*p['qty']*p['entry']/10" in src
    src=src.replace("limit=-.9*p['qty']*p['entry']/10",f"limit=-.9*p['qty']*p['entry']/{leverage}")
    original="abs(pos[s]['weight']-w)>1e-9"
    replacement={'exact':original,'direction':"pos[s]['weight']*w<=0",
       'tolerance25':"(pos[s]['weight']*w<=0 or abs(pos[s]['weight']-w)>abs(pos[s]['weight'])*.25)",
       'daily':"True"}[mode]
    assert original in src
    src=src.replace(original,replacement)
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
    times=[t for t in sorted(set.intersection(*(set(v) for v in series.values()))) if t>=first]
    cuts=[times[0]+(times[-1]+H-times[0])*k//3 for k in range(4)]
    results=[]
    for lev,mode in [(10,'exact'),(10,'direction'),(10,'tolerance25'),(10,'daily'),(5,'exact'),(3,'exact'),(3,'direction'),(3,'tolerance25')]:
        name=f'leverage{lev}_{mode}';fn=runner(lev,mode)
        run=lambda **kw:fn(series,maps,fs,times,'baseline',**kw)
        full=run();double=run(cost_mult=2)
        thirds=[e.compact(run(start=cuts[k],end=cuts[k+1])) for k in range(3)]
        item={'name':name,'full':e.compact(full),'double_cost':e.compact(double),'thirds':thirds}
        results.append(item)
        (OUT/f'{name}.json').write_text(json.dumps({'result':item,'ledger':full['ledger']},indent=2),encoding='utf8')
        print(name,json.dumps(item['full']),flush=True)
    report={'results':results,'range_ms':[times[0],times[-1]+H],'independent_validation':False,'live_changes':False,
      'limitations':['Same A tree signals and target exposure; no new filters; lower leverage means more hypothetical isolated margin, not lower notional',
      'No full exchange margin reservation/minimum quantity model; candidates are diagnostic, not execution-certified',
      '90% isolated-margin loss proxy; not actual BingX mark-price liquidation; fixed adverse funding assumption',
      'Five-year source window minus 720h indicator warmup; all thirds used for discovery',
      '10x exact comparator must match Stage46 baseline; old headline hourly-weight replay is not directly comparable'],
      'source_sha256':hashlib.sha256(inspect.getsource(e.a_replay).encode()).hexdigest()}
    old=json.loads((a.RESULT_DIR/'a_stage46/results.json').read_text())['results'][0]['full']
    assert abs(old['end_usd']-results[0]['full']['end_usd'])<1e-7
    (OUT/'results.json').write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':main()
