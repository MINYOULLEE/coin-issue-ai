import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import postgres from "https://deno.land/x/postgresjs@v3.4.5/mod.js";
import {createHmac} from "node:crypto";
import JSONBig from "npm:json-bigint@1.0.0";

const sql=postgres(Deno.env.get("SUPABASE_DB_URL")!,{prepare:false,max:1});
const INTERNAL=Deno.env.get("INTERNAL_TRADE_SECRET")||"";
const BASE="https://open-api.bingx.com";
const parse=JSONBig({storeAsString:true});
const ASSETS=new Set(["BTC","ETH","XRP","TRX","SOL"]);
const ACTIVE=new Set(["active","weakening"]);
const LEVERAGE=3,MAX_GROSS=2.24,STOP_PCT=.15;

function same(a:string,b:string){if(a.length!==b.length)return false;let x=0;for(let i=0;i<a.length;i++)x|=a.charCodeAt(i)^b.charCodeAt(i);return x===0}
function finite(v:unknown){const n=Number(v);if(!Number.isFinite(n))throw Error("invalid numeric response");return n}
function canonical(p:Record<string,unknown>){return Object.keys(p).sort().map(k=>`${k}=${p[k]}`).join("&")}
async function signed(key:string,secret:string,method:"GET"|"POST"|"DELETE",path:string,params:Record<string,unknown>={}){
 const all={...params,timestamp:Date.now()},q=canonical(all),sig=createHmac("sha256",secret).update(q).digest("hex");
 const r=await fetch(method==="POST"?BASE+path:`${BASE}${path}?${q}&signature=${sig}`,{method,headers:{"X-BX-APIKEY":key,...(method==="POST"?{"Content-Type":"application/x-www-form-urlencoded"}:{})},body:method==="POST"?`${q}&signature=${sig}`:undefined,signal:AbortSignal.timeout(10000)});
 const raw=await r.text(),j=parse.parse(raw||"{}");if(!r.ok||Number(j.code)!==0)throw Error(`BingX ${j.code??r.status}: ${j.msg??raw.slice(0,120)}`);return j.data;
}
function positionRows(v:any){return Array.isArray(v)?v:Array.isArray(v?.positions)?v.positions:[]}
function orderValue(v:any){return v?.order??v??{}}
function roundDown(v:number,p:number){const f=10**p;return Math.floor(v*f)/f}
function round(v:number,p:number){const f=10**p;return Math.round(v*f)/f}
async function credentials(accountId:string){const rows=await sql`select k.decrypted_secret api_key,s.decrypted_secret secret_key from public.managed_bingx_accounts a join vault.decrypted_secrets k on k.id=a.api_key_secret_id join vault.decrypted_secrets s on s.id=a.secret_key_secret_id where a.id=${accountId}::uuid`;if(!rows[0]?.api_key||!rows[0]?.secret_key)throw Error("Vault credentials missing");return rows[0]}
async function balance(key:string,secret:string){const raw=await signed(key,secret,"GET","/openApi/swap/v3/user/balance",{recvWindow:5000}),rows=Array.isArray(raw)?raw:Array.isArray(raw?.balance)?raw.balance:[raw?.balance||raw],u=rows.find((x:any)=>x?.asset==="USDT")||rows[0];return{equity:finite(u?.equity),available:finite(u?.availableMargin)}}
async function contract(key:string,secret:string,symbol:string){const raw=await signed(key,secret,"GET","/openApi/swap/v2/quote/contracts",{symbol}),rows=Array.isArray(raw)?raw:Array.isArray(raw?.contracts)?raw.contracts:[],x=rows.find((v:any)=>v.symbol===symbol)||rows[0];if(!x)throw Error("contract unavailable");return x}
async function confirmedOrder(key:string,secret:string,symbol:string,clientOrderId:string,raw:any){let o=orderValue(raw);if(o?.orderID||o?.orderId)return o;for(const ms of [150,300,700]){await new Promise(r=>setTimeout(r,ms));o=orderValue(await signed(key,secret,"GET","/openApi/swap/v2/trade/order",{symbol,clientOrderId,recvWindow:5000}));if(o?.orderID||o?.orderId)return o}throw Error("order confirmation unavailable")}

