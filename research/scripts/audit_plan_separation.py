"""Read-only checks for the user-adopted A/B baseline; not live certification."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))

def main():
    manifest = read('strategy/plan_freeze_manifest.json')
    for path, expected in manifest['sha256'].items():
        actual = hashlib.sha256((ROOT / path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        assert actual == expected, f'Frozen file changed: {path} ({actual} != {expected})'
    a = read('strategy/mdd30_standard.json')
    b = read('strategy/plan_b_standard.json')
    assert a['strategy_id'] == 'answer_mdd30'
    assert a['assets'] == ['BTC', 'ETH', 'XRP', 'TRX', 'SOL']
    assert a['standard_version'] == 'mdd30_drawdown_guard_stage75_v1'
    assert a['exchange_leverage'] == 3
    assert a['base_exposure_scale'] == 1.4
    assert a['max_gross_exposure'] == 2.24
    assert a['emergency_stop_loss_pct'] == 15
    assert a['drawdown_guard'] == {
        'equity_peak_basis': 'actual_bingx_equity',
        'activation_drawdown_pct': 35,
        'active_exposure_scale': 1.05,
        'recovery_drawdown_pct': 17.5,
        'normal_exposure_scale': 1.4,
        'evaluation': 'before_next_daily_rebalance',
        'state_persistence_required': True,
    }
    assert b == read('supabase/functions/_shared/plan_b_standard.json')
    assert b['strategy_id'] == 'b_profit_lock_stage66'
    assert b == read('strategy/plan_b_combination_standard.json')
    assert b == read('supabase/functions/_shared/plan_b_combination_standard.json')
    assert not b['acceptance']['live_validation']
    runtime = read('supabase/functions/_shared/plan_b_runtime.json')
    assert runtime['strategy_id'] == b['strategy_id']
    assert runtime['live_ready'] is True, 'Preserve owner-enabled B runtime; never restore old OFF snapshot'
    assert b['acceptance']['user_adopted_on'] == '2026-09-07'
    assert b['live_account']['starting_capital_usd'] == 650
    assert b['live_account']['public_trade_history'] is True
    assert b['reference']['start_usd'] == 100
    assert set(a['assets']).intersection(b['symbols']) == {'ETH'}
    assert b['isolation']['api_key_env'] == 'PLAN_B_BINGX_API_KEY'
    assert b['isolation']['secret_key_env'] == 'PLAN_B_BINGX_SECRET_KEY'
    assert b['isolation']['client_order_prefix'] == 'pb66'
    assert {s: (v['actual_hold_hours'], v['leverage']) for s,v in b['symbols'].items()} == {
        'AVAX': (13,3), 'ICP': (2,5), 'BCH': (4,3), 'DOGE': (13,5), 'UNI': (7,2),
        'ALGO': (1,3), 'ETH': (1,3), 'VET': (1,3), 'LINK': (1,3), 'DOT': (1,3),
        'LTC': (1,3), 'BNB': (1,3)}
    old = read('strategy/archive/plan_b_stage16_v1.json')
    for symbol,rule in old['symbols'].items():
        for key,value in rule.items(): assert b['symbols'][symbol][key] == value
    for symbol in ('ALGO','ETH','VET','LINK','LTC'):
        assert b['symbols'][symbol]['opportunity_cooldown_hours'] == 2
        assert b['symbols'][symbol]['target_margin_fraction'] == 1.15
    for symbol,fraction in {'DOT': .075, 'BNB': .125}.items():
        assert b['symbols'][symbol]['opportunity_cooldown_hours'] == 2
        assert b['symbols'][symbol]['target_margin_fraction'] == fraction
    assert read('strategy/plan_b_aggressive_candidate.json')['canonical'] == 'strategy/plan_b_standard.json'
    evidence = read(b['reference']['file'])
    result = next(r for r in evidence['results'] if set(r['symbols']) == {'ICP','BCH','UNI'})
    assert result['strict_pass'] and result['changed_exits'] == 26
    result = result['full']
    for key in ('start_usd','end_usd','return_pct','closed_trade_mdd_pct','hourly_mark_mdd_pct','trades','win_rate_pct'):
        assert abs(result[key] - b['reference'][key]) < 1e-8, key
    fills = read('research/results/profit_lock_fills_stage65/RESULTS.json')
    assert fills['orders_submitted'] == 0 and fills['complete_windows'] == 26 and fills['errors'] == []
    assert all(item['mean_improvement_pp'] > 0 for item in fills['summaries'])
    for name in ('plan-b-strategy', 'plan-b-account-read', 'plan-b-executor'):
        source = (ROOT / f'supabase/functions/{name}/index.ts').read_text(encoding='utf-8')
        for forbidden in ('BINGX_API_KEY', 'BINGX_SECRET_KEY', 'trade_signals',
                          'real_trading_state', 'real_trades', 'novel_multi_pattern_aggressive_stage14', '5.75', '20.7'):
            assert all(quote+forbidden+quote not in source for quote in ('"', "'")), f'{name}: {forbidden}'
    account = (ROOT / 'supabase/functions/plan-b-account-read/index.ts').read_text(encoding='utf-8')
    assert '!STANDARD.live_ready' in account
    migration = (ROOT / 'supabase/migrations/20260830122300_adopt_plan_b_aggressive.sql').read_text(encoding='utf-8')
    assert 'cron.schedule(' not in migration
    print(f'PASS: {len(manifest["sha256"])} frozen files; A/B IDs, settings, references and local activation guard')
    print('Research snapshot and shared runtime entry lock checked; remote source parity must also be verified.')

if __name__ == '__main__':
    main()
