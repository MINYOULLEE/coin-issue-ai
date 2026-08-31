import {COMBINATION_STANDARD as STANDARD,combinationDecision,advanceOpportunities} from './plan_b_combination.mjs';
import {signalRow} from './plan_b_signals.mjs';
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
 if(preview){
  const outcomes=Object.keys(data).map(symbol=>({symbol,...combinationDecision(symbol,data[symbol],stamp)}));
  return {ok:true,plan:'B',strategy_id:STANDARD.strategy_id,mode:'preview',orders_submitted:0,outcomes};
 }
 const steps=[];
 for(let t=state.lastConfirmedAt+H;t<=boundary;t+=H){
  const decisions=Object.fromEntries(Object.keys(data).map(symbol=>[symbol,combinationDecision(symbol,data[symbol].filter(r=>r.t+H<=t).slice(-170),t)]));
  const next=advanceOpportunities(state,decisions,t);
  const rows=next.selected.map(x=>signalRow(x.symbol,decisions[x.symbol],t));
  steps.push({state:next.state,decisions:Object.fromEntries(Object.entries(decisions).map(([k,d])=>[k,{side:d.side,confirmedAt:d.confirmedAt}])),signals:rows});
  state=next.state;
 }
 const committed=await checked(sb.rpc('plan_b_publish_opportunities',{p_expected:saved.payload.lastConfirmedAt,p_steps:steps}));
 return {ok:true,plan:'B',strategy_id:STANDARD.strategy_id,mode:committed?'published':'concurrent_worker_won',confirmed_at:new Date(state.lastConfirmedAt).toISOString(),recovered_hours:steps.length,results:steps.at(-1)?.signals.map(s=>({symbol:s.symbol,side:s.side,ok:true,stored:committed}))||[],orders_submitted:0};
}