async function closeTrade(account:any,trade:any,key:string,secret:string,reason:string){
 const symbol=trade.symbol+"-USDT",positionSide=trade.side.toUpperCase(),closeSide=trade.side==="long"?"SELL":"BUY";
 const ps=positionRows(await signed(key,secret,"GET","/openApi/swap/v2/user/positions",{symbol,recvWindow:5000})),p=ps.find((x:any)=>String(x.positionSide)===positionSide),actual=Math.abs(Number(p?.positionAmt??p?.positionAmount??0));
 if(!(actual>0)){await sql`update public.managed_bingx_trades set status='closed',closed_at=now(),close_reason=${reason+" · 거래소 포지션 없음"},updated_at=now() where id=${trade.id}`;return}
 const client=`ma${String(account.id).replace(/-/g,"").slice(0,8)}c${trade.id}`.slice(0,40),raw=await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side:closeSide,positionSide,type:"MARKET",quantity:actual,clientOrderId:client,recvWindow:5000}),o=await confirmedOrder(key,secret,symbol,client,raw),price=finite(o.avgPrice||o.price||p?.markPrice),gross=(trade.side==="long"?1:-1)*(price-finite(trade.entry_price))*actual,fee=Math.abs(Number(o.commission??0))||((finite(trade.entry_price)+price)*actual*.0005),pnl=Number.isFinite(Number(o.profit))?Number(o.profit)-fee:gross-fee;
 try{const oo=await signed(key,secret,"GET","/openApi/swap/v2/trade/openOrders",{symbol,recvWindow:5000}),list=Array.isArray(oo)?oo:(oo?.orders||[]);for(const x of list.filter((v:any)=>String(v.positionSide)===positionSide&&String(v.type)==="STOP_MARKET"))await signed(key,secret,"DELETE","/openApi/swap/v2/trade/order",{symbol,orderId:x.orderId??x.orderID,recvWindow:5000})}catch{}
 await sql`update public.managed_bingx_trades set status='closed',quantity=${actual},close_price=${price},realized_pnl_usdt=${pnl},fee_usdt=${fee},closed_at=now(),close_reason=${reason},last_error=null,updated_at=now() where id=${trade.id}`;
}

async function enter(account:any,signal:any,key:string,secret:string){
 if(signal.signal_type!=="answer_mdd30"||!ASSETS.has(signal.symbol)||!ACTIVE.has(signal.status))return;
 const reserved=await sql`insert into public.managed_bingx_trades(account_id,assigned_plan,signal_id,symbol,side,status,leverage,created_at,updated_at) values(${account.id}::uuid,'A',${signal.id},${signal.symbol},${signal.side},'reserved',3,now(),now()) on conflict do nothing returning id`;
 if(!reserved[0])return;const id=reserved[0].id,symbol=signal.symbol+"-USDT",positionSide=signal.side.toUpperCase(),side=signal.side==="long"?"BUY":"SELL";
 try{
  const b=await balance(key,secret),peak=Math.max(Number(account.a_equity_peak_usdt||0),b.equity),dd=peak>0?(peak-b.equity)/peak:0;let guard=!!account.a_drawdown_guard_active;if(!guard&&dd>=.35)guard=true;else if(guard&&dd<=.175)guard=false;
  await sql`update public.managed_bingx_accounts set current_equity_usdt=${b.equity},a_equity_peak_usdt=${peak},a_drawdown_guard_active=${guard},last_synced_at=now(),last_error=null,updated_at=now() where id=${account.id}::uuid`;
  const open=await sql`select symbol,margin_usdt,quantity,entry_price,leverage from public.managed_bingx_trades where account_id=${account.id}::uuid and status='open'`,usedMargin=open.reduce((s:number,x:any)=>s+Number(x.margin_usdt||0),0),usedSymbol=open.filter((x:any)=>x.symbol===signal.symbol).reduce((s:number,x:any)=>s+Number(x.margin_usdt||0),0),usedGross=open.reduce((s:number,x:any)=>s+Number(x.quantity)*Number(x.entry_price),0),cfg=signal.entry_metrics?.strategy_config||{},base=finite(cfg.base_exposure_multiplier??finite(cfg.exposure_multiplier)/1.4),exposure=base*(guard?1.05:1.4),rawMargin=b.equity*exposure/LEVERAGE,margin=Math.min(rawMargin,b.equity*.8-usedMargin,b.equity*.6-usedSymbol,(b.equity*MAX_GROSS-usedGross)/LEVERAGE,b.available*.95);
  if(!(margin>0))throw Error("no margin headroom");const c=await contract(key,secret,symbol),qp=Number(c.quantityPrecision??3),pp=Number(c.pricePrecision??2),entry=finite(signal.entry_price),qty=roundDown(margin*LEVERAGE/entry,qp),minQty=Number(c.tradeMinQuantity??0),minUsdt=Number(c.tradeMinUSDT??2);if(!(qty>0)||qty<minQty||qty*entry<minUsdt)throw Error("below exchange minimum");
  const mode=await signed(key,secret,"GET","/openApi/swap/v1/positionSide/dual",{recvWindow:5000});if(String(mode?.dualSidePosition)!=="true")throw Error("hedge mode required");
  await signed(key,secret,"POST","/openApi/swap/v2/trade/marginType",{symbol,marginType:"ISOLATED",recvWindow:5000}).catch((e:any)=>{if(!/No need to change/i.test(String(e.message)))throw e});
  await signed(key,secret,"POST","/openApi/swap/v2/trade/leverage",{symbol,side:positionSide,leverage:LEVERAGE,recvWindow:5000});const client=`ma${String(account.id).replace(/-/g,"").slice(0,8)}e${signal.id}`.slice(0,40);
  await signed(key,secret,"POST","/openApi/swap/v2/trade/order/test",{symbol,side,positionSide,type:"MARKET",quantity:qty,clientOrderId:client.slice(0,36)+"t",recvWindow:5000});
  const o=await confirmedOrder(key,secret,symbol,client,await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side,positionSide,type:"MARKET",quantity:qty,clientOrderId:client,recvWindow:5000})),fill=finite(o.avgPrice||o.price||entry),actual=finite(o.executedQty||o.quantity||qty),stop=round(fill*(signal.side==="long"?1-STOP_PCT:1+STOP_PCT),pp),closeSide=signal.side==="long"?"SELL":"BUY";
  let stopOrder:any;try{stopOrder=orderValue(await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side:closeSide,positionSide,type:"STOP_MARKET",stopPrice:stop,quantity:actual,workingType:"MARK_PRICE",recvWindow:5000}))}catch(e){await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side:closeSide,positionSide,type:"MARKET",quantity:actual,recvWindow:5000}).catch(()=>{});throw Error("protective stop failed; safety close sent: "+String(e))}
  const notional=actual*fill;await sql`update public.managed_bingx_trades set status='open',quantity=${actual},leverage=3,margin_usdt=${notional/3},entry_price=${fill},stop_price=${stop},target_price=null,bingx_order_id=${String(o.orderID??o.orderId)},client_order_id=${client},stop_order_id=${String(stopOrder?.orderID??stopOrder?.orderId??"")},fee_usdt=${notional*.0005},opened_at=now(),last_error=null,updated_at=now() where id=${id}`;
 }catch(e){await sql`update public.managed_bingx_trades set status='rejected',last_error=${String(e).slice(0,500)},updated_at=now() where id=${id}`;throw e}
}

