"""Run the Stage78 synthetic harness on locally refined Stage79 candidates."""
from pathlib import Path
import json

import validate_a_stage78_synthetic as v

v.OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage79_two_tier_refinement" / "SYNTHETIC.json"
v.CANDIDATES = {
    "top": dict(scale=1.45, stop_pct=.15, t1=.275, t2=.375, f1=.85, f2=.50, recovery=.20),
    "nearby": dict(scale=1.45, stop_pct=.15, t1=.275, t2=.375, f1=.85, f2=.55, recovery=.20),
    "lower_mdd": dict(scale=1.45, stop_pct=.15, t1=.275, t2=.375, f1=.85, f2=.45, recovery=.20),
}

if __name__ == "__main__":
    v.main()
    result = json.loads(v.OUT.read_text(encoding="utf-8"))
    result["id"] = "A-STAGE79-TWO-TIER-REFINEMENT-SYNTHETIC"
    v.OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
