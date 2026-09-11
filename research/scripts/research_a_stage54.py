"""Offline expanded A concentration/hysteresis grid, current contract constraints."""
import inspect,json,hashlib
import validate_a_stage52 as constrained
import a_gap_engine_stage53 as gap

def main():
    base=constrained.base
    configs=[('base',1,0)]+[(f'p{p}_t{t}',p,t) for p in (2,3,4,5,6,7,8,10) for t in (.5,1,2)]
    src=inspect.getsource(base.main)
    src=src.replace("[('base',1,0),('candidate',3,1)]",repr(configs))
    src=src.replace("('entry_only','hourly_flatten')","('buffer140',)")
    env=dict(base.__dict__);env['runner']=constrained.runner;env['OUT']=base.a.RESULT_DIR/'a_stage54'
    original=base.e.a_replay;base.e.a_replay=gap.a_replay
    try:exec(src,env);env['main']()
    finally:base.e.a_replay=original
    path=env['OUT']/'results.json';r=json.loads(path.read_text())
    r['grid']=configs;r['independent_validation']=False
    r['limitations']=['A signals and times unchanged; powers amplify existing exposure tier, NOT calibrated confidence probability',
      'New entries limited to gross1.4; hourly excess>1.6 attempts partial reduction to1.5; unsendable small exits skipped',
      'Current contract precision/minimum quantities/$2 minimum reused from Stage52, not historical specifications',
      'Binance spot bars, assumed adverse funding, 10x isolated-loss proxy; not a complete live replica',
      'Full grid selected and compared on the same data, no independent holdout; reference old headline uses different accounting']
    for item in r['results']:
        ledger=json.loads((env['OUT']/f"{item['name']}_{item['mode']}.json").read_text())['ledger']
        item['full']['partial_exit_fills']=sum(x['reason']=='partial_gross_reduction' for x in ledger)
        item['full']['position_exits']=sum(x['reason']!='partial_gross_reduction' for x in ledger)
    old=json.loads((base.a.RESULT_DIR/'a_stage53/results.json').read_text())
    for name,prev in [('base','base'),('p3_t1','candidate')]:
        actual=next(x for x in r['results'] if x['name']==name)['full']['end_usd']
        expected=next(x for x in old['results'] if x['name']==prev and x['mode']=='buffer140')['full']['end_usd']
        assert abs(actual-expected)<1e-7
    r['data_sha256']={s:hashlib.sha256((base.a.DATA_DIR/f'{s}USDT_1h.csv').read_bytes()).hexdigest() for s in base.a.CONFIG}
    path.write_text(json.dumps(r,indent=2),encoding='utf8')

if __name__=='__main__':main()
