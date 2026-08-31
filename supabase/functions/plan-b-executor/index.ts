import {outcomeErrors} from "../_shared/operational_health.mjs";
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "https://esm.sh/@supabase/supabase-js@2.49.8";
import JSONBig from "npm:json-bigint@1.0.0";
import {createBExchange} from "../_shared/plan_b_exchange.mjs";
import {checked,executeBatch,reconcileEntries,closeDue} from "../_shared/plan_b_live_cycle.mjs";
import runtime from "../_shared/plan_b_runtime.json" with {type:"json"};
import standard from "../_shared/plan_b_standard.json" with {type:"json"};
const sb=createClient(Deno.env.get("SUPABASE_URL")!,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});
Deno.serve(async req=>{
 if(req.method!=="POST")return Response.json({ok:false},{status:405});
 try{
  const key=req.headers.get("x-scheduler-key");if(!key)return Response.json({ok:false},{status:403});
  const secret=await checked(sb.from("private_runtime_secrets").select("secret_value").eq("id","scheduler_auth").single());
  if(key!==secret?.secret_value?.key)return Response.json({ok:false},{status:403});
  const body=await req.json();
  const state=()=>checked(sb.from("plan_b_trading_state").select("*").eq("id","singleton").single());
  const bx=createBExchange({apiKey:Deno.env.get("PLAN_B_BINGX_API_KEY"),secret:Deno.env.get("PLAN_B_BINGX_SECRET_KEY"),parse:JSONBig({storeAsString:true}).parse,
   liveAuthorized:async()=>{const s=await state();return s.strategy_id===runtime.strategy_id&&s.enabled===true&&s.test_mode===false;},
   exitAuthorized:async()=>{const s=await state();return s.strategy_id===runtime.strategy_id;},
   configurationAuthorized:async()=>{
    if(body.action!=="align_leverage"||body.confirm!=="align_only_no_orders"||runtime.live_ready)return false;
    const s=await state();if(s.strategy_id!==runtime.strategy_id)return false;
    const pending=await checked(sb.from("plan_b_execution_intents").select("id").not("status","in","(closed,failed,expired,rejected)"));
    const trades=await checked(sb.from("plan_b_real_trades").select("id").eq("status","open"));
    return pending.length===0&&trades.length===0;
   }});
  if(body.action==="align_leverage")return Response.json({ok:true,plan:"B",mode:"configuration_only",result:await bx.alignLeverage(body.symbol)});
  if(body.action==="inspect_configuration"){
   if(!Object.hasOwn(standard.symbols,body.symbol))return Response.json({ok:false},{status:400});
   const symbol=body.symbol+"-USDT";
   const positions=await bx.read('/openApi/swap/v2/user/positions',{symbol});
   const orders=await bx.read('/openApi/swap/v2/trade/openOrders',{symbol});
   const leverage=await bx.read('/openApi/swap/v2/trade/leverage',{symbol});
   return Response.json({ok:true,plan:"B",positions,orders,leverage,orders_submitted:0});
  }
  if(body.action==="preflight"){
   const s=await state(),contracts=[];
   for(const symbol of Object.keys(standard.symbols)){
    const expected=standard.symbols[symbol].leverage;
    try{await bx.verifyConfiguration(symbol,expected);contracts.push({symbol,ok:true});}catch(e){contracts.push({symbol,ok:false,error:String(e.message)});}
    await new Promise(resolve=>setTimeout(resolve,1200));
   }
   return Response.json({ok:contracts.every(c=>c.ok),plan:"B",mode:"read_only_preflight",runtime,enabled:s.enabled,test_mode:s.test_mode,contracts,orders_submitted:0});
  }
  if(!["execute","close"].includes(body.action))return Response.json({ok:false,error:"unknown action"},{status:400});
  if(body.action==="execute"&&!runtime.live_ready)return Response.json({ok:true,plan:"B",mode:"entry_locked",processed:0});
  // Recovery performs only lookups; no blind resubmission after a timeout.
  const recoveryErrors=await reconcileEntries({sb,bx});
  // Finish scheduled exits before considering any new group. Never extend the signal TTL.
  const exits=body.action==="execute"?await closeDue({sb,bx}):null;
  // Keep exit management running; incomplete recovery must not be reported as success.
  const result=body.action==="execute"?(recoveryErrors.length||exits?.ok===false?{mode:"reconciliation_required",processed:0,errors:outcomeErrors(exits)}:await executeBatch({sb,bx})):await closeDue({sb,bx});
  if(recoveryErrors.length){
   console.error("B entry recovery errors",JSON.stringify(recoveryErrors));
   const logged=await sb.from("system_errors").insert({source:"plan-b-entry-recovery",status_code:503,message:JSON.stringify(recoveryErrors).slice(0,1500),fingerprint:"plan-b-entry-recovery-"+new Date().toISOString().slice(0,16)});
   if(logged.error)console.error("B recovery error log failed",logged.error.message);
  }
  const errors=[...recoveryErrors,...outcomeErrors(result)];
  const outcome={plan:"B",execution_version:runtime.execution_version,...result,ok:!errors.length&&result.ok!==false,recovery_errors:recoveryErrors,errors};
  await checked(sb.from("plan_b_runtime_health").upsert({id:body.action,payload:outcome,updated_at:new Date().toISOString()}));
  return Response.json(outcome,{status:outcome.ok?200:503});
 }catch(e){console.error("B cycle failed",String(e.message));return Response.json({ok:false,plan:"B",error:String(e.message)},{status:503});}
});
