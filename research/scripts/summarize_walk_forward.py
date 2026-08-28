from __future__ import annotations

import json
from datetime import datetime, timezone

import replay_mdd30 as core


def main():
    rows = []
    for path in sorted(core.RESULT_DIR.glob("*_walk_forward.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        selected, holdout = item["selected"], item["holdout"]
        efficiency = holdout["return_pct"] / abs(holdout["mdd_pct"]) if holdout["mdd_pct"] else 0.0
        portfolio_gate = bool(
            item["promotion_gate"]
            and selected["worst_fold_multiple"] > 1
            and holdout["return_pct"] >= 5
            and holdout["mdd_pct"] >= -20
            and efficiency >= .5
        )
        rows.append({
            "symbol": item["symbol"], "minimum_gate": item["promotion_gate"],
            "portfolio_candidate_gate": portfolio_gate,
            "worst_validation_return_pct": (selected["worst_fold_multiple"] - 1) * 100,
            "worst_validation_mdd_pct": selected["worst_fold_mdd_pct"],
            "holdout_return_pct": holdout["return_pct"], "holdout_mdd_pct": holdout["mdd_pct"],
            "holdout_return_to_mdd": efficiency,
            "model": {k: selected[k] for k in ("neutral", "depth", "min_samples_leaf", "low", "high", "exposures")},
        })
    rows.sort(key=lambda z: (z["portfolio_candidate_gate"], z["minimum_gate"], z["holdout_return_pct"]), reverse=True)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "count": len(rows),
        "minimum_gate_count": sum(z["minimum_gate"] for z in rows),
        "portfolio_candidate_count": sum(z["portfolio_candidate_gate"] for z in rows),
        "portfolio_gate_definition": "all validation folds positive; holdout >=5%; holdout MDD <=20%; return/MDD >=0.5",
        "results": rows,
    }
    json_path = core.RESULT_DIR / "altcoin_walk_forward_summary.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Altcoin walk-forward summary", "", f"Generated: {output['generated_at']}", "",
        f"Tested: {len(rows)}; minimum gate: {output['minimum_gate_count']}; portfolio candidates: {output['portfolio_candidate_count']}", "",
        "| Symbol | Minimum | Portfolio | Worst validation | Holdout | Holdout MDD | Return/MDD |", "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for z in rows:
        lines.append(f"| {z['symbol']} | {'PASS' if z['minimum_gate'] else 'FAIL'} | {'PASS' if z['portfolio_candidate_gate'] else 'FAIL'} | {z['worst_validation_return_pct']:+.2f}% | {z['holdout_return_pct']:+.2f}% | {z['holdout_mdd_pct']:.2f}% | {z['holdout_return_to_mdd']:.2f} |")
    lines += ["", "Minimum-gate passes are observation candidates only. No live strategy changes are authorized or made by this report."]
    (core.RESULT_DIR / "altcoin_walk_forward_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
