import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import postgres from "https://deno.land/x/postgresjs@v3.4.5/mod.js";
import {createHmac} from "node:crypto";
import JSONBig from "npm:json-bigint@1.0.0";
import {closeManagedTrade,managedCloseSettlement} from "../_shared/managed_close.mjs";
import {copyDelta,copyKeys,normalizedPositions,positionKey,targetQuantity} from "../_shared/managed_position_copy.mjs";

const sql=postgres(Deno.env.get("SUPABASE_DB_URL")!,{prepare:false,max:1});
const INTERNAL=Deno.env.get("INTERNAL_TRADE_SECRET")||"";
const BASE="https://open-api.bingx.com";
const parse=JSONBig({storeAsString:true});
const ASSETS=new Set(["BTC","ETH","XRP","TRX","SOL"]);
const ACTIVE=new Set(["active","weakening"]);
const LEVERAGE=5,MAX_GROSS=56/15,STOP_PCT=.15;
const A_VERSION="mdd30_5x_c_controller_stage184_v1";
const CURRENT_PLAN_VERSIONS={A:A_VERSION,B:"b_regime_guard_stage112_v1"} as const;
const PLAN_ASSETS={A:new Set(["BTC","ETH","XRP","TRX","SOL"]),B:new Set(["AVAX","ICP","BCH","DOGE","UNI","ALGO","ETH","VET","LINK","DOT","LTC","BNB","ADA"])};

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
function sourceCredentials(plan:"A"|"B"){
 const api_key=Deno.env.get(plan==="A"?"BINGX_API_KEY":"PLAN_B_BINGX_API_KEY")||"",secret_key=Deno.env.get(plan==="A"?"BINGX_SECRET_KEY":"PLAN_B_BINGX_SECRET_KEY")||"";
 if(!api_key||!secret_key)throw Error(`${plan} source credentials missing`);
 return{api_key,secret_key};
}
async function balance(key:string,secret:string){const raw=await signed(key,secret,"GET","/openApi/swap/v3/user/balance",{recvWindow:5000}),rows=Array.isArray(raw)?raw:Array.isArray(raw?.balance)?raw.balance:[raw?.balance||raw],u=rows.find((x:any)=>x?.asset==="USDT")||rows[0];return{equity:finite(u?.equity),available:finite(u?.availableMargin)}}
async function contract(key:string,secret:string,symbol:string){const raw=await signed(key,secret,"GET","/openApi/swap/v2/quote/contracts",{symbol}),rows=Array.isArray(raw)?raw:Array.isArray(raw?.contracts)?raw.contracts:[],x=rows.find((v:any)=>v.symbol===symbol)||rows[0];if(!x)throw Error("contract unavailable");return x}
async function confirmedOrder(key:string,secret:string,symbol:string,clientOrderId:string,raw:any){let o=orderValue(raw);if(o?.orderID||o?.orderId)return o;for(const ms of [150,300,700]){await new Promise(r=>setTimeout(r,ms));o=orderValue(await signed(key,secret,"GET","/openApi/swap/v2/trade/order",{symbol,clientOrderId,recvWindow:5000}));if(o?.orderID||o?.orderId)return o}throw Error("order confirmation unavailable")}

async function alignStage184Leverage(account:any,trades:any[],key:string,secret:string){
 for(const trade of trades){
  const symbol=trade.symbol+"-USDT",positionSide=String(trade.side).toUpperCase();
  const positions=positionRows(await signed(key,secret,"GET","/openApi/swap/v2/user/positions",{symbol,recvWindow:5000}));
  const p=positions.find((x:any)=>String(x.symbol)===symbol&&String(x.positionSide)===positionSide);
  const actual=Math.abs(Number(p?.positionAmt??p?.positionAmount??0)),owned=finite(trade.quantity);
  if(!(actual>0))continue;
  if(actual>owned+1e-10){
   await sql`update public.managed_bingx_trades set last_error='manual same-side quantity present; Stage184 leverage alignment deferred',updated_at=now() where id=${trade.id}`;
   throw Error(`${trade.symbol} manual same-side quantity blocks leverage alignment`);
  }
  const exchangeLeverage=Number(p?.leverage??0);
  if(exchangeLeverage!==LEVERAGE)await signed(key,secret,"POST","/openApi/swap/v2/trade/leverage",{symbol,side:positionSide,leverage:LEVERAGE,recvWindow:5000});
  const mark=Number(p?.markPrice||trade.entry_price),notional=owned*(mark>0?mark:finite(trade.entry_price));
  await sql`update public.managed_bingx_trades set leverage=${LEVERAGE},margin_usdt=${notional/LEVERAGE},last_error=null,updated_at=now() where id=${trade.id}`;
 }
 await sql`update public.managed_bingx_accounts set desired_strategy_version=${A_VERSION},a_strategy_version=${A_VERSION},a_strategy_aligned_at=now(),applied_strategy_version=${A_VERSION},strategy_version_synced_at=now(),last_error=null,updated_at=now() where id=${account.id}::uuid`;
}

