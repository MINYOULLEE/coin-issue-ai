import {COMBINATION_STANDARD as STANDARD,combinationDecision,advanceOpportunities} from './plan_b_combination.mjs';
import {signalRow} from './plan_b_signals.mjs';
import {btcRegime,applyBtcEntryGuard} from './plan_b_risk.mjs';
const H=3600000;
const checked=async q=>{const {data,error}=await q;if(error)throw error;return data;};
export async function runCombinationSignals({sb,fetchCandles,now=Date.now,preview=false}){
 const stamp=now(),boundary=Math.floor(stamp/H)*H;
 const saved=await checked(sb.from('plan_b_opportunity_state').select('payload').eq('id','singleton').single());
 let state=saved.payload;
 if(state.version!==STANDARD.standard_version)throw Error('B opportunity version mismatch');
 if(state.lastConfirmedAt>boundary)throw Error('future opportunity state');
 if(!preview&&state.lastConfirmedAt===boundary)return {ok:true,plan:'B',strategy_id:STANDARD.strategy_id,confirmed_at:new Date(boundary).toISOString(),mode:'up_to_date',results:[],orders_submitted:0};
 if(boundary-state.lastConfirmedAt>800*H)throw Error('B recovery exceeds candle window; explicit backfill required');
 const data=Object.fromEntries(await Promise.all(Object.keys(STANDARD.symbols).map(async symbol=>[symbol,await fetchCandles(symbol)])));
 let btc=[];try{btc=await fetchCandles('BTC');}catch(_error){btc=[];}
 if(preview){
  const raw=Object.fromEntries(Object.keys(data).map(symbol=>[symbol,combinationDecision(symbol,data[symbol],stamp)]));
  const guarded=applyBtcEntryGuard(raw,btcRegime(btc,boundary,STANDARD.risk_overlay.btc_regime.lookback_completed_hours,STANDARD.risk_overlay.btc_regime.return_threshold),STANDARD.risk_overlay.btc_regime.protected_symbols);
  const outcomes=Object.entries(guarded).map(([symbol,decision])=>({symbol,...decision}));
  return {ok:true,plan:'B',strategy_id:STANDARD.strategy_id,mode:'preview',orders_submitted:0,outcomes};
 }
 const steps=[];
 for(let t=state.lastConfirmedAt+H;t<=boundary;t+=H){
  const rawDecisions=Object.fromEntries(Object.keys(data).map(symbol=>[symbol,combinationDecision(symbol,data[symbol].filter(r=>r.t+H<=t).slice(-170),t)]));
  const regime=btcRegime(btc,t,STANDARD.risk_overlay.btc_regime.lookback_completed_hours,STANDARD.risk_overlay.btc_regime.return_threshold);
  const decisions=applyBtcEntryGuard(rawDecisions,regime,STANDARD.risk_overlay.btc_regime.protected_symbols);
  const next=advanceOpportunities(state,decisions,t);
  const rows=next.selected.map(x=>signalRow(x.symbol,decisions[x.symbol],t));
  steps.push({state:next.state,decisions:Object.fromEntries(Object.entries(decisions).map(([k,d])=>[k,{side:d.side,confirmedAt:d.confirmedAt,diagnostic:d.diagnostic||null}])),signals:rows});
  state=next.state;
 }
 const committed=await checked(sb.rpc('plan_b_publish_opportunities',{p_expected:saved.payload.lastConfirmedAt,p_steps:steps}));
 const latest=steps.at(-1);
 return {ok:true,plan:'B',strategy_id:STANDARD.strategy_id,mode:committed?'published':'concurrent_worker_won',confirmed_at:new Date(state.lastConfirmedAt).toISOString(),recovered_hours:steps.length,results:latest?.signals.map(s=>({symbol:s.symbol,side:s.side,ok:true,stored:committed}))||[],diagnostics:latest?Object.fromEntries(Object.entries(latest.decisions).map(([symbol,d])=>[symbol,d.diagnostic])):{},orders_submitted:0};
}
