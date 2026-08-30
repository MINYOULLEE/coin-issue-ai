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
        actual = hashlib.sha256((ROOT / path).read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8')).hexdigest()
        assert actual == expected, f'Frozen file changed: {path}'
    a = read('strategy/mdd30_standard.json')
    b = read('strategy/plan_b_standard.json')
    assert a['strategy_id'] == 'answer_mdd30'
    assert a['assets'] == ['BTC', 'ETH', 'XRP', 'TRX', 'SOL']
    assert a['max_gross_exposure'] == 1.6
    assert b == read('supabase/functions/_shared/plan_b_standard.json')
    assert b['strategy_id'] == 'b_reserved_margin_stage16'
    assert not b['live_ready'] and not b['enabled'] and b['test_mode']
    assert b['acceptance']['return_floor_exception']
    assert b['live_account']['starting_capital_usd'] == 150
    assert b['live_account']['public_trade_history'] is True
    assert b['reference']['start_usd'] == 100
    assert set(a['assets']).isdisjoint(b['symbols'])
    assert {s: (v['actual_hold_hours'], v['leverage']) for s,v in b['symbols'].items()} == {
        'AVAX': (13,3), 'ICP': (2,5), 'BCH': (4,3), 'DOGE': (13,5), 'UNI': (7,2)}
    assert read('strategy/plan_b_aggressive_candidate.json')['canonical'] == 'strategy/plan_b_standard.json'
    result = next(r['full'] for r in read(b['reference']['file'])['results']
                  if r['target_margin_fraction'] == 1.15)
    for key in ('start_usd','end_usd','return_pct','closed_trade_mdd_pct','hourly_mark_mdd_pct','trades','win_rate_pct'):
        assert abs(result[key] - b['reference'][key]) < 1e-8, key
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
    print('Local static audit only; no deployed-state or exchange verification.')

if __name__ == '__main__':
    main()