async function replaceStopAfterResize(account:any,trade:any,key:string,secret:string,quantity:number,entry:number,pricePrecision:number){
 const symbol=trade.symbol+"-USDT",positionSide=String(trade.side).toUpperCase(),closeSide=trade.side==="long"?"SELL":"BUY";
 if(trade.stop_order_id)try{await signed(key,secret,"DELETE","/openApi/swap/v2/trade/order",{symbol,orderId:trade.stop_order_id,recvWindow:5000})}catch{}
 const stop=round(entry*(trade.side==="long"?1-STOP_PCT:1+STOP_PCT),pricePrecision);
 try{
  const stopOrder=orderValue(await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side:closeSide,positionSide,type:"STOP_MARKET",stopPrice:stop,quantity,workingType:"MARK_PRICE",recvWindow:5000}));
  return{stop,stopOrderId:String(stopOrder?.orderID??stopOrder?.orderId??"")};
 }catch(e){
  await sql`update public.managed_bingx_trades set quantity=${quantity},entry_price=${entry},last_error=${String(e).slice(0,500)},updated_at=now() where id=${trade.id} and account_id=${account.id}::uuid`;
  await closeTrade(account,{...trade,quantity,entry_price:entry,stop_order_id:null},key,secret,'Stage184 resize stop failed; safety close sent');
  throw Error("Stage184 resize protective stop failed; safety close sent");
 }
}

async function rebalanceStage184(account:any,trades:any[],key:string,secret:string,equity:number,guard:boolean,decisionMs:number){
 if(!(decisionMs>0)||decisionMs<=Number(account.a_last_rebalance_closed_ms||0))return;
 for(const trade of trades){
  const cfg=trade.entry_metrics?.strategy_config||{},base=finite(cfg.base_exposure_multiplier??finite(cfg.exposure_multiplier)/(7/5));
  const symbol=trade.symbol+"-USDT",positionSide=String(trade.side).toUpperCase();
  const [positions,c]=await Promise.all([signed(key,secret,"GET","/openApi/swap/v2/user/positions",{symbol,recvWindow:5000}),contract(key,secret,symbol)]);
  const p=positionRows(positions).find((x:any)=>String(x.symbol)===symbol&&String(x.positionSide)===positionSide);
  const actual=Math.abs(Number(p?.positionAmt??p?.positionAmount??0)),owned=finite(trade.quantity),mark=finite(p?.markPrice||trade.entry_price);
  if(!(actual>0)||actual>owned+1e-10)throw Error(`${trade.symbol} manual same-side quantity blocks Stage184 resize`);
  const qp=Number(c.quantityPrecision??3),pp=Number(c.pricePrecision??2),target=roundDown(equity*base*(guard?.77:7/3)/mark,qp),delta=roundDown(Math.abs(target-owned),qp);
  const minQty=Number(c.tradeMinQuantity??0),minUsdt=Number(c.tradeMinUSDT??2),reduce=target<owned;
  const selective=(trade.symbol==="SOL"&&trade.side==="long"&&reduce)||(trade.symbol==="BTC"&&trade.side==="short"&&reduce);
  if(!(delta>0)||delta<minQty||delta*mark<minUsdt||(selective&&delta*mark<equity*.0125))continue;
  if(trade.stop_order_id)try{await signed(key,secret,"DELETE","/openApi/swap/v2/trade/order",{symbol,orderId:trade.stop_order_id,recvWindow:5000})}catch{}
  const side=reduce?(trade.side==="long"?"SELL":"BUY"):(trade.side==="long"?"BUY":"SELL");
  const client=`ma${String(account.id).replace(/-/g,"").slice(0,8)}r${trade.id}${decisionMs}`.slice(0,40);
  await signed(key,secret,"POST","/openApi/swap/v2/trade/order/test",{symbol,side,positionSide,type:"MARKET",quantity:delta,clientOrderId:client.slice(0,36)+"t",recvWindow:5000});
  await confirmedOrder(key,secret,symbol,client,await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side,positionSide,type:"MARKET",quantity:delta,clientOrderId:client,recvWindow:5000}));
  const afterRows=positionRows(await signed(key,secret,"GET","/openApi/swap/v2/user/positions",{symbol,recvWindow:5000})),after=afterRows.find((x:any)=>String(x.symbol)===symbol&&String(x.positionSide)===positionSide),newQty=Math.abs(finite(after?.positionAmt??after?.positionAmount??0)),newEntry=finite(after?.avgPrice||after?.entryPrice||trade.entry_price);
  if(!(newQty>0))throw Error("Stage184 resize position verification failed");
  const protection=await replaceStopAfterResize(account,trade,key,secret,newQty,newEntry,pp);
  await sql`update public.managed_bingx_trades set quantity=${newQty},leverage=${LEVERAGE},margin_usdt=${newQty*mark/LEVERAGE},entry_price=${newEntry},stop_price=${protection.stop},stop_order_id=${protection.stopOrderId},last_error=null,updated_at=now() where id=${trade.id}`;
 }
 await sql`update public.managed_bingx_accounts set a_last_rebalance_closed_ms=${decisionMs},desired_strategy_version=${A_VERSION},a_strategy_version=${A_VERSION},a_strategy_aligned_at=now(),applied_strategy_version=${A_VERSION},strategy_version_synced_at=now(),last_error=null,updated_at=now() where id=${account.id}::uuid`;
}

