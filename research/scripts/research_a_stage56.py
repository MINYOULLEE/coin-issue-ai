"""Offline A directional allocation sensitivity; fixed chosen concentration baseline."""
import inspect,json
import validate_a_stage52 as constrained
import a_gap_engine_stage53 as gap

def main():
    base=constrained.base
    configs=[('base',1,0,1,1),('p7_reference',7,.5,1,1)]
    configs += [(f'short_{s}',7,.5,1,s) for s in (.25,.5,.75,1.25,1.5,2)]
    configs += [(f'long_{l}',7,.5,l,1) for l in (.5,.75,1.25,1.5)]
    src=inspect.getsource(base.main)
    src=src.replace("for name,power,threshold in [('base',1,0),('candidate',3,1)]:",'for name,power,threshold,long_scale,short_scale in '+repr(configs)+':')
    src=src.replace("            scale=min(1,1.6/sum(abs(w) for w in ws.values()))", "            ws={s:w*(long_scale if w>0 else short_scale) for s,w in ws.items()}\n            scale=min(1,1.6/sum(abs(w) for w in ws.values()))")
    src=src.replace("('entry_only','hourly_flatten')","('buffer140',)")
    env=dict(base.__dict__);env['runner']=constrained.runner;env['OUT']=base.a.RESULT_DIR/'a_stage56'
    original=base.e.a_replay;base.e.a_replay=gap.a_replay
    try:exec(src,env);env['main']()
    finally:base.e.a_replay=original
    path=env['OUT']/'results.json';r=json.loads(path.read_text())
    r['grid']=configs;r['independent_validation']=False
    r['limitations']=['Same A directional signals/time/5 assets; p7 threshold0.5 from prior full-data search',
      'Long/short multipliers modify requested allocation before target normalization and actual1.4 admission clipping, NOT guaranteed exposure multipliers',
      'Current contract grid applied historically; assumed funding,10x proxy and spot OHLC; not actual futures/live performance',
      'All thirds used for discovery; nested optimization creates selection bias; no untouched holdout',
      '1.6 hourly excess reduction can fail minimum orders and intrabar cap is not guaranteed']
    for item in r['results']:
        ledger=json.loads((env['OUT']/f"{item['name']}_{item['mode']}.json").read_text())['ledger']
        item['full']['partial_exit_fills']=sum(x['reason']=='partial_gross_reduction' for x in ledger)
        item['full']['position_exits']=sum(x['reason']!='partial_gross_reduction' for x in ledger)
    old=json.loads((base.a.RESULT_DIR/'a_stage54/results.json').read_text())
    for name,prev in [('base','base'),('p7_reference','p7_t0.5')]:
        assert abs(next(x for x in r['results'] if x['name']==name)['full']['end_usd']-next(x for x in old['results'] if x['name']==prev)['full']['end_usd'])<1e-7
    path.write_text(json.dumps(r,indent=2),encoding='utf8')

if __name__=='__main__':main()
