export const PLAN_B_EXECUTION = Object.freeze({
  targetDispatchMs: 1_000,
  warningAfterMs: 10_000,
  hardExpiryMs: 5 * 60_000,
  retryDelaysMs: [250, 750, 1_500] as const,
  maxSubmitAttempts: 3,
  maxAdversePriceMovePct: 0.35,
  ackTimeoutMs: 3_000,
  fillTimeoutMs: 10_000,
  alertAfterMs: 15_000,
});

export type PlanBSignal = {
  id: number;
  plan: "B";
  symbol: string;
  side: "long" | "short";
  signalPrice: number;
  confirmedAt: string;
};

export type EntryDecision =
  | { ok: true; ageMs: number; clientOrderId: string; warning: boolean }
  | { ok: false; ageMs: number; reason: string };

export function planBClientOrderId(signalId: number): string {
  if (!Number.isSafeInteger(signalId) || signalId <= 0) throw new Error("invalid Plan B signal id");
  return `pb${signalId}`;
}

export function validatePlanBEntry(signal: PlanBSignal, nowMs = Date.now()): EntryDecision {
  if (signal.plan !== "B") return { ok: false, ageMs: 0, reason: "plan mismatch" };
  if (!signal.symbol || !["long", "short"].includes(signal.side)) return { ok: false, ageMs: 0, reason: "invalid signal" };
  if (!(signal.signalPrice > 0)) return { ok: false, ageMs: 0, reason: "invalid signal price" };
  const confirmedMs = Date.parse(signal.confirmedAt);
  if (!Number.isFinite(confirmedMs)) return { ok: false, ageMs: 0, reason: "invalid confirmation time" };
  const ageMs = Math.max(0, nowMs - confirmedMs);
  if (ageMs > PLAN_B_EXECUTION.hardExpiryMs) return { ok: false, ageMs, reason: "signal expired" };
  return { ok: true, ageMs, clientOrderId: planBClientOrderId(signal.id), warning: ageMs > PLAN_B_EXECUTION.warningAfterMs };
}

export function adverseMovePct(side: "long" | "short", signalPrice: number, currentPrice: number): number {
  if (!(signalPrice > 0) || !(currentPrice > 0)) return Number.POSITIVE_INFINITY;
  const move = (currentPrice / signalPrice - 1) * 100;
  return side === "long" ? move : -move;
}

export function priceStillExecutable(signal: PlanBSignal, currentPrice: number): boolean {
  return adverseMovePct(signal.side, signal.signalPrice, currentPrice) <= PLAN_B_EXECUTION.maxAdversePriceMovePct;
}

export function retryAllowed(attempt: number, signal: PlanBSignal, nowMs = Date.now()): boolean {
  if (attempt < 1 || attempt >= PLAN_B_EXECUTION.maxSubmitAttempts) return false;
  return validatePlanBEntry(signal, nowMs).ok;
}

// 재시도 순서 고정:
// 1) 같은 clientOrderId로 거래소 주문 조회
// 2) 이미 접수/체결됐으면 성공 처리하고 절대 재주문하지 않음
// 3) 미접수 확인 + 신호 유효 + 가격 한도 통과 때만 다음 전송 허용
export async function waitBeforeRetry(attempt: number): Promise<void> {
  const delay = PLAN_B_EXECUTION.retryDelaysMs[Math.min(attempt - 1, PLAN_B_EXECUTION.retryDelaysMs.length - 1)];
  await new Promise((resolve) => setTimeout(resolve, delay));
}
