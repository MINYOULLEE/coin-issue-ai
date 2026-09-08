export function marginReturnPct(row) {
  if (row?.status !== 'closed') return null;
  if (row?.margin_usd == null || row?.net_pnl_usd == null) return null;
  const margin = Number(row?.margin_usd);
  const pnl = Number(row?.net_pnl_usd);
  if (!Number.isFinite(margin) || margin <= 0 || !Number.isFinite(pnl)) return null;
  return pnl / margin * 100;
}

export function withMarginReturn(row) {
  return {...row, margin_return_pct: marginReturnPct(row)};
}