async function closeTrade(account:any,trade:any,key:string,secret:string,reason:string){
 const symbol=trade.symbol+"-USDT",positionSide=trade.side.toUpperCase(),closeSide=trade.side==="long"?"SELL":"BUY";
 await closeManagedTrade({trade,
  position:async()=>{
   const raw=await signed(key,secret,"GET","/openApi/swap/v2/user/positions",{symbol,recvWindow:5000});
   if(!Array.isArray(raw)&&!Array.isArray(raw?.positions))throw Error("invalid position response");
   return positionRows(raw).filter((p:any)=>p.symbol===symbol&&p.positionSide===positionSide).reduce((n:number,p:any)=>n+Math.abs(finite(p.positionAmt??p.positionAmount)),0);
  },
  lookup:async(clientOrderId:string)=>orderValue(await signed(key,secret,"GET","/openApi/swap/v2/trade/order",{symbol,clientOrderId,startTs:Number(trade.close_context?.submittedAt||Date.now()-3600000)-120000,endTs:Date.now(),recvWindow:5000})),
  submit:async(clientOrderId:string,quantity:number)=>signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side:closeSide,positionSide,type:"MARKET",quantity,clientOrderId,recvWindow:5000}),
  cancelStop:async()=>{if(trade.stop_order_id){
   const raw=await signed(key,secret,"GET","/openApi/swap/v2/trade/openOrders",{symbol,recvWindow:5000}),rows=Array.isArray(raw)?raw:raw?.orders;
   if(!Array.isArray(rows))throw Error('invalid protective order response');
   if(rows.some((o:any)=>String(o.orderId??o.orderID)===String(trade.stop_order_id)))await signed(key,secret,"DELETE","/openApi/swap/v2/trade/order",{symbol,orderId:trade.stop_order_id,recvWindow:5000});
  }},
  claim:async(previous:any,next:any)=>{
   const rows=await sql`update public.managed_bingx_trades set status='closing',close_context=${JSON.stringify(next)}::jsonb,close_reason=${reason},updated_at=now()
    where id=${trade.id} and account_id=${account.id}::uuid and status in ('open','closing') and close_context is not distinct from ${previous?JSON.stringify(previous):null}::jsonb returning id`;
   return rows.length===1;
  },
  save:async(message:string)=>{await sql`update public.managed_bingx_trades set last_error=${message},updated_at=now() where id=${trade.id} and account_id=${account.id}::uuid`},
  finish:async()=>{await sql`update public.managed_bingx_trades set status='closed',close_price=null,realized_pnl_usdt=null,closed_at=now(),close_reason=${reason},last_error='settlement pending exchange history',updated_at=now() where id=${trade.id} and account_id=${account.id}::uuid`}
 });
}

