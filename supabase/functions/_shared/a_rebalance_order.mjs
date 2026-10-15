// Stable partition only: sizing, signals, targets and manual ownership stay unchanged.
export function aRebalanceOrder(assets, open, legacy) {
  const existing = new Set([...open, ...legacy].map(x => x.symbol));
  return [...assets.filter(x => existing.has(x)), ...assets.filter(x => !existing.has(x))];
}
export function aAdjustmentPending(audit) {
  return audit.some(x => ['close_failed','resize_failed','entry_failed','entry_pending'].includes(x.status));
}
