// Stage26 adopted signals and coordination. Imported by the atomic signal cycle.
// Persistence/atomic reservation is mandatory: these pure functions do not reserve funds.
import standard from './plan_b_combination_standard.json' with {type:'json'};
import {decidePlanB} from './plan_b_signals.mjs';
export const COMBINATION_STANDARD=standard;
const H=3600000;
const mean=a=>a.reduce((s,v)=>s+v,0)/a.length;
export function combinationDecision(symbol,rows,now) {
 const rule=standard.symbols[symbol];
 if(!rule||!Number.isFinite(now)||!Array.isArray(rows))throw Error('invalid combination input');
 if(rule.group==='core')return decidePlanB(symbol,rows,now);
 const x=rows.filter(r=>r.t+H<=now);
 if(x.length<170)throw Error('insufficient completed candles');
 for(let i=0;i<x.length;i++){
  const r=x[i];
  if(![r.t,r.o,r.h,r.l,r.c,r.v].every(Number.isFinite)||r.t%H||Math.min(r.o,r.h,r.l,r.c)<=0||r.v<0||r.h<Math.max(r.o,r.c)||r.l>Math.min(r.o,r.c)||(i&&r.t-x[i-1].t!==H))throw Error('invalid/gapped candles');
 }
 const last=x.at(-1),confirmedAt=last.t+H;
 if(now-confirmedAt>=standard.coordination.entry_ttl_ms)return {side:null,reason:'stale candle',confirmedAt};
 const span=Math.max(last.h-last.l,1e-12),lower=(Math.min(last.o,last.c)-last.l)/span,upper=(last.h-Math.max(last.o,last.c))/span;
 const average=mean(x.slice(-49,-1).map(r=>r.v));
 const meta={volume_ratio:average>0?last.v/average:0,lower_wick:lower,upper_wick:upper};
 let long=false,short=false;
 if(rule.kind==='capitulation'){
  meta.move=last.c/x.at(-1-rule.window).c-1;
  long=meta.move < -rule.shock&&lower>rule.wick;
  short=meta.move > rule.shock&&upper>rule.wick;
 }else{
  const prior=x.slice(-1-rule.window,-1);
  meta.prior_low=Math.min(...prior.map(r=>r.l));meta.prior_high=Math.max(...prior.map(r=>r.h));
  long=last.l<meta.prior_low*(1-rule.excess)&&last.c>meta.prior_low&&lower>rule.wick;
  short=last.h>meta.prior_high*(1+rule.excess)&&last.c<meta.prior_high&&upper>rule.wick;
 }
 const side=last.v>average*rule.volume?(long?'long':short?'short':null):null;
 return {side,last,ret:last.c/x.at(-2).c-1,meta,confirmedAt};
}

// One complete, chronological hour at a time. Missing hours must be replayed,
// never initialized as 'idle'. Caller must atomically persist returned state AND signals.
export function advanceOpportunities(previous,decisions,confirmedAt){
 if(previous?.version!==standard.standard_version||!Number.isFinite(confirmedAt)||confirmedAt%H||previous.lastConfirmedAt+H!==confirmedAt)throw Error('opportunity state requires chronological bootstrap/replay');
 const symbols=Object.keys(standard.symbols);
 for(const symbol of symbols){
  const d=decisions[symbol],n=previous.nextEligibleAt?.[symbol];
  if(!d||d.confirmedAt!==confirmedAt||d.reason==='stale candle'||!Number.isFinite(n)||!['long','short',null].includes(d.side))throw Error('incomplete same-hour decisions/state');
 }
 if(!Number.isFinite(previous.coreBusyUntil))throw Error('invalid core opportunity interval');
 const state={...previous,nextEligibleAt:{...previous.nextEligibleAt},lastConfirmedAt:confirmedAt};
 const selected=[];
 for(const group of ['core','supplement'])for(const symbol of symbols){
  const rule=standard.symbols[symbol],d=decisions[symbol];
  if(rule.group!==group||!d.side||confirmedAt<state.nextEligibleAt[symbol])continue;
  if(group==='supplement'&&confirmedAt<state.coreBusyUntil)continue;
  const expiresAt=confirmedAt+rule.actual_hold_hours*H;
  state.nextEligibleAt[symbol]=confirmedAt+rule.opportunity_cooldown_hours*H;
  if(group==='core')state.coreBusyUntil=Math.max(state.coreBusyUntil,expiresAt);
  selected.push({symbol,group,side:d.side,confirmedAt,expiresAt,entryDeadline:confirmedAt+300000,leverage:rule.leverage,targetMarginFraction:rule.target_margin_fraction,strategyId:standard.strategy_id});
 }
 return {state,selected};
}

