from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np
from sklearn.tree import DecisionTreeClassifier

import train_coin_answer as base
import replay_mdd30 as core


def build_dataset(symbol: str, max_horizon: int = 72):
    rows = core.read_candles(core.DATA_DIR / f"{symbol}USDT_1h.csv")
    items = []
    for i in range(720, len(rows) - max_horizon):
        if datetime.fromtimestamp(rows[i]["t"] / 1000, timezone.utc).hour != 0:
            continue
        future = {h: rows[i + h]["c"] / rows[i]["c"] - 1 for h in (6, 12, 24, 48, 72)}
        realized_24h = rows[i + 24]["c"] / rows[i]["c"] - 1
        items.append((rows[i]["t"], core.feature_vector(rows[:i + 1]), future, realized_24h))
    return items


def simulate(times, realized, direction, confidence, low, high, exposure, side_mode, fee=.0005):
    direction = direction.copy()
    if side_mode == "long":
        direction[direction < 0] = 0
    elif side_mode == "short":
        direction[direction > 0] = 0
    low_x, mid_x, high_x = exposure
    target = direction * np.where(confidence < low, low_x, np.where(confidence < high, mid_x, high_x))
    equity = 1.; peak = 1.; mdd = 0.; previous = 0.; changes = 0
    yearly = {}
    for stamp, ret, position in zip(times, realized, target):
        equity *= max(0., 1 - abs(position - previous) * fee)
        changes += position != previous
        equity *= max(0., 1 + position * ret)
        peak = max(peak, equity); mdd = min(mdd, equity / peak - 1)
        yearly[str(datetime.fromtimestamp(stamp / 1000, timezone.utc).year)] = equity
        previous = position
    return {"multiple": equity, "return_pct": (equity - 1) * 100, "mdd_pct": mdd * 100, "changes": int(changes), "year_end_multiple": yearly}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    symbol = parser.parse_args().symbol.upper()
    items = build_dataset(symbol)
    times = np.array([z[0] for z in items], dtype=np.int64)
    x = np.array([z[1] for z in items], dtype=float)
    realized = np.array([z[3] for z in items], dtype=float)
    n = len(x); boundaries = [int(n * p) for p in (.40, .55, .70, .85)]
    folds = [(boundaries[0], boundaries[1]), (boundaries[1], boundaries[2]), (boundaries[2], boundaries[3])]
    records = []
    for horizon in (6, 12, 24, 48, 72):
        forecast = np.array([z[2][horizon] for z in items], dtype=float)
        for neutral in (.002, .005, .01, .015):
            y = base.classify(forecast, neutral)
            for depth in (3, 4, 5, 6, 7):
                for leaf in (5, 10, 20):
                    fold_predictions = []
                    for train_end, validation_end in folds:
                        model = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=leaf, class_weight="balanced", random_state=42).fit(x[:train_end], y[:train_end])
                        fold_predictions.append(base.probabilities(model, x[train_end:validation_end]))
                    for low, high in ((.45, .60), (.55, .70), (.60, .75)):
                        for exposure in ((0., .25, .5), (0., .5, 1.), (.1, .5, 1.)):
                            for side_mode in ("both", "long", "short"):
                                results = []
                                for (train_end, validation_end), (direction, confidence) in zip(folds, fold_predictions):
                                    results.append(simulate(times[train_end:validation_end], realized[train_end:validation_end], direction, confidence, low, high, exposure, side_mode))
                                multiples = [z["multiple"] for z in results]; worst_mdd = min(z["mdd_pct"] for z in results)
                                score = sum(np.log(max(z, 1e-9)) for z in multiples) / 3 + worst_mdd / 20 - depth * .01
                                # A repair must survive every historical validation regime.
                                if min(multiples) <= 1 or worst_mdd < -25:
                                    score -= 10
                                records.append({"score": float(score), "horizon": horizon, "neutral": neutral, "depth": depth, "min_samples_leaf": leaf, "low": low, "high": high, "exposures": exposure, "side_mode": side_mode, "folds": results, "worst_fold_return_pct": (min(multiples) - 1) * 100, "worst_fold_mdd_pct": worst_mdd})
    records.sort(key=lambda z: z["score"], reverse=True)
    chosen = records[0]; holdout_start = boundaries[3]
    forecast = np.array([z[2][chosen["horizon"]] for z in items], dtype=float)
    y = base.classify(forecast, chosen["neutral"])
    model = DecisionTreeClassifier(max_depth=chosen["depth"], min_samples_leaf=chosen["min_samples_leaf"], class_weight="balanced", random_state=42).fit(x[:holdout_start], y[:holdout_start])
    direction, confidence = base.probabilities(model, x[holdout_start:])
    holdout = simulate(times[holdout_start:], realized[holdout_start:], direction, confidence, chosen["low"], chosen["high"], chosen["exposures"], chosen["side_mode"])
    full_model = DecisionTreeClassifier(max_depth=chosen["depth"], min_samples_leaf=chosen["min_samples_leaf"], class_weight="balanced", random_state=42).fit(x, y)
    full_direction, full_confidence = base.probabilities(full_model, x)
    full_in_sample = simulate(times, realized, full_direction, full_confidence, chosen["low"], chosen["high"], chosen["exposures"], chosen["side_mode"])
    return_to_mdd = holdout["return_pct"] / abs(holdout["mdd_pct"]) if holdout["mdd_pct"] else 0
    gate = bool(chosen["worst_fold_return_pct"] > 0 and chosen["worst_fold_mdd_pct"] >= -25 and holdout["return_pct"] >= 5 and holdout["mdd_pct"] >= -20 and return_to_mdd >= .5)
    output = {"symbol": symbol, "generated_at": datetime.now(timezone.utc).isoformat(), "samples": n, "boundaries": boundaries, "selected_without_holdout": chosen, "full_in_sample_reference": full_in_sample, "holdout": holdout, "holdout_return_to_mdd": return_to_mdd, "repair_gate": gate, "tree": {"nodes": int(model.tree_.node_count), "depth": int(model.tree_.max_depth), "leaves": int(model.tree_.n_leaves)}, "top_20": records[:20]}
    core.RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (core.RESULT_DIR / f"{symbol.lower()}_repair.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