async function enter(account:any,signal:any,key:string,secret:string){
 if(signal.signal_type!=="answer_mdd30"||!ASSETS.has(signal.symbol)||!ACTIVE.has(signal.status))return;
 const pair=signal.symbol+"-USDT",posSide=signal.side.toUpperCase(),live=positionRows(await signed(key,secret,"GET","/openApi/swap/v2/user/positions",{symbol:pair,recvWindow:5000})),liveQty=live.filter((p:any)=>String(p.symbol)===pair&&String(p.positionSide)===posSide).reduce((n:number,p:any)=>n+Math.abs(finite(p.positionAmt??p.positionAmount??0)),0),ownedRows=await sql`select quantity from public.managed_bingx_trades where account_id=${account.id}::uuid and symbol=${signal.symbol} and side=${signal.side} and status='open'`,ownedQty=ownedRows.reduce((n:number,t:any)=>n+Number(t.quantity||0),0);
 if(liveQty>ownedQty+1e-10){await sql`insert into public.managed_bingx_trades(account_id,assigned_plan,signal_id,symbol,side,status,last_error,created_at,updated_at) values(${account.id}::uuid,'A',${signal.id},${signal.symbol},${signal.side},'rejected','수동 포지션과 동일 종목·방향 중첩 · 자동 진입 차단',now(),now()) on conflict do nothing`;return}
 const reserved=await sql`insert into public.managed_bingx_trades(account_id,assigned_plan,signal_id,symbol,side,status,leverage,created_at,updated_at) values(${account.id}::uuid,'A',${signal.id},${signal.symbol},${signal.side},'reserved',${LEVERAGE},now(),now()) on conflict do nothing returning id`;
 if(!reserved[0])return;const id=reserved[0].id,symbol=signal.symbol+"-USDT",positionSide=signal.side.toUpperCase(),side=signal.side==="long"?"BUY":"SELL";
 try{
  const b=await balance(key,secret),peak=Math.max(Number(account.a_equity_peak_usdt||0),b.equity),dd=peak>0?(peak-b.equity)/peak:0;let guard=!!account.a_drawdown_guard_active;if(!guard&&dd>=.225)guard=true;else if(guard&&dd<=.10125)guard=false;
  await sql`update public.managed_bingx_accounts set current_equity_usdt=${b.equity},a_equity_peak_usdt=${peak},a_drawdown_guard_active=${guard},last_synced_at=now(),last_error=null,updated_at=now() where id=${account.id}::uuid`;
  const open=await sql`select symbol,margin_usdt,quantity,entry_price,leverage from public.managed_bingx_trades where account_id=${account.id}::uuid and status='open'`,usedMargin=open.reduce((s:number,x:any)=>s+Number(x.margin_usdt||0),0),usedSymbol=open.filter((x:any)=>x.symbol===signal.symbol).reduce((s:number,x:any)=>s+Number(x.margin_usdt||0),0),usedGross=open.reduce((s:number,x:any)=>s+Number(x.quantity)*Number(x.entry_price),0),cfg=signal.entry_metrics?.strategy_config||{},base=finite(cfg.base_exposure_multiplier??finite(cfg.exposure_multiplier)/(7/3)),exposure=base*(guard?.77:7/3),rawMargin=b.equity*exposure/LEVERAGE,margin=Math.min(rawMargin,b.equity*.8-usedMargin,b.equity*.6-usedSymbol,(b.equity*MAX_GROSS-usedGross)/LEVERAGE,b.available*.95);
  if(!(margin>0))throw Error("no margin headroom");const c=await contract(key,secret,symbol),qp=Number(c.quantityPrecision??3),pp=Number(c.pricePrecision??2),entry=finite(signal.entry_price),qty=roundDown(margin*LEVERAGE/entry,qp),minQty=Number(c.tradeMinQuantity??0),minUsdt=Number(c.tradeMinUSDT??2);if(!(qty>0)||qty<minQty||qty*entry<minUsdt)throw Error("below exchange minimum");
  const mode=await signed(key,secret,"GET","/openApi/swap/v1/positionSide/dual",{recvWindow:5000});if(String(mode?.dualSidePosition)!=="true")throw Error("hedge mode required");
  await signed(key,secret,"POST","/openApi/swap/v2/trade/marginType",{symbol,marginType:"ISOLATED",recvWindow:5000}).catch((e:any)=>{if(!/No need to change/i.test(String(e.message)))throw e});
  await signed(key,secret,"POST","/openApi/swap/v2/trade/leverage",{symbol,side:positionSide,leverage:LEVERAGE,recvWindow:5000});const client=`ma${String(account.id).replace(/-/g,"").slice(0,8)}e${signal.id}`.slice(0,40);
  await signed(key,secret,"POST","/openApi/swap/v2/trade/order/test",{symbol,side,positionSide,type:"MARKET",quantity:qty,clientOrderId:client.slice(0,36)+"t",recvWindow:5000});
  const o=await confirmedOrder(key,secret,symbol,client,await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side,positionSide,type:"MARKET",quantity:qty,clientOrderId:client,recvWindow:5000})),fill=finite(o.avgPrice||o.price||entry),actual=finite(o.executedQty||o.quantity||qty),stop=round(fill*(signal.side==="long"?1-STOP_PCT:1+STOP_PCT),pp),closeSide=signal.side==="long"?"SELL":"BUY";
  let stopOrder:any;try{stopOrder=orderValue(await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side:closeSide,positionSide,type:"STOP_MARKET",stopPrice:stop,quantity:actual,workingType:"MARK_PRICE",recvWindow:5000}))}catch(e){await signed(key,secret,"POST","/openApi/swap/v2/trade/order",{symbol,side:closeSide,positionSide,type:"MARKET",quantity:actual,recvWindow:5000}).catch(()=>{});throw Error("protective stop failed; safety close sent: "+String(e))}
  const notional=actual*fill;await sql`update public.managed_bingx_trades set status='open',quantity=${actual},leverage=${LEVERAGE},margin_usdt=${notional/LEVERAGE},entry_price=${fill},stop_price=${stop},target_price=null,bingx_order_id=${String(o.orderID??o.orderId)},client_order_id=${client},stop_order_id=${String(stopOrder?.orderID??stopOrder?.orderId??"")},fee_usdt=${notional*.0005},opened_at=now(),last_error=null,updated_at=now() where id=${id}`;
 }catch(e){await sql`update public.managed_bingx_trades set status='rejected',last_error=${String(e).slice(0,500)},updated_at=now() where id=${id}`;throw e}
}