async function runAccount(account:any){const c=await credentials(account.id),key=String(c.api_key),secret=String(c.secret_key);try{
 if(!account.live_enabled_at){
  const[mode,positions,c]=await Promise.all([signed(key,secret,"GET","/openApi/swap/v1/positionSide/dual",{recvWindow:5000}),signed(key,secret,"GET","/openApi/swap/v2/user/positions",{recvWindow:5000}),contract(key,secret,"BTC-USDT")]);
  if(String(mode?.dualSidePosition)!=="true")throw Error("LIVE preflight: hedge mode required");if(positionRows(positions).some((p:any)=>Math.abs(Number(p.positionAmt??p.positionAmount??0))>0))throw Error("LIVE preflight: unmanaged position exists");
  const qty=Math.max(Number(c.tradeMinQuantity||0),roundDown(Number(c.tradeMinUSDT||2)/50000,Number(c.quantityPrecision??3)));if(!(qty>0))throw Error("LIVE preflight: contract minimum unavailable");
  await signed(key,secret,"POST","/openApi/swap/v2/trade/order/test",{symbol:"BTC-USDT",side:"BUY",positionSide:"LONG",type:"MARKET",quantity:qty,clientOrderId:("mapre"+String(account.id).replace(/-/g,"")).slice(0,32),recvWindow:5000});
  account.live_enabled_at=new Date().toISOString();await sql`update public.managed_bingx_accounts set live_enabled_at=${account.live_enabled_at},last_error=null,updated_at=now() where id=${account.id}::uuid`;
 }
 const b=await balance(key,secret);await sql`update public.managed_bingx_accounts set current_equity_usdt=${b.equity},a_equity_peak_usdt=greatest(coalesce(a_equity_peak_usdt,0),${b.equity}),status='connected',last_synced_at=now(),last_error=null,updated_at=now() where id=${account.id}::uuid`;
 const trades=await sql`select t.*,s.status signal_status,s.close_reason signal_close_reason from public.managed_bingx_trades t left join public.trade_signals s on s.id=t.signal_id where t.account_id=${account.id}::uuid and t.status='open' order by t.created_at`;
 for(const t of trades)if(!ACTIVE.has(String(t.signal_status)))await closeTrade(account,t,key,secret,String(t.signal_close_reason||"A플랜 신호 종료"));
 const signals=await sql`select id,symbol,side,signal_type,status,created_at,entry_price,invalidation_price,target_price,entry_metrics from public.trade_signals where signal_type='answer_mdd30' and status in ('active','weakening') and created_at>=${account.live_enabled_at} order by created_at`;
 for(const s of signals)await enter(account,s,key,secret);
 }catch(e){await sql`update public.managed_bingx_accounts set live_enabled=false,status='error',last_error=${String(e).slice(0,500)},last_synced_at=now(),updated_at=now() where id=${account.id}::uuid`;throw e}}

Deno.serve(async req=>{if(req.method!=="POST")return new Response("POST required",{status:405});if(!INTERNAL||!same(req.headers.get("x-internal-key")||"",INTERNAL))return new Response("forbidden",{status:403});const accounts=await sql`select * from public.managed_bingx_accounts where live_enabled and status in ('connected','error') order by created_at`,results=[];for(const a of accounts){if(a.assigned_plan!=="A"){results.push({id:a.id,ok:false,error:"B managed executor not deployed"});continue}try{await runAccount(a);results.push({id:a.id,ok:true})}catch(e){results.push({id:a.id,ok:false,error:String(e).slice(0,200)})}}return Response.json({ok:results.every(x=>x.ok),accounts:results});});
