import standard from './plan_b_standard.json' with { type: 'json' };
export const PLAN_B_STANDARD = standard;

// Pure preflight calculation only. An executor must atomically reserve this
// budget in B's DB and reconcile actual fills; this is not a reservation itself.
export function allocatePlanB({ plan, strategyId, balance, equity, reservedMargin, proposals,
  feeRate = standard.research_costs.fee_each_side,
  fundingHourly = standard.research_costs.funding_hourly }) {
  if (plan !== 'B' || strategyId !== standard.strategy_id) throw Error('B plan/version mismatch');
  for (const value of [balance, equity, reservedMargin, feeRate, fundingHourly]) {
    if (!Number.isFinite(value)) throw Error('nonfinite account value');
  }
  if (reservedMargin < 0 || feeRate < 0 || fundingHourly < 0) throw Error('negative reserve/cost');
  const seen = new Set();
  const targetFor = rule => Math.max(equity, 0) * (rule.target_margin_fraction ?? standard.sizing.target_margin_fraction);
  const available = Math.max(0, Math.min(balance - reservedMargin, equity - reservedMargin)
    - Math.max(equity, 0) * standard.sizing.cash_buffer_fraction);
  const demands = proposals.map(p => {
    const rule = standard.symbols[p.symbol];
    if (!rule || seen.has(p.symbol) || !Number.isFinite(p.entryPrice) || p.entryPrice <= 0) throw Error('invalid/duplicate B proposal');
    seen.add(p.symbol);
    return targetFor(rule) * (1 + rule.leverage * (2 * feeRate + fundingHourly * rule.actual_hold_hours));
  });
  const total = demands.reduce((a, b) => a + b, 0);
  const shrink = total > 0 ? Math.min(1, available / total) : 0;
  const orders = proposals.map((p, i) => {
    const rule = standard.symbols[p.symbol];
    const margin = targetFor(rule) * shrink;
    return { plan: 'B', strategyId, symbol: p.symbol, margin,
      requiredReservation: demands[i] * shrink, leverage: rule.leverage,
      notional: margin * rule.leverage, quantity: margin * rule.leverage / p.entryPrice,
      actualHoldHours: rule.actual_hold_hours, rejected: margin < 1e-9 };
  });
  return { available, shrink, orders };
}