async function settleManagedCloses(account:any,key:string,secret:string){
 const trades=await sql`select * from public.managed_bingx_trades where account_id=${account.id}::uuid and status='closed' and realized_pnl_usdt is null and close_reason is not null order by closed_at limit 100`;
 for(const trade of trades)try{
  const start=Date.parse(trade.opened_at);if(!Number.isFinite(start))continue;
  const raw=await signed(key,secret,"GET","/openApi/swap/v1/trade/positionHistory",{symbol:trade.symbol+'-USDT',startTs:start-120000,endTs:Date.now(),page:1,limit:100});
  const settled=managedCloseSettlement(raw,trade);if(!settled)continue;
  await sql`update public.managed_bingx_trades set close_price=${settled.price},realized_pnl_usdt=${settled.net},fee_usdt=coalesce(${settled.fee},fee_usdt),closed_at=${settled.closedAt},last_error=null,updated_at=now() where id=${trade.id} and account_id=${account.id}::uuid and status='closed' and realized_pnl_usdt is null`;
 }catch(e){console.error('managed settlement lookup pending',String(e).slice(0,200))}
}

async function sourceMarker(plan:"A"|"B",position:any){
 const symbol=String(position.symbol).replace("-USDT","").toUpperCase(),side=String(position.side).toLowerCase();
 if(plan==="A"){
  const actual=Number(position.quantity),rows=await sql`select coalesce(sum(quantity),0) quantity from public.real_trades where symbol=${symbol} and side=${side} and status='open' and test_mode=false`;
  return Math.abs(Number(rows[0]?.quantity||0)-actual)>1e-10?2:1;
 }
 const rows=await sql`select quantity,control_marker from public.plan_b_real_trades where symbol=${symbol} and side=${side} and status='open' order by created_at desc limit 1`;
 return !rows[0]||Math.abs(Number(rows[0].quantity||0)-Number(position.quantity))>1e-10||Number(rows[0].control_marker)===2?2:1;
}

