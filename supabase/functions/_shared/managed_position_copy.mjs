export function finite(value,label='value'){
 const number=Number(value);
 if(!Number.isFinite(number))throw Error(`invalid ${label}`);
 return number;
}

export function normalizedPositions(raw){
 const rows=Array.isArray(raw)?raw:Array.isArray(raw?.positions)?raw.positions:[];
 return rows.map(row=>({
  symbol:String(row?.symbol||''),
  side:String(row?.positionSide||'').toUpperCase(),
  quantity:Math.abs(finite(row?.positionAmt??row?.positionAmount??0,'position quantity')),
  entryPrice:finite(row?.avgPrice??row?.entryPrice??0,'entry price'),
  markPrice:finite(row?.markPrice??row?.avgPrice??row?.entryPrice??0,'mark price'),
  leverage:Math.max(1,finite(row?.leverage??1,'leverage'))
 })).filter(row=>row.symbol&&['LONG','SHORT'].includes(row.side)&&row.quantity>0);
}

export function targetQuantity(sourceQuantity,sourceEquity,followerEquity,precision){
 const source=finite(sourceQuantity,'source quantity'),sourceFunds=finite(sourceEquity,'source equity'),followerFunds=finite(followerEquity,'follower equity');
 if(!(sourceFunds>0)||!(followerFunds>=0)||!(source>=0))throw Error('invalid copy equity');
 const factor=10**Math.max(0,Math.floor(finite(precision,'quantity precision')));
 return Math.floor(source*followerFunds/sourceFunds*factor+1e-12)/factor;
}

export function copyDelta(actual,target,precision,minQuantity,minNotional,markPrice){
 const factor=10**Math.max(0,Math.floor(finite(precision,'quantity precision'))),a=finite(actual,'actual quantity'),t=finite(target,'target quantity');
 const quantity=Math.floor(Math.abs(t-a)*factor+1e-12)/factor;
 const threshold=Math.max(finite(minQuantity||0,'minimum quantity'),1/factor);
 if(quantity<threshold||quantity*finite(markPrice,'mark price')<finite(minNotional||0,'minimum notional'))return null;
 return{quantity,reduce:t<a};
}

export function positionKey(symbol,side){return `${String(symbol)}:${String(side).toUpperCase()}`}
