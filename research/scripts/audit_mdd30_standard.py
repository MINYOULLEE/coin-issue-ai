from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STANDARD = json.loads((ROOT / "strategy/mdd30_standard.json").read_text(encoding="utf-8"))


def require(path: str, snippets: list[str]) -> list[str]:
    text = (ROOT / path).read_text(encoding="utf-8")
    return [f"{path}: missing {snippet!r}" for snippet in snippets if snippet not in text]


def main() -> int:
    assets = STANDARD["assets"]
    failures: list[str] = []
    failures += require("supabase/functions/coin-collector/index.ts", [
        f'const ANSWER_ASSETS = {json.dumps(assets, separators=(",", ":"))};',
        'signal_type:type',
        'max_gross_exposure:1.6',
        'exchange_leverage:leverage',
        'await enter(symbol,"answer_mdd30",answer.side,Number(answer.exposure),10,24',
    ])
    failures += require("supabase/functions/bingx-order-execute/index.ts", [
        'const MDD30_ASSETS = new Set(["BTC", "ETH", "XRP", "TRX", "SOL"]);',
        'const MDD30_EXCHANGE_LEVERAGE = 10;',
        'const MDD30_MAX_GROSS_EXPOSURE = 1.6;',
    ])
    failures += require("docs/index.html", [
        "+799,385.16%", "-29.22%", "5개 독립 트리", "10x", "최대 1.6x",
        "BTC · ETH · XRP · TRX · SOL", "매일 08:00 태국시간",
    ])
    failures += require("supabase/functions/telegram-trade-notify/index.ts", [
        "MDD30 최종 기준", "총 실질 노출 한도: 1.6x", "5개 독립 트리",
    ])
    if failures:
        print("MDD30 STANDARD AUDIT: FAIL")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f'MDD30 STANDARD AUDIT: PASS ({STANDARD["standard_version"]})')
    print("assets=BTC,ETH,XRP,TRX,SOL trees=5 leverage=10x gross=1.6x decision=00:00UTC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
