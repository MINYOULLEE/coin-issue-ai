"""Read-only adoption/source checks, distinct from live certification."""
import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
class AdoptionTests(unittest.TestCase):
    def test_adopted_copy_and_reference(self):
        s=read('strategy/plan_b_combination_standard.json')
        self.assertEqual(s,read('supabase/functions/_shared/plan_b_combination_standard.json'))
        source=read(s['reference']['file'])
        r=next(x for x in source['results'] if x['patterns']==s['reference']['selector']['patterns'] and x['target_fraction_per_signal']==.9)
        for key,value in r['full'].items():self.assertEqual(s['reference'][key],value,key)
        self.assertEqual(s['reference']['trades'],736)
        self.assertEqual(s['reference']['extra_trades'],80)
        self.assertFalse(s['live_ready'])
    def test_stage16_preserved_and_switch_not_reset(self):
        old=read('strategy/archive/plan_b_stage16_v1.json')
        self.assertEqual(old,read('strategy/plan_b_standard.json'))
        runtime=read('supabase/functions/_shared/plan_b_runtime.json')
        self.assertTrue(runtime['live_ready'])
        self.assertEqual(runtime['strategy_id'],old['strategy_id'])
        adopted=read('strategy/plan_b_combination_standard.json')
        for symbol,rule in old['symbols'].items():
            for key,value in rule.items():self.assertEqual(adopted['symbols'][symbol][key],value)
    def test_new_symbol_overlap_is_not_account_sharing(self):
        a=read('strategy/mdd30_standard.json');b=read('strategy/plan_b_combination_standard.json')
        self.assertEqual(set(a['assets'])&set(b['symbols']),{'ETH'})
        self.assertEqual(b['isolation']['api_key_env'],'PLAN_B_BINGX_API_KEY')
        self.assertEqual(b['live_account']['starting_capital_usd'],150)
        self.assertEqual(b['reference']['start_usd'],100)
if __name__=='__main__':unittest.main()
