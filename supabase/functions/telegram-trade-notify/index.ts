import {healthProblems,healthTransitions,transportErrorDisposition} from "../_shared/operational_health.mjs";
import {stableHealthAlerts} from "../_shared/news_alert_stability.mjs";
import {webhookSecret} from "../_shared/telegram_webhook_auth.mjs";
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.8";

const URL=Deno.env.get("SUPABASE_URL")!;
const SERVICE=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const BOT=Deno.env.get("TELEGRAM_BOT_TOKEN")||"";
const CHAT="6818439075";
const COIN_ISSUE_URL="https://minyoullee.github.io/coin-issue-ai/";
const MDD30_STANDARD="MDD30 최종 기준 · 5개 독립 트리";
const sb=createClient(URL,SERVICE);
// Kept identical to telegram-bot-webhook's keyboard on purpose -- this function used to
// carry its own older/different keyboard, so every automated notification it sent would
// silently reset the user's menu back to that stale version. Simplified to 6 buttons.
const keyboard={keyboard:[["🔵 A 현황","🟣 B 현황"],["🔵 A 기록","🟣 B 기록"],["🔗 대시보드","❓ 도움말"]],resize_keyboard:true,is_persistent:true};

async function tg(method:string,body:any={}){if(!BOT)throw new Error("TELEGRAM_BOT_TOKEN missing");const r=await fetch(`https://api.telegram.org/bot${BOT}/${method}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const j=await r.json();if(!j.ok)throw new Error(`Telegram ${j.error_code}: ${j.description}`);return j.result}
async function send(text:string){return tg("sendMessage",{chat_id:CHAT,text,disable_web_page_preview:true,reply_markup:keyboard})}
function num(v:any,d=2){const x=Number(v);return Number.isFinite(x)?x.toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d}):"-"}
function side(v:string){return String(v).toLowerCase()==="long"?"LONG 🟢":"SHORT 🔴"}
function price(v:any){if(v==null||v==="")return "-";const x=Number(v);if(!Number.isFinite(x)||x<=0)return "-";return x<10?num(x,5):num(x,2)}
function secureEqual(a:string,b:string){if(a.length!==b.length)return false;let x=0;for(let i=0;i<a.length;i++)x|=a.charCodeAt(i)^b.charCodeAt(i);return x===0}
async function markDelivered(table:string,id:number,column:string){const {error}=await sb.from(table).update({[column]:new Date().toISOString()}).eq("id",id);if(error)throw error;}
async function schedulerAuthorized(req:Request){
 const supplied=req.headers.get("x-scheduler-key")||"";if(!supplied)return false;
 const {data,error}=await sb.from("private_runtime_secrets").select("secret_value").eq("id","scheduler_auth").limit(1);
 const expected=String(data?.[0]?.secret_value?.key||"");return !error&&!!expected&&secureEqual(supplied,expected);
}

Deno.serve(async req=>{
 if(req.method!=="POST")return Response.json({ok:false,error:"POST required"},{status:405});
 if(!await schedulerAuthorized(req))return Response.json({ok:false,error:"scheduler authorization required"},{status:401});
 try{
  const body=await req.json().catch(()=>({}));
  if(body.action==="webhook_status"){
   const info=await tg("getWebhookInfo");
   return Response.json({ok:true,webhook:{url:info.url,pending_update_count:info.pending_update_count,last_error_date:info.last_error_date,last_error_message:info.last_error_message,allowed_updates:info.allowed_updates},secret_configured:!!Deno.env.get("TELEGRAM_WEBHOOK_SECRET")});
  }
  if(body.action==="repair_webhook"){
   await tg("setWebhook",{url:URL+"/functions/v1/telegram-bot-webhook",secret_token:webhookSecret(BOT,Deno.env.get("TELEGRAM_WEBHOOK_SECRET")||""),allowed_updates:["message"],drop_pending_updates:false});
   const info=await tg("getWebhookInfo");
   return Response.json({ok:info.url===URL+"/functions/v1/telegram-bot-webhook",pending_update_count:info.pending_update_count});
  }
  if(body.action==="test_overview"&&["A","B"].includes(body.plan)){
   const r=await fetch(URL+"/functions/v1/telegram-bot-webhook",{method:"POST",headers:{"Content-Type":"application/json","x-telegram-bot-api-secret-token":webhookSecret(BOT,Deno.env.get("TELEGRAM_WEBHOOK_SECRET")||"")},body:JSON.stringify({message:{chat:{id:CHAT},text:body.plan==="B"?"🟣 B 현황":"🔵 A 현황"}}),signal:AbortSignal.timeout(25000)});
   const result=await r.json();return Response.json({ok:r.ok&&result.ok===true,plan:body.plan,overview_test:result});
  }
  if(body.action==="test"){await send(`✅ Coin Issue AI · 자동 알림 엔진 정상\n🔵 A플랜 · 기존 실거래 시스템\n${MDD30_STANDARD}\nBTC·ETH·XRP·TRX·SOL · 10x\n총 실질 노출 한도: 1.6x\n매일 08:00 태국시간 재판정\n\n🟣 B플랜 · 별도 계정 · 주문 ON/OFF와 신호 상태는 시스템 메뉴에서 확인`);return Response.json({ok:true,test_sent:true})}
  const {data:rows,error:stateReadError}=await sb.from("telegram_notify_state").select("*").eq("id","singleton").limit(1);if(stateReadError)throw stateReadError;const st=rows?.[0]||{};
  if(st.test_action==="show_history_menu")await send("✅ 실거래 기록 메뉴가 추가됐습니다.\n아래의 🔵 A 기록 / 🟣 B 기록 버튼을 누르면 최신 성과를 확인할 수 있습니다.");
  let lastId=Number(st.last_trade_id||0),lastClosed=st.last_closed_at||"1970-01-01T00:00:00Z",lastError=Number(st.last_error_id||0);
  let lastPbId=Number(st.last_pb_trade_id||0),lastPbClosed=st.last_pb_closed_at||"1970-01-01T00:00:00Z";

  // ---- A플랜 (real_trades) ----
  const {data:newRows,error:e1}=await sb.from("real_trades").select("id,symbol,side,signal_type,status,margin_usd,leverage,notional_usd,entry_price,reject_reason,strategy_config,bingx_order_id").or("and(status.in.(open,closing,closed),telegram_entry_notified_at.is.null),and(status.eq.rejected,telegram_rejection_notified_at.is.null)").order("id",{ascending:true});if(e1)throw e1;
  for(const x of newRows||[]){lastId=Math.max(lastId,Number(x.id));if(["open","closing","closed"].includes(x.status)&&x.bingx_order_id&&Number(x.entry_price)>0){const exposure=x.strategy_config?.exposure_multiplier;await send(`🔵 A플랜 · 신규 진입 🚀\n${x.symbol} ${side(x.side)}\n${x.signal_type==="answer_mdd30"?`${MDD30_STANDARD}\n`:""}진입가: ${price(x.entry_price)}\n담보금: ${num(x.margin_usd)} USDT\n레버리지: ${x.leverage}x${exposure==null?"":`\n목표 실질 노출: ${num(exposure,3)}x`}\n포지션 규모: ${num(x.notional_usd)} USDT${x.signal_type==="answer_mdd30"?"\n총 실질 노출 한도: 1.6x":""}`);await markDelivered("real_trades",x.id,"telegram_entry_notified_at")}else if(x.status==="rejected"){await send(`🔵 A플랜 · 주문 거절/실패 ⚠️\n${x.symbol} ${side(x.side)}\n사유: ${String(x.reject_reason||"확인 필요").slice(0,500)}`);await markDelivered("real_trades",x.id,"telegram_rejection_notified_at")}}
  // Do not notify from the executor's provisional close values. Wait until
  // BingX positionHistory has supplied the actual close price, fees and PnL.
  const {data:closed,error:e2}=await sb.from("real_trades").select("id,symbol,side,entry_price,close_price,last_mark_price,net_pnl_usd,margin_usd,closed_at,close_reason").eq("status","closed").eq("close_reason","BingX positionHistory 주문별 동기화").not("net_pnl_usd","is",null).not("close_price","is",null).is("telegram_close_notified_at",null).order("closed_at",{ascending:true});if(e2)throw e2;
  for(const x of closed||[]){if(x.net_pnl_usd==null||!Number.isFinite(Number(x.net_pnl_usd))||!(Number(x.close_price)>0))continue;if(x.closed_at>lastClosed)lastClosed=x.closed_at;const pnl=Number(x.net_pnl_usd);const roe=Number(x.margin_usd)>0&&Number.isFinite(pnl)?pnl/Number(x.margin_usd)*100:null;await send(`🔵 A플랜 · ${pnl>=0?"포지션 청산 ✅":"포지션 청산 🔻"} (거래소 정산)\n${x.symbol} ${side(x.side)}\n진입가: ${price(x.entry_price)}\n청산가: ${price(x.close_price??x.last_mark_price)}\n실현손익: ${pnl>=0?"+":""}${num(pnl)} USDT${roe==null?"":`\n담보수익률: ${roe>=0?"+":""}${num(roe)}%`}\n사유: ${x.close_reason||"전략/거래소 종료"}`);await markDelivered("real_trades",x.id,"telegram_close_notified_at")}

  // ---- B플랜 (plan_b_real_trades) ----
  // B settlement is asynchronous. Notify only verified settlement; track each trade independently.
  const {data:newPbRows,error:eb1}=await sb.from("plan_b_real_trades").select("id,symbol,side,status,margin_usd,leverage,entry_price,reject_reason,bingx_order_id").or("and(status.in.(open,closing,closed),telegram_entry_notified_at.is.null),and(status.eq.rejected,telegram_rejection_notified_at.is.null)").order("id",{ascending:true});if(eb1)throw eb1;
  for(const x of newPbRows||[]){lastPbId=Math.max(lastPbId,Number(x.id));if(["open","closing","closed"].includes(x.status)&&x.bingx_order_id&&Number(x.entry_price)>0){const notional=Number(x.margin_usd)*Number(x.leverage);await send(`🟣 B플랜 · ${['ALGO','ETH','VET','LINK','DOT','LTC'].includes(x.symbol)?'공백 반전 보조':'기본 패턴'} 신규 진입 🚀\n${x.symbol} ${side(x.side)}\n진입가: ${price(x.entry_price)}\n담보금: ${num(x.margin_usd)} USDT\n레버리지: ${x.leverage}x\n포지션 규모: ${num(notional)} USDT`);await markDelivered("plan_b_real_trades",x.id,"telegram_entry_notified_at")}else if(x.status==="rejected"){await send(`🟣 B플랜 · 주문 거절/실패 ⚠️\n${x.symbol} ${side(x.side)}\n사유: ${String(x.reject_reason||"확인 필요").slice(0,500)}`);await markDelivered("plan_b_real_trades",x.id,"telegram_rejection_notified_at")}}
  const {data:closedPb,error:eb2}=await sb.from("plan_b_real_trades").select("id,symbol,side,entry_price,close_price,net_pnl_usd,margin_usd,closed_at").eq("status","closed").not("net_pnl_usd","is",null).not("close_price","is",null).not("bingx_order_id","is",null).is("telegram_close_notified_at",null).order("closed_at",{ascending:true});if(eb2)throw eb2;
  for(const x of closedPb||[]){if(x.net_pnl_usd==null||!Number.isFinite(Number(x.net_pnl_usd))||!(Number(x.close_price)>0))continue;const pnl=Number(x.net_pnl_usd);const roe=Number(x.margin_usd)>0&&Number.isFinite(pnl)?pnl/Number(x.margin_usd)*100:null;await send(`🟣 B플랜 · ${['ALGO','ETH','VET','LINK','DOT','LTC'].includes(x.symbol)?'공백 반전 보조':'기본 패턴'} · ${pnl>=0?"포지션 청산 ✅":"포지션 청산 🔻"}\n${x.symbol} ${side(x.side)}\n진입가: ${price(x.entry_price)}\n청산가: ${price(x.close_price)}\n실현손익: ${pnl>=0?"+":""}${num(pnl)} USDT${roe==null?"":`\n담보수익률: ${roe>=0?"+":""}${num(roe)}%`}`);const {error:sentError}=await sb.from("plan_b_real_trades").update({telegram_close_notified_at:new Date().toISOString()}).eq("id",x.id);if(sentError)throw sentError;}

  const {data:snap,error:snapshotError}=await sb.from("coin_snapshots").select("updated_at,payload").eq("id","live").limit(1);if(snapshotError)throw snapshotError;const hb=snap?.[0]?.updated_at?Date.parse(snap[0].updated_at):0,stale=!hb||Date.now()-hb>180000,was=!!st.collector_stale;if(stale&&!was)await send(`🚨 시스템 경고\nCoin Collector heartbeat가 3분 이상 멈챰습니다.\n마지막 heartbeat: ${snap?.[0]?.updated_at||"없음"}`);if(!stale&&was)await send("✅ 시스템 복구\nCoin Collector heartbeat가 정상으로 돌아왔습니다.");
  const [{data:bHealth,error:bHealthError},{data:bState,error:bStateError}]=await Promise.all([sb.from("plan_b_runtime_health").select("*"),sb.from("plan_b_trading_state").select("enabled,test_mode").eq("id","singleton").single()]);
  if(bHealthError||bStateError)throw bHealthError||bStateError;
  const pendingById=new Map((Array.isArray(st.pending_transport_errors)?st.pending_transport_errors:[]).map((e:any)=>[Number(e.id),e]));
  const {data:errs,error:e3}=await sb.from("system_errors").select("id,source,status_code,message,created_at").gt("id",lastError).order("id",{ascending:true}).limit(20);if(e3)throw e3;
  for(const e of errs||[]){
   lastError=Math.max(lastError,Number(e.id));
   const disposition=transportErrorDisposition({error:e,snapshot:snap?.[0],bHealth:bHealth||[]});
   if(disposition==='immediate'||disposition==='alert')await send(`🚨 시스템 오류 감지\n구간: ${e.source}\nHTTP: ${e.status_code??"-"}\n내용: ${String(e.message||"").slice(0,500)}\n시각: ${e.created_at}`);
   else if(disposition==='pending')pendingById.set(Number(e.id),e);
  }
  const pendingTransportErrors=[];
  for(const e of pendingById.values()){
   const disposition=transportErrorDisposition({error:e,snapshot:snap?.[0],bHealth:bHealth||[]});
   if(disposition==='pending')pendingTransportErrors.push(e);
   else if(disposition==='alert')await send(`🚨 시스템 오류 감지\n구간: ${e.source}\nHTTP: ${e.status_code??"-"}\n내용: ${String(e.message||"").slice(0,500)}\n시각: ${e.created_at}`);
  }
  const problems=healthProblems({snapshot:snap?.[0],bHealth:bHealth||[],bState});
  // Retired news incidents are not recoveries; preserve all trading alerts and delivery markers.
  const priorHealth=snap?.[0]?.payload?.news_enabled===false
    ? Object.fromEntries(Object.entries(st.health_alerts||{}).filter(([key])=>key!=='__news_state'&&!key.startsWith('news:')))
    : st.health_alerts||{};
  const stable=stableHealthAlerts(priorHealth,problems);
  const transitions=healthTransitions(stable.previous,stable.active);
  if(transitions.opened.length)await send("⚠️ 보조 기능 오류 감지\n"+transitions.opened.map(([,v])=>v).join("\n").slice(0,3000)+"\n실거래 ON/OFF는 변경하지 않았습니다.");
  if(transitions.resolved.length)await send("✅ 보조 기능 복구\n"+transitions.resolved.join("\n"));
  const {error:stateWriteError}=await sb.from("telegram_notify_state").upsert({id:"singleton",health_alerts:stable.stored,pending_transport_errors:pendingTransportErrors,last_trade_id:lastId,last_closed_at:lastClosed,last_pb_trade_id:lastPbId,last_pb_closed_at:lastPbClosed,collector_stale:stale,last_error_id:lastError,test_action:null,updated_at:new Date().toISOString()});
  if(stateWriteError)throw stateWriteError;
  return Response.json({ok:true,last_trade_id:lastId,last_pb_trade_id:lastPbId,last_error_id:lastError,collector_stale:stale});
 }catch(e){console.error(e);try{await send(`🚨 Telegram 자동 알림 엔진 오류\n${e instanceof Error?e.message:String(e)}`)}catch{}return Response.json({ok:false,error:e instanceof Error?e.message:String(e)},{status:500})}
});
