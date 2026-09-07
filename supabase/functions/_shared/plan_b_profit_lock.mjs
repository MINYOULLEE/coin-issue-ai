import standard from './plan_b_standard.json' with {type:'json'};

const HOUR=3600000;
const finitePositive=value=>Number.isFinite(Number(value))&&Number(value)>0;

export function atr24(rows){
 if(!Array.isArray(rows)||rows.length<25)throw Error('profit lock requires 25 completed candles');
 const x=rows.slice(-25);
 const ranges=[];
 for(let i=1;i<x.length;i++){
  const previous=Number(x[i-1].c),high=Number(x[i].h),low=Number(x[i].l);
  if(![previous,high,low].every(Number.isFinite)||previous<=0||low<=0||high<low)throw Error('invalid profit lock candles');
  ranges.push(Math.max(high-low,Math.abs(high-previous),Math.abs(low-previous)));
 }
 return ranges.reduce((sum,value)=>sum+value,0)/ranges.length;
}

export function profitLockPolicy({symbol,side,entryPrice,atr}){
 const rule=standard.profit_lock?.symbols?.[symbol];
 const ratio=rule?.[side==='long'?'trigger_atr_ratio_long':'trigger_atr_ratio_short'];
 if(!rule)return null;
 if(!['long','short'].includes(side)||![entryPrice,atr,ratio,rule.keep_fraction].every(finitePositive))throw Error('invalid profit lock policy input');
 return {policy:standard.profit_lock.policy_version,triggerPct:Number(atr)/Number(entryPrice)*Number(ratio),keepFraction:Number(rule.keep_fraction)};
}

export function normalizeKlines(raw,intervalMs,now=Date.now()){
 const rows=Array.isArray(raw)?raw:Array.isArray(raw?.data)?raw.data:Array.isArray(raw?.list)?raw.list:[];
 return rows.map(row=>{
  if(Array.isArray(row))return {t:Number(row[0]),o:Number(row[1]),h:Number(row[2]),l:Number(row[3]),c:Number(row[4])};
  return {t:Number(row.t??row.time??row.openTime??row.timestamp),o:Number(row.o??row.open??row.openPrice),h:Number(row.h??row.high??row.highPrice),l:Number(row.l??row.low??row.lowPrice),c:Number(row.c??row.close??row.closePrice)};
 }).map(row=>({...row,t:row.t<100000000000?row.t*1000:row.t})).filter(row=>[row.t,row.o,row.h,row.l,row.c].every(Number.isFinite)&&row.t+intervalMs<=now).sort((a,b)=>a.t-b.t);
}
export const normalizeHourlyKlines=(raw,now=Date.now())=>normalizeKlines(raw,HOUR,now);

export function advanceProfitLock(trade,candle){
 if(!trade.profit_lock_policy||!finitePositive(trade.profit_lock_trigger_pct)||!finitePositive(trade.profit_lock_keep_fraction))return null;
 const entry=Number(trade.entry_price),lastAt=Date.parse(trade.profit_lock_last_candle_at||0);
 if(!finitePositive(entry)||!candle||!finitePositive(candle.c)||!Number.isFinite(candle.t)||candle.t+HOUR<=lastAt)return null;
 const direction=trade.side==='long'?1:-1;
 const favorable=(Number(candle.c)/entry-1)*direction;
 const peak=Math.max(Number(trade.profit_lock_peak_pct)||0,favorable);
 const armed=peak>=Number(trade.profit_lock_trigger_pct);
 const previousFloor=Number(trade.profit_lock_floor_price);
 const candidate=armed?entry*(1+direction*peak*Number(trade.profit_lock_keep_fraction)):null;
 const floor=!armed?null:finitePositive(previousFloor)?(direction===1?Math.max(previousFloor,candidate):Math.min(previousFloor,candidate)):candidate;
 const armedAt=trade.profit_lock_armed_at||(armed?new Date(candle.t+HOUR).toISOString():null);
 return {profit_lock_peak_pct:peak,profit_lock_floor_price:floor,profit_lock_armed_at:armedAt,profit_lock_last_candle_at:new Date(candle.t+HOUR).toISOString()};
}

export function profitFloorBreached(trade,markPrice,now=Date.now(),minuteCandles=[]){
 const floor=Number(trade.profit_lock_floor_price),armedAt=Date.parse(trade.profit_lock_armed_at||0),mark=Number(markPrice);
 if(!finitePositive(floor)||!finitePositive(mark)||!Number.isFinite(armedAt)||now<armedAt)return false;
 const afterArm=minuteCandles.filter(c=>c.t>=armedAt);
 return trade.side==='long'?mark<=floor||afterArm.some(c=>c.l<=floor):mark>=floor||afterArm.some(c=>c.h>=floor);
}
