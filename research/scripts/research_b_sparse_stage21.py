"""Combine Stage20 rare supplements under shared available-collateral limits."""
import json, inspect, itertools
from datetime import datetime,timezone
import research_b_sparse_stage20 as p
s=p.s

def main():
    prior=json.loads((p.OUT/'results.json').read_text())
    chosen=[]
    for r in prior['results']:
        symbol=r['id'].split(':')[0]
        if r['research_filter_pass'] and symbol not in [x.split(':')[0] for x in chosen]:chosen.append(r['id'])
        if len(chosen)==3:break
    series,entries,times=s.b.prepare();busy=set()
    for t,ps in entries.items():
        for x in ps:busy.update(range(t,x['exit_bar']+3600000,3600000))
    src=inspect.getsource(s.b.replay).replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
    env=dict(s.b.__dict__);exec(src,env);run=env['replay']
    ops={}
    for ident in chosen:
        symbol,name=ident.split(':');rows=s.core.read_candles(s.core.DATA_DIR/f'{symbol}USDT_1h.csv')
        for row in rows:row['symbol']=symbol
        series[symbol]={r['t']:r for r in rows}
        sig=dict(p.signals(rows))[name];ops[ident]=s.opportunities(rows,sig,1,3,busy)
    cuts=[times[0]+int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
    results=[]
    for n in (2,3):
        for combo in itertools.combinations(chosen,n):
            for frac in (.5,.9):
                e={t:[dict(x) for x in ps] for t,ps in entries.items()}
                for ident in combo:
                    for x in ops[ident]:e.setdefault(x['entry_ts'],[]).append({**x,'weight_scale':frac/1.15})
                full=run(series,e,times,1.15);stress=run(series,e,times,1.15,cost_mult=2)
                a=[x for x in full['ledger'] if x['symbol'] in s.b.SYMBOLS];extra=[x for x in full['ledger'] if x['symbol'] not in s.b.SYMBOLS]
                overlap=sum(any(x['entry_ts']<y['exit_ts'] and x['exit_ts']>y['entry_ts'] for y in a) for x in extra)
                assert overlap==0
                r=dict(patterns=combo,target_fraction_per_signal=frac,full=s.compact(full),double_cost=s.compact(stress),extra_trades=len(extra),holding_overlap_trades=overlap,segments=[s.compact(run(series,e,times,1.15,start=cuts[k],end=cuts[k+1])) for k in range(3)])
                results.append(r);print('COMBO',combo,frac,full['return_pct'],stress['return_pct'],flush=True)
    results.sort(key=lambda x:x['full']['return_pct'],reverse=True)
    output=dict(id='B-SPARSE-STAGE21',generated_at=datetime.now(timezone.utc).isoformat(),selected=chosen,baseline=prior['baseline'],baseline_stress=prior['baseline_stress'],results=results,independent_validation=False,allocation='Each signal requests its target fraction; simultaneous signals clipped proportionately to shared free collateral, 5% equity buffer plus fees reserved. Not additive leverage or independent account returns.')
    (p.OUT/'combinations.json').write_text(json.dumps(output,indent=2),encoding='utf8')

if __name__=='__main__':main()