async function saveCopiedPosition(account:any,position:any,marker:number,clientOrderId:string|null){
 const symbol=String(position.symbol).replace("-USDT","").toUpperCase(),side=String(position.side).toLowerCase();
 const current=await sql`select id,control_marker from public.managed_bingx_trades where account_id=${account.id}::uuid and symbol=${symbol} and side=${side} and status in ('open','closing') order by created_at desc limit 1`;
 const quantity=Number(position.quantity),entry=Number(position.entryPrice),leverage=Number(position.leverage),margin=quantity*entry/leverage,control=Math.max(marker,Number(current[0]?.control_marker||1));
 if(current[0])await sql`update public.managed_bingx_trades set assigned_plan=${account.assigned_plan},status='open',quantity=${quantity},leverage=${leverage},margin_usdt=${margin},entry_price=${entry},control_marker=${control},client_order_id=coalesce(${clientOrderId},client_order_id),stop_order_id=null,last_error=null,updated_at=now() where id=${current[0].id} and account_id=${account.id}::uuid`;
 else await sql`insert into public.managed_bingx_trades(account_id,assigned_plan,symbol,side,status,quantity,leverage,margin_usdt,entry_price,control_marker,client_order_id,opened_at,created_at,updated_at) values(${account.id}::uuid,${account.assigned_plan},${symbol},${side},'open',${quantity},${leverage},${margin},${entry},${control},${clientOrderId},now(),now(),now())`;
}

async function closeCopiedLedger(account:any,symbol:string,side:string,marker:number){
 await sql`update public.managed_bingx_trades set status='closed',control_marker=greatest(control_marker,${marker}),closed_at=now(),close_reason='선택 플랜 실제 계정 포지션 동기화',last_error='settlement pending exchange history',stop_order_id=null,updated_at=now() where account_id=${account.id}::uuid and symbol=${symbol.replace("-USDT","")} and side=${side.toLowerCase()} and status in ('open','closing')`;
}

