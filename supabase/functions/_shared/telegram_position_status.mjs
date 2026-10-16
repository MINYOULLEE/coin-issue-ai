const finite = value => value == null || String(value).trim() === '' ? null
  : Number.isFinite(Number(value)) ? Number(value) : null;
const positive = (...values) => values.map(finite).find(value => value > 0) ?? null;
const number = (value, digits = 2) => value == null ? '조회 불가'
  : value.toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits});
const signed = value => value == null ? '조회 불가' : `${value >= 0 ? '+' : ''}${number(value)}`;
const price = value => number(value, value < 10 ? 5 : 2);
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

export function positionStatus(position) {
  const amount = finite(position.positionAmt ?? position.positionAmount);
  const explicitSide = String(position.positionSide || '').toUpperCase();
  const side = ['LONG', 'SHORT'].includes(explicitSide) ? explicitSide
    : amount > 0 ? 'LONG' : amount < 0 ? 'SHORT' : null;
  const pnl = finite(position.unrealizedProfit ?? position.unrealizedPnl);
  const margin = positive(position.initialMargin, position.positionMargin, position.margin);
  const entry = positive(position.avgPrice, position.entryPrice);
  const liquidation = positive(position.liquidationPrice);
  let mark = positive(position.markPrice), estimated = false;
  // Linear USDT PnL reconstructs the price from this same position snapshot,
  // avoiding another quote request (and a different observation timestamp).
  if (!mark && entry && amount && pnl != null && side) {
    mark = positive(entry + pnl / Math.abs(amount) * (side === 'LONG' ? 1 : -1));
    estimated = mark != null;
  }
  const roe = pnl != null && margin ? pnl / margin * 100 : null;
  const distance = mark && liquidation && side
    ? (side === 'LONG' ? mark - liquidation : liquidation - mark) / mark * 100 : null;
  return {side, pnl, margin, roe, mark, liquidation, distance, estimated};
}

export function positionStatusText(position, detailed = false) {
  const metrics = positionStatus(position);
  const symbol = escape(String(position.symbol || '').replace(/-USDT$/, ''));
  const leverage = positive(position.leverage);
  const heading = `<b>${symbol} ${metrics.side || '방향 조회 불가'} · ${leverage ? number(leverage, 0) + 'x' : '배율 조회 불가'}</b>`;
  const detail = detailed ? `\n진입 ${price(positive(position.avgPrice, position.entryPrice))} · 수량 ${number(Math.abs(finite(position.positionAmt ?? position.positionAmount) ?? 0), 6)}` : '';
  const pnl = `\n미실현 <b>${signed(metrics.pnl)} USDT</b> · 담보 손익률 <b>${metrics.roe == null ? '조회 불가' : signed(metrics.roe) + '%'}</b>`;
  const distance = metrics.distance == null ? '거리 조회 불가'
    : metrics.distance <= 0 ? '⚠️ 청산가 도달/초과'
    : `거리 ${number(metrics.distance)}%${metrics.estimated ? ' (가격 추정)' : ''}`;
  return `${heading}${detail}${pnl}\n청산가 ${price(metrics.liquidation)} · ${distance}`;
}
