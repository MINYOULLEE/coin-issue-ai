"""Independent ledger checks; research files only, no trading interfaces."""
import json,hashlib
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/results/b_stage170_portfolio_continuation'
def main():
    result=json.loads((OUT/'RESULTS.json').read_text(encoding='utf-8'))
    books=json.loads((OUT/'PRIMARY_LEDGERS.json').read_text(encoding='utf-8'))
    checks={}
    for name,r in books.items():
        assert abs(100+sum(x['net_pnl'] for x in r['ledger'])-r['end_usd'])<r['end_usd']*1e-8
        assert abs((r['end_usd']/100-1)*100-r['return_pct'])<1e-7
        assert len(r['ledger'])==r['trades']
        active={};latest={};retained=0
        for x in r['actions']:
            s=x['symbol'];t=x['t']
            assert t>=latest.get('clock',0)
            latest['clock']=t
            if x['event']=='entry':
                assert s not in active and t-x['confirmed_at']<300000
                assert not active or all(p['group']==x['group'] for p in active.values())
                active[s]=x
            elif x['event']=='retain':
                assert s=='ICP' and s in active and x['quantity']==active[s]['quantity']
                retained+=1
            else:
                assert s in active
                del active[s]
        assert not active
        assert retained==r['counts'].get('retained_boundaries',0)
        assert all(x['exit_ts']>x['entry_ts'] and x['fees']>0 and x['funding']>0 for x in r['ledger'])
        assert all(x['exit_ts']-x['entry_ts']<=8*3600000 for x in r['ledger'] if x['symbol']=='ICP')
        checks[name]={'ledger_reconciles':True,'quantity_carried':True,'group_overlap':0,
                      'strict_ttl':True,'by_symbol':dict(Counter(x['symbol'] for x in r['ledger'])),
                      'retained_boundaries':retained}
    rows=result['scenarios']
    report={'status':'passed','research_only':True,'checks':checks,
            'scenarios':len(rows),'improved_scenarios':sum(x['return_better'] for x in rows),
            'no_worse_mdd_scenarios':sum(x['mdd_no_worse'] for x in rows),
            'frozen_improved_thirds':sum(x['return_better'] for x in result['thirds']),
            'results_sha256':hashlib.sha256((OUT/'RESULTS.json').read_bytes()).hexdigest(),
            'not_verified':['whole-B synchronized futures minutes','BingX mark-price liquidation tiers','unseen future returns']}
    standards=json.loads((ROOT/'strategy/plan_b_standard.json').read_text(encoding='utf-8'))
    sources=[ROOT/'strategy/plan_b_standard.json',ROOT/'strategy/plan_b_combination_standard.json',
             ROOT/'research/scripts/research_b_stage170_portfolio_continuation.py',
             ROOT/'research/results/b_stage169_icp_minutes/RESULTS.json']
    sources.extend(ROOT/'research/data_7y'/f'{s}USDT_1h.csv' for s in standards['symbols'])
    report['input_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    (OUT/'VERIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report))
if __name__=='__main__':main()
