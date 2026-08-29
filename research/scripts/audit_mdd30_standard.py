from __future__ import annotations

import json
import hashlib
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
        'closedDate.getUTCHours()===0',
        'const STRATEGY_TYPES = ["answer_mdd30"]',
        'MDD30 orphan signal recovery failed',
        'await triggerMdd30LeverageRepair()',
        'claim_trade_control_command',
        'scheduler authorization required',
        'private_runtime_secrets?id=eq.scheduler_auth',
    ])
    failures += require("supabase/functions/bingx-order-execute/index.ts", [
        'const MDD30_ASSETS = new Set(["BTC", "ETH", "XRP", "TRX", "SOL"]);',
        'const MDD30_EXCHANGE_LEVERAGE = 10;',
        'const MDD30_MAX_GROSS_EXPOSURE = 1.6;',
        'if (dailyNetPnl <= -dailyLossLimitUsd)',
        'if (!manualImmediateMdd30 && consecutiveLosses >= maxConsecutiveLosses',
        '"/openApi/swap/v2/trade/order/test"',
        'submitMarketOrderAndLookup',
        'clientOrderId',
        'trade_execution_reservations?created_at=lt.',
        'EdgeRuntime.waitUntil(fetch(PROJECT_URL + "/functions/v1/bingx-order-submit"',
        'action === "repair_mdd30_leverage"',
    ])
    failures += require("supabase/functions/bingx-order-submit/index.ts", [
        'rpc/reserve_real_trade_slot',
        '"/openApi/swap/v2/trade/leverage"',
        'const clientOrderId = `ciai${signalId}`',
        'actualMargin = notional / Number(p.leverage)',
        'EMERGENCY CLOSE FAILED',
    ])
    failures += require("docs/index.html", [
        "+257,597.52%", "-35.53%", "5개 독립 트리", "10x", "최대 1.6x",
        "BTC · ETH · XRP · TRX · SOL", "매일 07:00 태국시간",
        "현재 소스 5년 재현", "n.setUTCHours(0,0,0,0)",
    ])
    failures += require("supabase/functions/telegram-trade-notify/index.ts", [
        "MDD30 최종 기준", "총 실질 노출 한도: 1.6x", "5개 독립 트리",
        "매일 07:00 태국시간 재판정",
        "scheduler authorization required",
    ])
    failures += require("supabase/migrations/20260829154800_secure_scheduler_edge_calls.sql", [
        "gen_random_bytes(32)", "x-scheduler-key", "cron.alter_job(",
        "revoke all on table public.private_runtime_secrets from public, anon, authenticated",
    ])
    tree_bytes = (ROOT / "supabase/functions/coin-collector/answer_trees.ts").read_bytes()
    actual_tree_hash = hashlib.sha256(tree_bytes).hexdigest().upper()
    if actual_tree_hash != STANDARD["answer_trees_sha256"]:
        failures.append(f"answer_trees.ts hash changed: {actual_tree_hash}")
    replay = STANDARD["reference_replay"]
    if replay.get("verification_status") != "legacy_claim_not_reproduced_from_current_artifacts":
        failures.append("reference replay must disclose that the stored result is not reproducible")
    current = STANDARD["current_replay"]
    if current.get("verification_status") != "reproduced_from_current_source_and_downloaded_market_data":
        failures.append("current replay is not marked reproducible")
    if failures:
        print("MDD30 STANDARD AUDIT: FAIL")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f'MDD30 STANDARD AUDIT: PASS ({STANDARD["standard_version"]})')
    print("assets=BTC,ETH,XRP,TRX,SOL trees=5 leverage=10x gross=1.6x decision=00:00UTC/07:00Asia-Bangkok")
    print(f"answer_trees_sha256={actual_tree_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
