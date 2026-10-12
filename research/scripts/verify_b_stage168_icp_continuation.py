"""Read-only runtime validation; writes research verification evidence only."""
import hashlib
import json
from pathlib import Path
import research_b_stage168_icp_continuation as study

def main():
    study.self_checks()
    data=json.loads(study.OUT.read_text(encoding='utf-8'))
    standard=json.loads((study.ROOT/'strategy/plan_b_standard.json').read_text(encoding='utf-8'))
    assert data['research_only'] and not data['live_changes']
    assert len(data['rows'])==9
    base=data['rows'][0]
    assert abs(base['five']['return_pct']-standard['reference']['return_pct'])<1e-7
    assert abs(base['extended']['return_pct']-standard['reference']['extended_7y']['return_pct'])<1e-7
    comparisons=[]
    for row in data['rows'][1:]:
        results=[row[k] for k in ('five','extended','five_double_cost','extended_double_cost')]
        assert all(r['max_icp_hold_hours']<=row['max_hold_hours'] for r in results)
        assert all(abs(r['return_pct']-(r['end_usd']/100-1)*100)<1e-7 for r in results)
        assert all(r['fees_usd']>=0 and r['funding_usd']>=0 for r in results)
        stress_better=all(row[k]['return_pct']>base[k]['return_pct'] for k in ('five_double_cost','extended_double_cost'))
        risk_pass=all(r['hourly_adverse_bound_pct']>=-70 and r['liquidation_proxy_count']==0 for r in results)
        comparisons.append({'max_hold_hours':row['max_hold_hours'],
            'additional_continuation_margin_gross_guard':row['additional_continuation_margin_gross_guard'],
            'final_equity_improvement_pct':(row['five']['end_usd']/base['five']['end_usd']-1)*100,
            'double_cost_better_both':stress_better,'stress_risk_pass':risk_pass,
            'candidate_screen_pass':row['beat_baseline_both'] and row['mdd_no_worse_both'] and row['thirds_no_worse'] and stress_better and risk_pass})
    fingerprints={str(p.relative_to(study.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (Path(study.__file__),study.OUT,study.ROOT/'research/data_7y/ICPUSDT_1h.csv')}
    out={'research_only':True,'live_changes':False,'baseline_exact':True,'synthetic_accounting_and_control_checks':'passed',
         'comparisons':comparisons,'sha256':fingerprints,
         'not_yet_verified':['ICP perpetual minute execution on changed boundaries','BingX live fills','untouched future market']}
    target=study.OUT.with_name('VERIFICATION.json')
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
