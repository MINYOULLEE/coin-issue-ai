import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "https://esm.sh/@supabase/supabase-js@2.49.8";
import {createBExchange} from "../_shared/plan_b_exchange.mjs";
import standard from "../_shared/plan_b_standard.json" with {type:"json"};
import {runCombinationSignals} from "../_shared/plan_b_signal_cycle.mjs";
const sb=createClient(Deno.env.get("SUPABASE_URL")!,Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,{auth:{persistSession:false}});
Deno.serve(async req=>{
 if(req.method!=="POST")return Response.json({ok:false},{status:405});
 const key=req.headers.get('x-scheduler-key');if(!key)return Response.json({ok:false},{status:403});
 const {data,error}=await sb.from('private_runtime_secrets').select('secret_value').eq('id','scheduler_auth').single();
 if(error||key!==data?.secret_value?.key)return Response.json({ok:false},{status:403});
 try{
  const body=await req.json().catch(()=>({}));
  if(body.action==='backfill')return Response.json(await runCombinationSignals({sb,fetchCandles:async symbol=>{
   const r=await fetch(`https://api.binance.com/api/v3/klines?symbol=${symbol}USDT&interval=1h&limit=1000`,{signal:AbortSignal.timeout(10000)});
   if(!r.ok)throw Error('B backfill market data unavailable: '+symbol);
   const raw=await r.json();if(!Array.isArray(raw))throw Error('invalid backfill candles');
   return raw.map(x=>({t:+x[0],o:+x[1],h:+x[2],l:+x[3],c:+x[4],v:+x[5]}));
  }}));
  // No write authorizers supplied: even an accidental submit/configure call is denied.
  const bx=createBExchange({apiKey:Deno.env.get('PLAN_B_BINGX_API_KEY'),secret:Deno.env.get('PLAN_B_BINGX_SECRET_KEY')});
  const contracts=await bx.read('/openApi/swap/v2/quote/contracts',{}),results=[];
  for(const [symbol,rule] of Object.entries(standard.symbols)){
   const pair=symbol+'-USDT';
   try{
    const margin=await bx.read('/openApi/swap/v2/trade/marginType',{symbol:pair});
    const leverage=await bx.read('/openApi/swap/v2/trade/leverage',{symbol:pair});
    const contract=contracts.find(c=>c.symbol===pair);
    const ok=margin.marginType==='ISOLATED'&&Number(leverage.longLeverage)===rule.leverage&&Number(leverage.shortLeverage)===rule.leverage&&String(contract?.apiStateOpen)==='true'&&String(contract?.apiStateClose)==='true';
    results.push({symbol,ok,expected_leverage:rule.leverage,margin_type:margin.marginType,long_leverage:leverage.longLeverage,short_leverage:leverage.shortLeverage,min_quantity:contract?.tradeMinQuantity,min_notional:contract?.tradeMinUSDT});
   }catch(e){results.push({symbol,ok:false,error:String(e.message)});}
  }
  const mode=await bx.read('/openApi/swap/v1/positionSide/dual',{});
  return Response.json({ok:results.every(r=>r.ok)&&String(mode.dualSidePosition)==='true',plan:'B',mode:'read_only_stage35_preflight',hedge_mode:mode.dualSidePosition,results,orders_submitted:0});
 }catch(e){return Response.json({ok:false,plan:'B',error:String(e.message),orders_submitted:0},{status:503});}
});
