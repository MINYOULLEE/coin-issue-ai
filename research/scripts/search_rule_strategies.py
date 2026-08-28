from __future__ import annotations

import argparse
import itertools
import json
from datetime import datetime, timezone

import numpy as np

import replay_mdd30 as core
import repair_coin_strategy as repair

IDX = {name: i for i, name in enumerate(core.FEATURES)}


def signal_for(x: np.ndarray, family: str, a: float, b: float) -> np.ndarray:
    if family == "momentum":
        value = x[:, IDX[f"return_{int(a)}h"]]
        return np.where(value > b, 1., np.where(value < -b, -1., 0.))
    if family == "ema":
        value = x[:, IDX[str(a)]]
        return np.where(value > b, 1., np.where(value < -b, -1., 0.))
    if family == "channel":
        value = x[:, IDX[f"channel_{int(a)}"]]
        return np.where(value > b, 1., np.where(value < 1 - b, -1., 0.))
    if family == "rsi_trend":
        value = x[:, IDX[f"rsi_{int(a)}"]]
        return np.where(value > 50 + b, 1., np.where(value < 50 - b, -1., 0.))
    if family == "rsi_revert":
        value = x[:, IDX[f"rsi_{int(a)}"]]
        return np.where(value < 50 - b, 1., np.where(value > 50 + b, -1., 0.))
    raise ValueError(family)


def simulate(times, realized, raw_signal, exposure, side, vol_target, guard, fee=.0005):
    signal = raw_signal.copy()
    if side == "long": signal[signal < 0] = 0
    if side == "short": signal[signal > 0] = 0
    equity = 1.; peak = 1.; mdd = 0.; previous = 0.; changes = 0; guarded = False
    year_start = {}; year_end = {}
    vol = np.ones(len(signal))
    if vol_target:
        # vol_72 is annualized in the deployed feature set.
        vol = np.clip(vol_target / np.maximum(CURRENT_X[:, IDX["vol_72"]], .05), .25, 1.5)
    for i, (stamp, ret, direction) in enumerate(zip(times, realized, signal)):
        year = str(datetime.fromtimestamp(stamp / 1000, timezone.utc).year)
        year_start.setdefault(year, equity)
        drawdown = equity / peak - 1
        if guard and drawdown <= -.20: guarded = True
        if guard and guarded and drawdown >= -.05: guarded = False
        target = direction * exposure * vol[i] * (.5 if guarded else 1.)
        equity *= max(0., 1 - abs(target - previous) * fee)
        changes += target != previous
        equity *= max(0., 1 + target * ret)
        peak = max(peak, equity); mdd = min(mdd, equity / peak - 1)
        year_end[year] = equity; previous = target
    yearly = {year: float((year_end[year] / year_start[year] - 1) * 100) if year_start[year] > 0 else -100.0 for year in year_end}
    return {"multiple": float(equity), "return_pct": float((equity - 1) * 100), "mdd_pct": float(mdd * 100), "changes": int(changes), "yearly_return_pct": yearly, "positive_years": int(sum(v > 0 for v in yearly.values())), "years": int(len(yearly))}


CURRENT_X: np.ndarray


def main():
    global CURRENT_X
    parser = argparse.ArgumentParser(); parser.add_argument("symbol")
    symbol = parser.parse_args().symbol.upper()
    items = repair.build_dataset(symbol)
    times = np.array([z[0] for z in items], dtype=np.int64)
    CURRENT_X = np.array([z[1] for z in items], dtype=float)
    realized = np.array([z[3] for z in items], dtype=float)
    split = int(len(times) * .70)
    definitions = []
    for lookback, threshold in itertools.product((24, 72, 168, 336, 720), (.0, .005, .01, .02, .04)):
        definitions.append(("momentum", lookback, threshold))
    for feature in ("ema_gap_12_72", "ema_gap_24_168", "ema_gap_72_336", "ema_gap_168_720"):
        for threshold in (0., .0025, .005, .01, .02): definitions.append(("ema", feature, threshold))
    for lookback, threshold in itertools.product((24, 72, 168, 336, 720), (.55, .60, .70, .80, .90)):
        definitions.append(("channel", lookback, threshold))
    for family, lookback, threshold in itertools.product(("rsi_trend", "rsi_revert"), (14, 72, 168), (5, 10, 15, 20, 25)):
        definitions.append((family, lookback, threshold))
    candidates = []
    for family, a, b in definitions:
        raw = signal_for(CURRENT_X, family, a, b)
        for exposure, side, vol_target, guard in itertools.product((1., 1.5, 2., 3., 4.), ("both", "long", "short"), (0., .4, .8), (False, True)):
            train_x = CURRENT_X; CURRENT_X = train_x[:split]
            train = simulate(times[:split], realized[:split], raw[:split], exposure, side, vol_target, guard)
            CURRENT_X = train_x
            score = np.log(max(train["multiple"], 1e-12)) + train["mdd_pct"] / 35 + train["positive_years"] * .15
            if train["mdd_pct"] < -55 or train["positive_years"] < train["years"] - 1: score -= 10
            candidates.append({"score": float(score), "family": family, "a": a, "b": b, "exposure": exposure, "side": side, "vol_target": vol_target, "drawdown_guard": guard, "train": train})
    candidates.sort(key=lambda z: z["score"], reverse=True)
    # The independent 30% is evaluated once for the train-selected top candidates.
    evaluated = []
    for candidate in candidates[:100]:
        raw = signal_for(CURRENT_X, candidate["family"], candidate["a"], candidate["b"])
        original_x = CURRENT_X; CURRENT_X = original_x[split:]
        test = simulate(times[split:], realized[split:], raw[split:], candidate["exposure"], candidate["side"], candidate["vol_target"], candidate["drawdown_guard"])
        CURRENT_X = original_x
        full = simulate(times, realized, raw, candidate["exposure"], candidate["side"], candidate["vol_target"], candidate["drawdown_guard"])
        passed = bool(full["return_pct"] >= 10_000 and full["mdd_pct"] >= -50 and test["return_pct"] > 0 and test["mdd_pct"] >= -50)
        evaluated.append({**candidate, "test": test, "full": full, "gate_10000": passed})
    passing = [z for z in evaluated if z["gate_10000"]]
    output = {"symbol": symbol, "generated_at": datetime.now(timezone.utc).isoformat(), "gate": "five-year >=10000%; MDD <=50%; independent test positive and MDD <=50%", "passing_count": len(passing), "best_passing": max(passing, key=lambda z: z["full"]["return_pct"]) if passing else None, "train_selected_best": evaluated[0], "top_100": evaluated}
    core.RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (core.RESULT_DIR / f"{symbol.lower()}_rule_search.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
