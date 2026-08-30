import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "https://esm.sh/@supabase/supabase-js@2.49.8";
import JSONBig from "npm:json-bigint@1.0.0";
import {createBExchange,constrainBQuantity} from "../_shared/plan_b_exchange.mjs";
import {allocatePlanB,PLAN_B_STANDARD as STANDARD} from "../_shared/plan_b_sizing.mjs";
const sb=createClient(Deno.env.get('SUPABASE_URL')!,Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,{auth:{persistSession:false}});
const delay=()=>new Promise(r=>setTimeout(r,550));
Deno.serve(async req=>{
 if(req.method!=='POST')return Response.json({ok:false},{status:405});
 try{
  const key=req.headers.get('x-scheduler-key');
  if(!key)return Response.json({ok:false},{status:403});
  const {data:auth,error:ae}=await sb.from('private_runtime_secrets').select('secret_value').eq('id','scheduler_auth').single();
  if(ae||key!==auth?.secret_value?.key)return Response.json({ok:false},{status:403});
  const body=await req.json().catch(()=>({}));
  if(body.action!=='preflight')return Response.json({ok:false,error:'only read-only preflight is available; no live activation'},{status:409});
  const bx=createBExchange({apiKey:Deno.env.get('PLAN_B_BINGX_API_KEY'),secret:Deno.env.get('PLAN_B_BINGX_SECRET_KEY'),parse:JSONBig({storeAsString:true}).parse});
  const {data:state,error}=await sb.from('plan_b_trading_state').select('*').eq('id','singleton').single();if(error)throw error;
  const blockers:string[]=[];
  if(state.strategy_id!==STANDARD.strategy_id)blockers.push('strategy_mismatch');
  const bal=await bx.read('/openApi/swap/v3/user/balance',{}),positions=await bx.read('/openApi/swap/v2/user/positions',{});
  const balances=Array.isArray(bal)?bal:Array.isArray(bal?.balance)?bal.balance:[bal?.balance||bal];
  const usdt=balances.find((b:any)=>b?.asset==='USDT');
  if(!usdt)throw Error('USDT account unavailable');
  const balance=Number(usdt.balance),equity=Number(usdt.equity),available=Number(usdt.availableMargin);
  if(![balance,equity,available].every(Number.isFinite))throw Error('invalid account numbers');
  if(available<=0)blockers.push('no_available_margin');
  if(equity<STANDARD.live_account.starting_capital_usd)blockers.push('equity_below_user_starting_capital');
  const open=(Array.isArray(positions)?positions:positions?.positions||[]).filter((p:any)=>Math.abs(Number(p.positionAmt??p.positionAmount))>0);
  const orders=await bx.read('/openApi/swap/v2/trade/openOrders',{});
  const pending=Array.isArray(orders)?orders:orders?.orders||[];
  const mode=await bx.read('/openApi/swap/v1/positionSide/dual',{});
  if(String(mode.dualSidePosition)!=='true')blockers.push('hedge_mode_required');
  if(open.length||pending.length)blockers.push('existing_positions_or_orders_require_reconciliation');
  const contracts=await bx.read('/openApi/swap/v2/quote/contracts',{});
  const marks=await bx.read('/openApi/swap/v2/quote/premiumIndex',{});
  const report:any[]=[];
  // All below are hypothetical sizing checks, not current trading signals.
  for(const symbol of Object.keys(STANDARD.symbols)){
   try{
    const pair=symbol+'-USDT',rule=(STANDARD.symbols as any)[symbol];
    const c=contracts.find((x:any)=>x.symbol===pair),m=marks.find((x:any)=>x.symbol===pair);
    if(!c||!m)throw Error('contract_or_mark_missing');
    const price=Number(m.markPrice);
    const allocation=allocatePlanB({plan:'B',strategyId:STANDARD.strategy_id,balance,equity,reservedMargin:0,proposals:[{symbol,entryPrice:price}]});
    const bounded=allocation.orders[0];
    // Exchange free margin is a second cap; preserve the cash buffer.
    const free=Math.max(0,available-equity*.05),shrink=bounded.requiredReservation>0?Math.min(1,free/bounded.requiredReservation):0;
    const margin=await bx.read('/openApi/swap/v2/trade/marginType',{symbol:pair});await delay();
    const leverage=await bx.read('/openApi/swap/v2/trade/leverage',{symbol:pair});await delay();
    const capabilities={...c,maxLongLeverage:leverage.maxLongLeverage,maxShortLeverage:leverage.maxShortLeverage};
    const sized=constrainBQuantity({...bounded,side:'long',quantity:bounded.quantity*shrink},capabilities,price);
    const local:string[]=[];
    if(margin.marginType!=='ISOLATED')local.push('isolated_margin_required');
    if(Number(leverage.longLeverage)!==rule.leverage||Number(leverage.shortLeverage)!==rule.leverage)local.push('leverage_mismatch');
    if(!Number.isFinite(Number(leverage.maxShortLeverage))||Number(leverage.maxShortLeverage)<rule.leverage)local.push('short_leverage_unavailable');
    report.push({symbol,ok:local.length===0,blockers:local,expected_leverage:rule.leverage,current_long:Number(leverage.longLeverage),current_short:Number(leverage.shortLeverage),margin_type:margin.marginType,mark_price:price,hypothetical_quantity:sized.quantity,min_quantity:c.tradeMinQuantity,min_notional:c.tradeMinUSDT});
   }catch(e){report.push({symbol,ok:false,blockers:[e instanceof Error?e.message:'preflight_failed']});}
  }
  return Response.json({ok:true,plan:'B',mode:'read_only_preflight',starting_capital_usd:150,balance,equity,available_margin:available,
    open_positions:open.length,pending_orders:pending.length,blockers,contracts:report,
    live_ready:false,orders_submitted:0,remaining:['execution_cycle_and_close_reconciliation_not_live_verified','maintenance_tier_validation']});
 }catch(e){return Response.json({ok:false,plan:'B',error:e instanceof Error?e.message:'preflight_failed',orders_submitted:0},{status:503});}
});
