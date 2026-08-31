import standard from './plan_b_standard.json' with {type:'json'};
const HOUR=3600000;
const mean=a=>a.reduce((s,v)=>s+v,0)/a.length;
// Prior windows and strict volume boundary match search_novel_patterns.py.
export function decidePlanB(symbol, rows, nowMs=Date.now()) {
  const q=standard.symbols[symbol];
  if(!q || !Number.isFinite(nowMs)) throw Error('invalid B symbol/time');
  const x=rows.filter(r=>r.t+HOUR<=nowMs);
  if(x.length<170) throw Error('insufficient completed candles');
  for(let i=0;i<x.length;i++) {
    const r=x[i];
    if(![r.t,r.o,r.h,r.l,r.c,r.v].every(Number.isFinite) || r.t%HOUR!==0 ||
       Math.min(r.o,r.h,r.l,r.c)<=0 || r.v<0 || r.h<Math.max(r.o,r.c) ||
       r.l>Math.min(r.o,r.c) || (i && r.t-x[i-1].t!==HOUR)) throw Error('invalid/gapped candles');
  }
  const last=x.at(-1), ret=last.c/x.at(-2).c-1,confirmedAt=last.t+HOUR;
  if(nowMs-confirmedAt>=300000) return {side:null,reason:'stale candle',confirmedAt};
  let side=null; const meta={return_1h:ret};
  if(q.kind==='rsi') {
    const prior=x.slice(0,-1).map(r=>r.c),d=prior.slice(1).map((v,i)=>v-prior[i]).slice(-q.window);
    const g=mean(d.map(v=>Math.max(v,0))),l=mean(d.map(v=>Math.max(-v,0)));
    meta.rsi=l===0?100:100-100/(1+g/l);
    side=meta.rsi<=q.edge?'long':meta.rsi>=100-q.edge?'short':null;
  }
  if(q.kind==='session'&&q.hours.includes(new Date(last.t).getUTCHours())) side=ret<=-q.shock?'long':ret>=q.shock?'short':null;
  if(q.kind==='squeeze') {
    const returns=x.slice(1).map((r,i)=>Math.abs(r.c/x[i].c-1));
    meta.fast_vol=mean(returns.slice(-13,-1));meta.slow_vol=mean(returns.slice(-169,-1));
    const avgVolume=mean(x.slice(-25,-1).map(r=>r.v));
    meta.volume_ratio=avgVolume>0?last.v/avgVolume:0;
    if(meta.fast_vol<meta.slow_vol*q.compression&&last.v>avgVolume*q.volume) side=ret>0?'long':ret<0?'short':null;
  }
  return {side,last,ret,meta,confirmedAt};
}
export function signalRow(symbol, decision, nowMs=Date.now()) {
  const q=standard.symbols[symbol];
  if(!decision.side || nowMs<decision.confirmedAt || nowMs-decision.confirmedAt>=300000) throw Error('ineligible signal');
  const confirmed=new Date(decision.confirmedAt).toISOString();
  return {signal_key:`${standard.isolation.client_order_prefix}:${symbol}:${confirmed}:${decision.side}`,symbol,side:decision.side,status:'active',
    signal_price:decision.last.c,volume_ratio:decision.meta.volume_ratio||0,return_1h:decision.ret,realized_vol_24h:0,
    hold_hours:q.actual_hold_hours,leverage:q.leverage,portfolio_weight:1,portfolio_scale:1,
    confirmed_at:confirmed,entry_deadline:new Date(decision.confirmedAt+300000).toISOString(),
    expires_at:new Date(decision.confirmedAt+q.actual_hold_hours*HOUR).toISOString(),strategy_id:standard.strategy_id,
    strategy_params:{...q,...decision.meta,sizing:standard.sizing},updated_at:new Date(nowMs).toISOString()};
}
