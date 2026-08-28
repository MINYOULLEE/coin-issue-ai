from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_mdd30 as core


def dataset(symbol: str, decision_hour: int = 0):
    rows = core.read_candles(core.DATA_DIR / f"{symbol}USDT_1h.csv")
    items = []
    for i in range(720, len(rows) - 24):
        stamp = datetime.fromtimestamp(rows[i]["t"] / 1000, timezone.utc)
        if stamp.hour != decision_hour:
            continue
        future_return = rows[i + 24]["c"] / rows[i]["c"] - 1
        items.append((rows[i]["t"], core.feature_vector(rows[:i + 1]), future_return))
    return rows, items


def classify(returns: np.ndarray, neutral: float) -> np.ndarray:
    return np.where(returns > neutral, 1, np.where(returns < -neutral, -1, 0))


def simulate(times, returns, directions, confidence, low, high, exposures, fee=.0005):
    low_x, mid_x, high_x = exposures
    target = directions * np.where(confidence < low, low_x, np.where(confidence < high, mid_x, high_x))
    equity = 1.0; peak = 1.0; mdd = 0.0; previous = 0.0; trades = 0
    yearly = {}
    for stamp, ret, position in zip(times, returns, target):
        equity *= max(0.0, 1 - abs(position - previous) * fee)
        trades += position != previous
        equity *= max(0.0, 1 + position * ret)
        peak = max(peak, equity); mdd = min(mdd, equity / peak - 1)
        yearly[str(datetime.fromtimestamp(stamp / 1000, timezone.utc).year)] = equity
        previous = position
    return {
        "multiple": equity, "return_pct": (equity - 1) * 100,
        "mdd_pct": mdd * 100, "changes": int(trades),
        "year_end_multiple": yearly,
    }


def probabilities(model, x):
    p = model.predict_proba(x)
    indices = np.argmax(p, axis=1)
    return model.classes_[indices].astype(float), p[np.arange(len(p)), indices]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", nargs="?", default="BNB")
    args = parser.parse_args()
    symbol = args.symbol.upper()
    _, items = dataset(symbol)
    times = np.array([x[0] for x in items], dtype=np.int64)
    x = np.array([x[1] for x in items], dtype=float)
    future = np.array([x[2] for x in items], dtype=float)
    train_end = int(len(x) * .55)
    validation_end = int(len(x) * .70)
    candidates = []
    for neutral in (.001, .002, .003, .005, .0075, .01):
        y = classify(future, neutral)
        for depth in range(3, 9):
            for leaf in (2, 5, 10, 20):
                model = DecisionTreeClassifier(
                    max_depth=depth, min_samples_leaf=leaf,
                    class_weight="balanced", random_state=42,
                ).fit(x[:train_end], y[:train_end])
                train_dir, train_conf = probabilities(model, x[:train_end])
                validation_dir, validation_conf = probabilities(model, x[train_end:validation_end])
                test_dir, test_conf = probabilities(model, x[validation_end:])
                for low, high in ((.45, .60), (.50, .65), (.55, .70), (.55, .75), (.60, .75)):
                    for exposure in ((0., .25, .5), (0., .5, 1.), (.1, .5, 1.), (0., 1., 1.5), (.25, 1., 1.5), (.5, 1.5, 2.)):
                        train = simulate(times[:train_end], future[:train_end], train_dir, train_conf, low, high, exposure)
                        validation = simulate(times[train_end:validation_end], future[train_end:validation_end], validation_dir, validation_conf, low, high, exposure)
                        test = simulate(times[validation_end:], future[validation_end:], test_dir, test_conf, low, high, exposure)
                        # Selection uses validation only. The final 30% remains untouched.
                        score = np.log(max(validation["multiple"], 1e-9)) + validation["mdd_pct"] / 25 - depth * .015
                        if validation["mdd_pct"] < -35 or validation["multiple"] <= 1:
                            score -= 10
                        candidates.append({
                            "score": float(score), "neutral": neutral, "depth": depth,
                            "min_samples_leaf": leaf, "low": low, "high": high,
                            "exposures": exposure, "train": train, "validation": validation, "test": test,
                        })
    candidates.sort(key=lambda z: z["score"], reverse=True)
    best = candidates[0]
    test_survivors = [z for z in candidates if z["test"]["multiple"] > 1 and z["test"]["mdd_pct"] >= -30]
    y = classify(future, best["neutral"])
    final_model = DecisionTreeClassifier(
        max_depth=best["depth"], min_samples_leaf=best["min_samples_leaf"],
        class_weight="balanced", random_state=42,
    ).fit(x, y)
    full_dir, full_conf = probabilities(final_model, x)
    full = simulate(times, future, full_dir, full_conf, best["low"], best["high"], best["exposures"])
    output = {
        "symbol": symbol, "generated_at": datetime.now(timezone.utc).isoformat(),
        "samples": len(x), "train_end": train_end, "validation_end": validation_end,
        "train_range": [datetime.fromtimestamp(times[0] / 1000, timezone.utc).isoformat(), datetime.fromtimestamp(times[train_end - 1] / 1000, timezone.utc).isoformat()],
        "validation_range": [datetime.fromtimestamp(times[train_end] / 1000, timezone.utc).isoformat(), datetime.fromtimestamp(times[validation_end - 1] / 1000, timezone.utc).isoformat()],
        "test_range": [datetime.fromtimestamp(times[validation_end] / 1000, timezone.utc).isoformat(), datetime.fromtimestamp(times[-1] / 1000, timezone.utc).isoformat()],
        "selection": best, "full_in_sample_refit": full,
        "independent_test_survivor_count": len(test_survivors),
        "best_independent_test_diagnostic": max(test_survivors, key=lambda z: z["test"]["multiple"]) if test_survivors else None,
        "tree": {"nodes": int(final_model.tree_.node_count), "depth": int(final_model.tree_.max_depth), "leaves": int(final_model.tree_.n_leaves)},
        "top_20": candidates[:20],
        "warning": "The full refit is an answer-sheet/in-sample figure. Promotion requires portfolio and walk-forward validation.",
    }
    core.RESULT_DIR.mkdir(parents=True, exist_ok=True)
    path = core.RESULT_DIR / f"{symbol.lower()}_answer_research.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
