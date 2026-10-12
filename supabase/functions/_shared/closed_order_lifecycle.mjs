const time=o=>{const v=Number(o.time??o.updateTime);return Number.isFinite(v)&&v>0?(v<1e11?v*1000:v):NaN;};
export const isReduceOrder=o=>o.reduceOnly===true||o.reduceOnly===1||String(o.reduceOnly).toLowerCase()==='true';
export function closedOrderGroupVerified(group,liveIds=new Set()){
 if(!Array.isArray(group)||!group.length)return false;
 const pid=String(group[0].positionID??group[0].positionId??'');
 if(!pid||liveIds.has(pid))return false;
 const opens=group.filter(o=>!isReduceOrder(o)),closes=group.filter(isReduceOrder);
 if(!opens.length||!closes.length||!group.every(o=>Number.isFinite(time(o))))return false;
 const qty=o=>Math.abs(Number(o.executedQty??o.origQty));
 if(!group.every(o=>Number.isFinite(qty(o))&&qty(o)>0))return false;
 const opening=opens.reduce((s,o)=>s+qty(o),0),closing=closes.reduce((s,o)=>s+qty(o),0);
 // A rolling query can contain old reductions and later adds to the same position.
 // Excess reductions and backwards lifecycle times are not a completed trade.
 return Math.abs(opening-closing)<=Math.max(1e-10,opening*1e-8)&&
  Math.min(...opens.map(time))<=Math.min(...closes.map(time))&&
  Math.max(...opens.map(time))<=Math.max(...closes.map(time));
}
