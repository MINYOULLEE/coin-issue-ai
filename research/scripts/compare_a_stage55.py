"""Compare already-computed Stage54 candidates without rerunning/selectively changing costs."""
import json,hashlib
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[2]
    source=root/'research/results/a_stage54/results.json'
    r=json.loads(source.read_text());items=r['results'];base=next(x for x in items if x['name']=='base')
    for x in items:
        x['beats_base_every_third']=all(y['end_usd']>z['end_usd'] for y,z in zip(x['thirds'],base['thirds']))
        x['worst_third_relative_capital']=min(y['end_usd']/z['end_usd'] for y,z in zip(x['thirds'],base['thirds']))
        x['return_cost_drawdown_dominance']=x['full']['end_usd']>base['full']['end_usd'] and x['double_cost']['end_usd']>base['double_cost']['end_usd'] and all(x[k]['hourly_mark_mdd_pct']>=base[k]['hourly_mark_mdd_pct'] for k in ('full','double_cost')) and x['beats_base_every_third']
    picks={'same_conditions_base':base,
      'maximum_base_cost_return':max(items,key=lambda x:x['full']['end_usd']),
      'maximum_double_cost_return':max(items,key=lambda x:x['double_cost']['end_usd']),
      'best_worst_third_relative':max(items,key=lambda x:x['worst_third_relative_capital'])}
    dominant=[x for x in items if x['return_cost_drawdown_dominance']]
    picks['highest_return_without_worse_base_or_stress_drawdown']=max(dominant,key=lambda x:x['full']['end_usd']) if dominant else None
    folds=[]
    for k in range(3):
        winner=max(items,key=lambda x:x['thirds'][k]['end_usd'])
        folds.append({'selected_on_third':k+1,'name':winner['name'],'all_third_returns':[z['return_pct'] for z in winner['thirds']]})
    out={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'range_ms':r['range_ms'],'picks':picks,'dominant_candidates':[x['name'] for x in dominant],'third_winners':folds,
      'definitions':{'same_conditions_base':'Original A signals/tiers but research 1.4 admission cap; NOT unchanged production A or historical headline',
       'dominance':'Higher full and doubled-cost ending equity; no worse full and doubled-cost hourly MDD; higher equity in every discovery third'},
      'limitations':r['limitations']+['Optimization is conditional on chosen objective; same-data rankings are not independent validation; no candidate certified deployable'],
      'live_changes':False}
    dest=root/'research/results/a_stage55';dest.mkdir(exist_ok=True)
    (dest/'comparison.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    for name,x in picks.items():
        if x:print(name,json.dumps({'name':x['name'],'full':x['full'],'double_cost_return':x['double_cost']['return_pct'],'double_cost_mdd':x['double_cost']['hourly_mark_mdd_pct'],'thirds':[z['return_pct'] for z in x['thirds']]}))
    print('dominant',out['dominant_candidates']);print('third_winners',folds)

if __name__=='__main__':main()