async function runCopyAccount(account:any){
 const plan=String(account.assigned_plan).toUpperCase() as "A"|"B",allowed=PLAN_ASSETS[plan];if(!allowed)throw Error("invalid assigned plan");
 const follower=await credentials(account.id),source=sourceCredentials(plan);
 const [sourceBalance,sourceRaw,followerBalance,followerRaw]=await Promise.all([balance(source.api_key,source.secret_key),signed(source.api_key,source.secret_key,"GET","/openApi/swap/v2/user/positions",{recvWindow:5000}),balance(follower.api_key,follower.secret_key),signed(follower.api_key,follower.secret_key,"GET","/openApi/swap/v2/user/positions",{recvWindow:5000})]);
 const sourcePositions=normalizedPositions(sourceRaw).filter(p=>allowed.has(p.symbol.replace("-USDT",""))),followerPositions=normalizedPositions(followerRaw),sourceMap=new Map(sourcePositions.map(p=>[positionKey(p.symbol,p.side),p])),followerMap=new Map(followerPositions.map(p=>[positionKey(p.symbol,p.side),p]));
 const openLedger=await sql`select symbol,side from public.managed_bingx_trades where account_id=${account.id}::uuid and status in ('open','closing')`;
 const keys=copyKeys(sourcePositions,followerPositions,openLedger);
 for(const key of keys){
  const sourcePosition=sourceMap.get(key),actual=followerMap.get(key),symbol=sourcePosition?.symbol||actual?.symbol||"",side=sourcePosition?.side||actual?.side||"";
  if(!allowed.has(symbol.replace("-USDT","")))continue;
  const c=await contract(follower.api_key,follower.secret_key,symbol),precision=Number(c.quantityPrecision??3),mark=Number(actual?.markPrice||sourcePosition?.markPrice||sourcePosition?.entryPrice||0),target=sourcePosition?targetQuantity(sourcePosition.quantity,sourceBalance.equity,followerBalance.equity,precision):0,delta=copyDelta(actual?.quantity||0,target,precision,Number(c.tradeMinQuantity||0),Number(c.tradeMinUSDT||2),mark);
  const marker=sourcePosition?await sourceMarker(plan,sourcePosition):1;
  const ledger=await sql`select id,quantity,entry_price,stop_order_id,control_marker from public.managed_bingx_trades where account_id=${account.id}::uuid and symbol=${symbol.replace("-USDT","")} and side=${side.toLowerCase()} and status in ('open','closing') order by created_at desc limit 1`;
  const followerManual=actual&&ledger[0]&&(Math.abs(Number(ledger[0].quantity||0)-actual.quantity)>10**(-precision)/2||Math.abs(Number(ledger[0].entry_price||0)-actual.entryPrice)>Math.max(.00000001,actual.entryPrice*1e-8));
  const effectiveMarker=followerManual?2:marker;
  if(delta){
   if(ledger[0]?.stop_order_id)await signed(follower.api_key,follower.secret_key,"DELETE","/openApi/swap/v2/trade/order",{symbol,orderId:ledger[0].stop_order_id,recvWindow:5000}).catch(()=>{});
   await signed(follower.api_key,follower.secret_key,"POST","/openApi/swap/v2/trade/marginType",{symbol,marginType:"ISOLATED",recvWindow:5000}).catch((e:any)=>{if(!/No need to change/i.test(String(e.message)))throw e});
   const leverage=Math.max(1,Math.round(Number(sourcePosition?.leverage||actual?.leverage||1)));await signed(follower.api_key,follower.secret_key,"POST","/openApi/swap/v2/trade/leverage",{symbol,side,leverage,recvWindow:5000});
   const orderSide=side==="LONG"?(delta.reduce?"SELL":"BUY"):(delta.reduce?"BUY":"SELL"),client=`cp${String(account.id).replace(/-/g,"").slice(0,8)}${Date.now().toString(36)}`.slice(0,40),params:any={symbol,side:orderSide,positionSide:side,type:"MARKET",quantity:delta.quantity,clientOrderId:client,recvWindow:5000};
   await signed(follower.api_key,follower.secret_key,"POST","/openApi/swap/v2/trade/order/test",params);await confirmedOrder(follower.api_key,follower.secret_key,symbol,client,await signed(follower.api_key,follower.secret_key,"POST","/openApi/swap/v2/trade/order",params));
   const after=normalizedPositions(await signed(follower.api_key,follower.secret_key,"GET","/openApi/swap/v2/user/positions",{symbol,recvWindow:5000})).find(p=>positionKey(p.symbol,p.side)===key);
   if(after)await saveCopiedPosition(account,after,effectiveMarker,client);else await closeCopiedLedger(account,symbol,side,effectiveMarker);
  }else if(actual)await saveCopiedPosition(account,actual,effectiveMarker,null);else await closeCopiedLedger(account,symbol,side,effectiveMarker);
 }
 await settleManagedCloses(account,follower.api_key,follower.secret_key);
 await sql`update public.managed_bingx_accounts set current_equity_usdt=${followerBalance.equity},status='connected',last_synced_at=now(),last_error=null,desired_strategy_version=${CURRENT_PLAN_VERSIONS[plan]},applied_strategy_version=${CURRENT_PLAN_VERSIONS[plan]},strategy_version_synced_at=now(),updated_at=now() where id=${account.id}::uuid`;
}

