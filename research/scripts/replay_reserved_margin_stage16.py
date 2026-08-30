"""Fixed-quantity, reserved-margin replay. Research only; no exchange requests.

Preserves the 677 preselected opportunities (selection-biased, NOT a holdout).
Research hold indices imply hold+1 actual bars. Hourly OHLC is not mark price.
"""
import json
from datetime import datetime, timezone
import numpy as np
import replay_mdd30 as core
import combine_novel_patterns as patterns

SYMBOLS = ('AVAX', 'ICP', 'BCH', 'DOGE', 'UNI')
FEE = .0005
SLIP = .0002
FUNDING_PER_HOUR = .0001 / 8


def prepare():
    saved = json.loads((core.RESULT_DIR / 'novel_pattern_search_stage10.json').read_text(encoding='utf-8'))
    selected = {x['best']['symbol']: x['best'] for x in saved['results'] if x['best']}
    series, entries = {}, {}
    for symbol in SYMBOLS:
        candidate = selected[symbol]
        rows = core.read_candles(core.DATA_DIR / f'{symbol}USDT_1h.csv')
        sig = patterns.matching_signal(rows, candidate)
        series[symbol] = {r['t']: r for r in rows}
        hold, lev = candidate['hold_hours'], candidate['leverage']
        nxt = 169
        for i in np.flatnonzero(sig[169:len(rows)-hold-1]) + 169:
            if i < nxt:
                continue
            nxt = int(i) + hold + 1
            stamp = rows[i+1]['t']
            entries.setdefault(stamp, []).append(dict(symbol=symbol, side=int(sig[i]),
                lev=lev, entry_ts=stamp, exit_bar=rows[i+1+hold]['t']))
    times = sorted(set.intersection(*(set(x) for x in series.values())))
    return series, entries, times