export function handoffEligibility({signal,now,price,signalPrice,intents,coreBusyUntil}){
 const rule=standard.symbols[signal.symbol];
 if(!rule||signal.strategyId!==standard.strategy_id||!['long','short'].includes(signal.side)||!Array.isArray(intents)||!Number.isFinite(coreBusyUntil))return {ok:false,reason:'invalid state'};
 if(!Number.isFinite(signal.confirmedAt)||!Number.isFinite(now)||now<signal.confirmedAt||now-signal.confirmedAt>=300000)return {ok:false,reason:'expired or future signal'};
 const active=intents.filter(i=>!['closed','rejected','expired'].includes(i.status));
 if(active.some(i=>!standard.symbols[i.symbol]||!['reserved','submitted','unknown','partial','open','closing'].includes(i.status)))return {ok:false,reason:'unknown reservation state'};
 if(active.some(i=>['submitted','unknown','partial','closing'].includes(i.status)))return {ok:false,reason:'reconciliation required'};
 if(active.some(i=>standard.symbols[i.symbol].group!==rule.group))return {ok:false,reason:'await opposite group close confirmation'};
 if(active.some(i=>i.symbol===signal.symbol))return {ok:false,reason:'symbol already reserved'};
 if(rule.group==='supplement'&&now<coreBusyUntil)return {ok:false,reason:'core opportunity interval'};
 if(![price,signalPrice].every(v=>Number.isFinite(v)&&v>0)||(price/signalPrice-1)*(signal.side==='long'?1:-1)>standard.coordination.max_adverse_move_fraction)return {ok:false,reason:'adverse price or invalid quote'};
 return {ok:true,expiresAt:signal.confirmedAt+rule.actual_hold_hours*H};
}

export function allocateCombination({balance,equity,availableMargin,reservedMargin,proposals}){
 if(![balance,equity,availableMargin,reservedMargin].every(Number.isFinite)||reservedMargin<0)throw Error('invalid account');
 const available=Math.max(0,Math.min(balance-reservedMargin,equity-reservedMargin,availableMargin)-Math.max(equity,0)*.05);
 const seen=new Set(),groups=new Set();
 const demands=proposals.map(p=>{
  const rule=standard.symbols[p.symbol];
  if(!rule||seen.has(p.symbol)||!Number.isFinite(p.entryPrice)||p.entryPrice<=0)throw Error('invalid proposal');
  seen.add(p.symbol);groups.add(rule.group);
  const margin=Math.max(equity,0)*rule.target_margin_fraction;
  return {p,rule,margin,cost:margin*(1+rule.leverage*(2*standard.research_costs.fee_each_side+standard.research_costs.funding_hourly*rule.actual_hold_hours))};
 });
 if(groups.size>1)throw Error('core and supplement cannot share a batch');
 const total=demands.reduce((s,x)=>s+x.cost,0),scale=total>0?Math.min(1,available/total):0;
 return {available,scale,orders:demands.map(({p,rule,margin,cost})=>({symbol:p.symbol,group:rule.group,margin:margin*scale,requiredReservation:cost*scale,quantity:margin*scale*rule.leverage/p.entryPrice,leverage:rule.leverage}))};
}
