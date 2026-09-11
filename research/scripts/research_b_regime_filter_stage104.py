"""Train a causal BTC-crash gate on the extension, then test it on the later five years."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97


ab = s101.ab
OUT = ab.OUT / "B_STAGE104_CAUSAL_REGIME_FILTER.json"


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def main():
    series, entries, times, _ = s101.delayed_inputs(1)
    btc_rows = ab.core.read_candles(ab.SPOT / "BTCUSDT_1h.csv")
    btc = {row["t"]: row for row in btc_rows}
    hour = s97.HOUR

    def btc_return(stamp, hours):
        recent, prior = btc.get(stamp-hour), btc.get(stamp-(hours+1)*hour)
        if not recent or not prior:
            return None
        return recent["c"]/prior["c"]-1

    variants = []
    scopes = [
        ("BCH_LINK_ALL", {"BCH", "LINK"}, 0),
        ("BCH_LINK_LONG", {"BCH", "LINK"}, 1),
        ("BCH_LINK_SHORT", {"BCH", "LINK"}, -1),
        ("BCH_LINK_UNI_ALL", {"BCH", "LINK", "UNI"}, 0),
    ]
    for label, symbols, required_side in scopes:
        for lookback in (24, 72):
            for threshold in (-.03, -.05, -.08, -.10):
                filtered = {}
                blocked = []
                for stamp, rows in entries.items():
                    kept = []
                    market_return = btc_return(stamp, lookback)
                    for row in rows:
                        applies = row["symbol"] in symbols and (required_side == 0 or row["side"] == required_side)
                        if applies and market_return is not None and market_return <= threshold:
                            blocked.append({"symbol": row["symbol"], "entry_ts": row["entry_ts"],
                                            "side": row["side"], "btc_return": market_return})
                        else:
                            kept.append(dict(row))
                    filtered[stamp] = kept
                features = {symbol: ab.b91.s90.s86.s58.old.prev.features(list(rows.values()))
                            for symbol, rows in series.items()}
                exits = s101.s99.learned_exits(series, filtered, features)
                fn = s97.runner(exits, 3.75, .25, 168)
                extension = fn(series, filtered, times, 1.15, start=min(times), end=s101.START_5Y)
                variants.append({"label": label, "lookback_hours": lookback,
                                 "threshold_pct": threshold*100, "blocked": len(blocked),
                                 "extension": compact(extension), "entries": filtered, "fn": fn})

    # Select only on the earlier extension, then evaluate the six leaders on the later five years.
    selected = sorted(variants, key=lambda row: row["extension"]["end_usd"], reverse=True)[:6]
    evaluated = []
    for row in selected:
        fn, filtered = row.pop("fn"), row.pop("entries")
        five = fn(series, filtered, times, 1.15, start=s101.START_5Y, end=s101.END)
        seven = fn(series, filtered, times, 1.15)
        item = {**row, "five_year_holdout": compact(five), "full_extension": compact(seven)}
        if five["return_pct"] >= 1_000_000 and seven["return_pct"] >= 1_000_000:
            item["double_cost_five_year"] = compact(
                fn(series, filtered, times, 1.15, cost_mult=2, start=s101.START_5Y, end=s101.END))
            item["double_cost_full"] = compact(fn(series, filtered, times, 1.15, cost_mult=2))
        evaluated.append(item)

    result = {
        "id": "B-STAGE104-CAUSAL-BTC-REGIME-FILTER",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "training_range": [datetime.fromtimestamp(min(times)/1000, timezone.utc).isoformat(),
                           datetime.fromtimestamp(s101.START_5Y/1000, timezone.utc).isoformat()],
        "holdout_range": [datetime.fromtimestamp(s101.START_5Y/1000, timezone.utc).isoformat(),
                          datetime.fromtimestamp(s101.END/1000, timezone.utc).isoformat()],
        "screen_count": len(variants), "evaluated": evaluated,
        "limitations": [
            "The new BTC gate is selected only on the early extension; the later five-year result is its chronological holdout.",
            "The underlying Stage93 signals and profit-lock family were previously developed on later history.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
