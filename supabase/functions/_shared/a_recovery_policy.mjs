const HOUR = 3600000;
const ASSETS = ['BTC', 'ETH', 'XRP', 'TRX', 'SOL'];

// Candle close timestamps are inclusive (.999). Expiry is the next UTC 01:00,
// not a rolling TTL measured from a later retry or from signal creation.
export function nextADecisionBoundary(closedAt) {
  if (!Number.isFinite(closedAt)) return NaN;
  const next = new Date(closedAt);
  next.setUTCHours(1, 0, 0, 0);
  if (next.getTime() <= closedAt + 1) next.setUTCDate(next.getUTCDate() + 1);
  return next.getTime();
}

export function currentADecision(closedAt, now) {
  return Number.isFinite(closedAt) && closedAt > 0 && Number.isFinite(now)
    && now >= closedAt + 1 && now < nextADecisionBoundary(closedAt);
}

export function aEntryAdmission(signal, candidates = {}, now = Date.now()) {
  const deny = reason => ({allowed: false, reason});
  if (signal?.signal_type !== 'answer_mdd30' || !ASSETS.includes(signal.symbol)
      || !['active', 'weakening'].includes(signal.status)
      || signal.signal_model_version !== 'answer_mdd30_stage184_v1'
      || signal.strategy_epoch !== 'answer_mdd30_stage75_2026_09_08') return deny('invalid A source signal');
  if (signal.entry_metrics?.c_close_intent?.status === 'pending') return deny('C close pending');
  const freeze = Date.parse(candidates.a_c_controller?.freeze_until || '');
  if (freeze > now) return deny('C entry freeze');
  const created = Date.parse(signal.created_at);
  if (!Number.isFinite(created) || created > now) return deny('invalid signal timestamp');
  const cfg = signal.entry_metrics?.strategy_config || {};
  const explicit = cfg.decision_closed_at != null;
  const boundary = explicit ? Date.parse(cfg.decision_closed_at) : NaN;
  if (explicit && !currentADecision(boundary, now)) return deny('A decision expired or future');
  if (!explicit) {
    const start = new Date(created);
    start.setUTCHours(1, 0, 0, 0);
    if (start.getTime() > created) start.setUTCDate(start.getUTCDate() - 1);
    if (!currentADecision(start.getTime() - 1, now)) return deny('A legacy decision expired');
  }
  if (now - created <= HOUR) return {allowed: true, recovery: false};

  const audit = candidates.hourly_audit;
  const auditBoundary = Date.parse(audit?.closed_at || '');
  if (audit?.status !== 'retry_pending' || !currentADecision(auditBoundary, now)) return deny('A recovery decision expired or unavailable');
  if (explicit && boundary !== auditBoundary) return deny('A recovery boundary mismatch');
  if (created < auditBoundary + 1 || created >= nextADecisionBoundary(auditBoundary)) return deny('A signal outside decision');
  const asset = Array.isArray(audit.assets) ? audit.assets.find(x => x.symbol === signal.symbol) : null;
  if (!asset?.answer || asset.answer.side !== signal.side) return deny('A recovery direction unavailable or changed');
  if (asset.signal_id != null && String(asset.signal_id) !== String(signal.id)) return deny('A recovery signal mismatch');
  const exposure = Number(cfg.base_exposure_multiplier);
  if (!(exposure > 0) || !Number.isFinite(exposure) || Math.abs(exposure - Number(asset.answer.exposure)) > 1e-9) return deny('A recovery exposure mismatch');
  return {allowed: true, recovery: true, boundary: auditBoundary};
}

// Persist the intent before the first close call. A changed market must not
// erase a previously requested close; only confirmed closure completes it.
export async function completeAClose(signal, {patch, close, now, price}) {
  if (signal.entry_metrics?.c_close_intent?.status !== 'pending') return {closed: false, pending: false};
  if (!(price > 0) || !Number.isFinite(price) || !(Number(signal.entry_price) > 0)) throw Error('invalid C close valuation');
  if (!await close(signal, 'A Stage184 C 급변 특이시장 방어')) return {closed: false, pending: true};
  const result = (price / Number(signal.entry_price) - 1) * 100 * (signal.side === 'long' ? 1 : -1);
  await patch(signal.id, {status: result > .1 ? 'success' : result < -.1 ? 'failure' : 'neutral',
    closed_at: now, exit_price: price, result_pct: result, close_reason: 'A Stage184 C 급변 특이시장 방어', updated_at: now,
    entry_metrics: {...signal.entry_metrics, c_close_intent: {...signal.entry_metrics.c_close_intent, status: 'completed', completed_at: now}}});
  return {closed: true, pending: false};
}