def replay(series, entries, times, weight, start_cash=100., cost_mult=1., start=None, end=None):
    balance = start_cash
    positions = {}
    ledger = []
    rejected = clipped = liq_proxies = 0
    peak_closed = peak_mark = start_cash
    mdd_closed = mdd_mark = worst_hour_bound = 0.
    max_reserved_ratio = max_gross = 0.
    fee_rate, slip = FEE*cost_mult, SLIP*cost_mult
    window = [t for t in times if (start is None or t >= start) and (end is None or t < end)]
    last = window[-1]
    for t in window:
        def unrealized(field):
            return sum(p['qty']*p['side']*(series[s][t][field]-p['entry']) for s,p in positions.items())
        equity_open = balance + unrealized('o')
        reserved = sum(p['margin'] for p in positions.values())
        proposals = [x for x in entries.get(t, []) if x['exit_bar'] <= last and x['symbol'] not in positions]
        # Allocate simultaneous signals proportionately; no arbitrary coin priority.
        available = max(0., min(balance-reserved, equity_open-reserved) - max(equity_open,0)*.05)
        target = max(equity_open, 0) * weight
        demands = [target*(1+x['lev']*(2*fee_rate+FUNDING_PER_HOUR*cost_mult*((x['exit_bar']-t)/3600000+1))) for x in proposals]
        shrink = min(1., available/sum(demands)) if sum(demands)>0 else 0.
        assert sum(demands)*shrink <= available+1e-7, 'new reservations exceed free margin'
        for x in proposals:
            if shrink <= 0 or target*shrink < 1e-9:
                rejected += 1
                continue
            margin = target*shrink
            clipped += shrink < .999999
            raw_open = series[x['symbol']][t]['o']
            entry = raw_open*(1+x['side']*slip)
            qty = margin*x['lev']/entry
            entry_fee = qty*entry*fee_rate
            balance -= entry_fee
            positions[x['symbol']] = dict(x, margin=margin, entry=entry, qty=qty,
                entry_fee=entry_fee, funding=0.)
        reserved = sum(p['margin'] for p in positions.values())
        max_reserved_ratio = max(max_reserved_ratio, reserved/max(equity_open,1e-12))
        max_gross = max(max_gross, sum(p['qty']*p['entry'] for p in positions.values())/max(equity_open,1e-12))
        # Conservative sum of individual hourly adverse extremes, not simultaneous ticks.
        bound = balance + sum(p['qty']*p['side']*(series[s][t]['l' if p['side']>0 else 'h']-p['entry']) for s,p in positions.items())
        worst_hour_bound = min(worst_hour_bound, bound/peak_mark-1)
        for s,p in list(positions.items()):
            bar = series[s][t]
            funding = p['qty']*bar['o']*FUNDING_PER_HOUR*cost_mult
            p['funding'] += funding
            balance -= funding
            worst = p['qty']*p['side']*(bar['l' if p['side']>0 else 'h']-p['entry'])
            # Explicit conservative assumption, not BingX's actual maintenance formula.
            proxy = worst-p['entry_fee']-p['funding'] <= -.9*p['margin']
            if proxy or t >= p['exit_bar']:
                if proxy:
                    close = p['entry']+p['side']*(-.9*p['margin']+p['entry_fee']+p['funding'])/p['qty']
                    liq_proxies += 1
                else:
                    close = bar['c']*(1-p['side']*slip)
                gross = p['qty']*p['side']*(close-p['entry'])
                exit_fee = p['qty']*close*fee_rate
                balance += gross-exit_fee
                net = gross-p['entry_fee']-exit_fee-p['funding']
                ledger.append(dict(symbol=s, entry_ts=p['entry_ts'], exit_ts=t+3600000,
                    margin=p['margin'], quantity=p['qty'], net_pnl=net, proxy=bool(proxy)))
                del positions[s]
                peak_closed = max(peak_closed,balance)
                mdd_closed = min(mdd_closed,balance/peak_closed-1)
        mark = balance+unrealized('c')
        peak_mark = max(peak_mark,mark)
        mdd_mark = min(mdd_mark,mark/peak_mark-1)
        if mark <= 0:
            raise RuntimeError('account insolvent in hourly replay')
    assert not positions, 'unclosed positions at end'
    return dict(start_usd=start_cash,end_usd=balance,return_pct=(balance/start_cash-1)*100,
        closed_trade_mdd_pct=mdd_closed*100,hourly_mark_mdd_pct=mdd_mark*100,
        hourly_adverse_bound_pct=worst_hour_bound*100,trades=len(ledger),
        win_rate_pct=100*sum(x['net_pnl']>0 for x in ledger)/len(ledger) if ledger else 0,
        margin_clipped=clipped,rejected=rejected,liquidation_proxy_count=liq_proxies,
        max_reserved_equity_ratio=max_reserved_ratio,max_gross_equity_ratio=max_gross,ledger=ledger)


def main():
    series,entries,times = prepare()
    cuts = [times[0]+int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
    output = dict(generated_at=datetime.now(timezone.utc).isoformat(),
        notes=['Frozen previously selected opportunities; no independent holdout',
               'Calendar thirds, fixed quantity, proportional simultaneous allocation, 5% cash buffer',
               'No actual contract minimums/tiered maintenance/mark-price data; not deployable validation'],
        ranges=[datetime.fromtimestamp(x/1000,timezone.utc).isoformat() for x in cuts],results=[])
    for weight in (.2,.5,.8,1.15):
        full = replay(series,entries,times,weight)
        stress = replay(series,entries,times,weight,cost_mult=2)
        segments = [replay(series,entries,times,weight,start=cuts[i],end=cuts[i+1]) for i in range(3)]
        item = dict(target_margin_fraction=weight, full=full, double_cost=stress, segments=segments)
        output['results'].append(item)
        print(json.dumps({k:v for k,v in dict(weight=weight,**full).items() if k!='ledger'}),flush=True)
    # Percentage results must be invariant to initial cash in this proportional model.
    other = replay(series,entries,times,1.15,start_cash=150.)
    assert abs(other['return_pct']-output['results'][-1]['full']['return_pct'])<1e-6
    output['start_150_check']={k:v for k,v in other.items() if k!='ledger'}
    path=core.RESULT_DIR/'reserved_margin_stage16.json'
    path.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print('Saved',path)

if __name__=='__main__': main()
