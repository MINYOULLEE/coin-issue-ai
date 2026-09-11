from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np

import repair_coin_strategy as data
import replay_mdd30 as core

IDX = {name: i for i, name in enumerate(core.FEATURES)}


def raw_signal(x: np.ndarray, family: str, a: int, b: float, c: float) -> np.ndarray:
    if family == "rsi_revert":
        v = x[:, IDX[f"rsi_{a}"]]
        return np.where(v <= 50 - b, 1.0, np.where(v >= 50 + b, -1.0, 0.0))
    if family == "channel_revert":
        v = x[:, IDX[f"channel_{a}"]]
        return np.where(v <= b, 1.0, np.where(v >= 1 - b, -1.0, 0.0))
    if family == "shock_revert":
        ret = x[:, IDX[f"return_{a}h"]]
        volume = x[:, IDX["volume_change_24h"]]
        active = volume >= c
        return np.where(active & (ret <= -b), 1.0, np.where(active & (ret >= b), -1.0, 0.0))
    if family == "rsi_channel_revert":
        rsi = x[:, IDX[f"rsi_{a}"]]
        channel = x[:, IDX[f"channel_{int(c)}"]]
        return np.where((rsi <= 50 - b) & (channel <= .25), 1.0,
                        np.where((rsi >= 50 + b) & (channel >= .75), -1.0, 0.0))
    raise ValueError(family)


def simulate(times, returns, signal, exposure, fee=.0005):
    equity = 1.0; peak = 1.0; mdd = 0.0; previous = 0.0; changes = 0; entries = 0
    yearly = {}
    for stamp, ret, direction in zip(times, returns, signal):
        target = float(direction) * exposure
        equity *= max(0.0, 1 - abs(target - previous) * fee)
        changes += target != previous
        entries += target != 0 and target != previous
        equity *= max(0.0, 1 + target * ret)
        peak = max(peak, equity); mdd = min(mdd, equity / peak - 1)
        yearly[str(datetime.fromtimestamp(int(stamp) / 1000, timezone.utc).year)] = equity
        previous = target
    return {"multiple": equity, "return_pct": (equity - 1) * 100,
            "mdd_pct": mdd * 100, "changes": int(changes), "trades": int(entries),
            "year_end_multiple": yearly}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("symbol")
    symbol = parser.parse_args().symbol.upper()
    items = data.build_dataset(symbol)
    times = np.array([z[0] for z in items], dtype=np.int64)
    x = np.array([z[1] for z in items], dtype=float)
    realized = np.array([z[3] for z in items], dtype=float)
    split = int(len(x) * .70)
    definitions = []
    for a in (14, 72, 168):
        for b in (10, 15, 20, 25, 30, 35): definitions.append(("rsi_revert", a, b, 0.0))
    for a in (24, 72, 168, 336, 720):
        for b in (.05, .10, .15, .20, .25, .30): definitions.append(("channel_revert", a, b, 0.0))
    for a in (6, 12, 24, 72):
        for b in (.01, .02, .03, .04, .06, .08):
            for c in (-.5, 0.0, .25, .5, 1.0): definitions.append(("shock_revert", a, b, c))
    for a in (14, 72, 168):
        for b in (10, 15, 20, 25, 30):
            for c in (24, 72, 168, 336): definitions.append(("rsi_channel_revert", a, b, c))
    records = []
    for family, a, b, c in definitions:
        sig = raw_signal(x, family, a, b, c)
        for exposure in (.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0):
            train = simulate(times[:split], realized[:split], sig[:split], exposure)
            if train["changes"] < 20: continue
            score = np.log(max(train["multiple"], 1e-12)) + train["mdd_pct"] / 25
            if train["mdd_pct"] < -50: score -= 20
            records.append({"score": float(score), "family": family, "a": a, "b": b,
                            "c": c, "exposure": exposure, "train": train})
    records.sort(key=lambda z: z["score"], reverse=True)
    selected = records[0]
    sig = raw_signal(x, selected["family"], selected["a"], selected["b"], selected["c"])
    test = simulate(times[split:], realized[split:], sig[split:], selected["exposure"])
    full = simulate(times, realized, sig, selected["exposure"])
    gate = bool(full["return_pct"] > 1_000_000 and full["mdd_pct"] >= -50 and
                test["return_pct"] > 0 and test["mdd_pct"] >= -40)
    print(json.dumps({"symbol": symbol, "method": "selective_non_trend_reversion",
                      "selected_without_holdout": selected, "full": full, "holdout": test,
                      "start_usd": 100, "end_usd": 100 * full["multiple"],
                      "gate": gate}, ensure_ascii=False))


if __name__ == "__main__": main()
