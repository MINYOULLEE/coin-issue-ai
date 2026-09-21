function qty(value) {
  const n=Number(value);
  if(!Number.isFinite(n)) throw Error('invalid position quantity');
  return Math.abs(n);
}

export function liveSideQuantity(positions,symbol,side) {
  const pair=symbol.endsWith('-USDT')?symbol:`${symbol}-USDT`;
  return (positions||[]).filter(p=>String(p.symbol)===pair&&String(p.positionSide).toUpperCase()===String(side).toUpperCase())
    .reduce((sum,p)=>sum+qty(p.positionAmt??p.positionAmount??0),0);
}

export function ledgerSideQuantity(openTrades,symbol,side) {
  return (openTrades||[]).filter(t=>String(t.symbol)===symbol&&String(t.side).toLowerCase()===String(side).toLowerCase())
    .reduce((sum,t)=>sum+qty(t.quantity||0),0);
}

export function manualOppositeQuantity(positions,openTrades,symbol,automaticSide) {
  const opposite=String(automaticSide).toLowerCase()==='long'?'short':'long';
  return Math.max(0,liveSideQuantity(positions,symbol,opposite)-ledgerSideQuantity(openTrades,symbol,opposite));
}

export function hasAnyOppositePosition(positions,symbol,requestedSide) {
  const opposite=String(requestedSide).toLowerCase()==='long'?'SHORT':'LONG';
  return liveSideQuantity(positions,symbol,opposite)>1e-10;
}