async function runAccount(account:any){const c=await credentials(account.id),key=String(c.api_key),secret=String(c.secret_key);try{
 if(!account.live_enabled_at){
  const[mode,positions,c]=await Promise.all([signed(key,secret,"GET","/openApi/swap/v1/positionSide/dual",{recvWindow:5000}),signed(key,secret,"GET","/openApi/swap/v2/user/positions",{recvWindow:5000}),contract(key,secret,"BTC-USDT")]);
  if(String(mode?.dualSidePosition)!=="true")throw Error("LIVE preflight: hedge mode required");if(positionRows(positions).some((p:any)=>Math.abs(Number(p.positionAmt??p.positionAmount??0))>0))throw Error("LIVE preflight: unmanaged position exists");
  const qty=Math.max(Number(c.tradeMinQuantity||0),roundDown(Number(c.tradeMinUSDT||2)/50000,Number(c.quantityPrecision??3)));if(!(qty>0))throw Error("LIVE preflight: contract minimum unavailable");
  await signed(key,secret,"POST","/openApi/swap/v2/trade/order/test",{symbol:"BTC-USDT",side:"BUY",positionSide:"LONG",type:"MARKET",quantity:qty,clientOrderId:("mapre"+String(account.id).replace(/-/g,"")).slice(0,32),recvWindow:5000});
  account.live_enabled_at=new Date().toISOString();await sql`update public.managed_bingx_accounts set live_enabled_at=${account.live_enabled_at},last_error=null,updated_at=now() where id=${account.id}::uuid`;
 }
 const b=await balance(key,secret),peak=Math.max(Number(account.a_equity_peak_usdt||0),b.equity),dd=peak>0?(peak-b.equity)/peak:0;let guard=!!account.a_drawdown_guard_active;if(!guard&&dd>=.225)guard=true;else if(guard&&dd<=.10125)guard=false;
 await sql`update public.managed_bingx_accounts set current_equity_usdt=${b.equity},a_equity_peak_usdt=${peak},a_drawdown_guard_active=${guard},status='connected',last_synced_at=now(),last_error=null,updated_at=now() where id=${account.id}::uuid`;
 const trades=await sql`select t.*,s.status signal_status,s.close_reason signal_close_reason,s.entry_metrics from public.managed_bingx_trades t left join public.trade_signals s on s.id=t.signal_id where t.account_id=${account.id}::uuid and t.status in ('open','closing') order by t.created_at`;
 for(const t of trades)if(t.status==='closing'||!ACTIVE.has(String(t.signal_status)))await closeTrade(account,t,key,secret,String(t.signal_close_reason||"A플랜 신호 종료"));
 const surviving=trades.filter((t:any)=>t.status==='open'&&ACTIVE.has(String(t.signal_status)));
 await alignStage184Leverage(account,surviving,key,secret);
 const decision=await sql`select case when payload #>> '{signal_candidates,hourly_audit,status}'='completed' then coalesce((extract(epoch from ((payload #>> '{signal_candidates,hourly_audit,closed_at}')::timestamptz))*1000)::bigint,0) else 0 end closed_ms from public.coin_snapshots where id='live'`;
 await rebalanceStage184(account,surviving,key,secret,b.equity,guard,Number(decision[0]?.closed_ms||0));
 const signals=await sql`select id,symbol,side,signal_type,status,created_at,entry_price,invalidation_price,target_price,entry_metrics from public.trade_signals where signal_type='answer_mdd30' and status in ('active','weakening') and created_at>=${account.live_enabled_at} order by created_at`;
 for(const s of signals)await enter(account,s,key,secret);
 await settleManagedCloses(account,key,secret);
 }catch(e){await sql`update public.managed_bingx_accounts set status='error',last_error=${String(e).slice(0,500)},last_synced_at=now(),updated_at=now() where id=${account.id}::uuid`;throw e}}

Deno.serve(async req=>{if(req.method!=="POST")return new Response("POST required",{status:405});if(!INTERNAL||!same(req.headers.get("x-internal-key")||"",INTERNAL))return new Response("forbidden",{status:403});await sql`update public.managed_bingx_accounts set desired_strategy_version=case assigned_plan when 'A' then ${CURRENT_PLAN_VERSIONS.A} when 'B' then ${CURRENT_PLAN_VERSIONS.B} end,updated_at=now() where desired_strategy_version is distinct from case assigned_plan when 'A' then ${CURRENT_PLAN_VERSIONS.A} when 'B' then ${CURRENT_PLAN_VERSIONS.B} end`;const accounts=await sql`select * from public.managed_bingx_accounts where live_enabled and status in ('connected','error') order by created_at`,results=[];for(const a of accounts)try{await runCopyAccount(a);results.push({id:a.id,ok:true,desired_version:CURRENT_PLAN_VERSIONS[a.assigned_plan as "A"|"B"],applied_version:CURRENT_PLAN_VERSIONS[a.assigned_plan as "A"|"B"]})}catch(e){await sql`update public.managed_bingx_accounts set status='error',last_error=${String(e).slice(0,500)},last_synced_at=now(),updated_at=now() where id=${a.id}::uuid`;results.push({id:a.id,ok:false,error:String(e).slice(0,200)})}return Response.json({ok:results.every(x=>x.ok),mode:'owner_position_copy',plan_versions:CURRENT_PLAN_VERSIONS,accounts:results});});
