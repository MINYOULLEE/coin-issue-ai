import {createDashboardSessions,reserveLoginAttempt} from "../_shared/dashboard_sessions.mjs";
import {allHistoryPages} from "../_shared/history_pages.mjs";
const planSessions=createDashboardSessions("A");
import { createHmac } from "node:crypto";
import JSONBig from "npm:json-bigint@1.0.0";

const JSONBigParse = JSONBig({ storeAsString: true });
const API_KEY = Deno.env.get("BINGX_API_KEY") || "";
const SECRET_KEY = Deno.env.get("BINGX_SECRET_KEY") || "";
const PROJECT_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const INTERNAL_TRADE_SECRET = Deno.env.get("INTERNAL_TRADE_SECRET") || "";
const BASE = {
  "prod-live": ["https://open-api.bingx.com", "https://open-api.bingx.pro"],
};

function isNetworkOrTimeout(e: unknown): boolean {
  if (e instanceof TypeError) return true;
  if (e instanceof DOMException && e.name === "AbortError") return true;
  if (e instanceof Error && e.name === "TimeoutError") return true;
  if (e instanceof Error && /empty response|parse failed/i.test(e.message)) return true;
  return false;
}

function validateParams(params: Record<string, unknown>): void {
  const FORBIDDEN = /[&=?#\r\n]/;
  for (const [k, v] of Object.entries(params)) {
    const s = String(v);
    if (FORBIDDEN.test(s)) throw new Error(`Param "${k}" has forbidden char in: "${s}"`);
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function fetchSigned(env: string, apiKey: string, secretKey: string,
  method: "GET" | "POST" | "DELETE", path: string, params: Record<string, unknown> = {}
) {
  const urls = BASE[env as keyof typeof BASE] ?? BASE["prod-live"];
  const all = { ...params, timestamp: Date.now() };
  validateParams(all);
  const qs = Object.keys(all).sort().map(k => `${k}=${all[k as keyof typeof all]}`).join("&");
  const sig = createHmac("sha256", secretKey).update(qs).digest("hex");
  const signed = `${qs}&signature=${sig}`;
  for (const base of urls) {
    try {
      const url = method === "POST" ? `${base}${path}` : `${base}${path}?${signed}`;
      const res = await fetch(url, {
        method,
        headers: { "X-BX-APIKEY": apiKey, "X-SOURCE-KEY": "BX-AI-SKILL",
          ...(method === "POST" ? { "Content-Type": "application/x-www-form-urlencoded" } : {}) },
        body: method === "POST" ? signed : undefined,
        signal: AbortSignal.timeout(10000),
      });
      const text = await res.text();
      if (!text) throw new Error(`empty response from BingX (status ${res.status}, possibly rate limited)`);
      let json: any;
      try { json = JSONBigParse.parse(text); } catch { throw new Error("parse failed: BingX returned non-JSON body"); }
      if (json.code !== 0) throw new Error(`BingX error ${json.code}: ${json.msg}`);
      return json.data;
    } catch (e) {
      if (!isNetworkOrTimeout(e) || base === urls[urls.length - 1]) throw e;
    }
  }
}

function n(v: unknown): number {
  const x = Number(v ?? 0);
  return Number.isFinite(x) ? x : 0;
}

async function db(path: string, init: RequestInit = {}) {
  const r = await fetch(PROJECT_URL + "/rest/v1/" + path, {
    ...init,
    headers: { apikey: SERVICE_KEY, Authorization: "Bearer " + SERVICE_KEY, "Content-Type": "application/json", ...(init.headers || {}) },
  });
  const text = await r.text();
  if (!r.ok) throw new Error("db " + path + " " + r.status + " " + text);
  if (!text) return null;
  try { return JSON.parse(text); } catch { throw new Error("db json parse failed on " + path + " (len=" + text.length + ")"); }
}


const TRACKED_SYMBOLS=["BTC-USDT","ETH-USDT","XRP-USDT","SOL-USDT","BNB-USDT","DOGE-USDT","ADA-USDT","LINK-USDT","AVAX-USDT","SUI-USDT","LTC-USDT","BCH-USDT","TRX-USDT","AAVE-USDT"];
function isoTime(v:unknown):string|null{
  const x=Number(v||0); if(!x)return null;
  const ms=x<100000000000?x*1000:x;
  const d=new Date(ms); return Number.isNaN(d.getTime())?null:d.toISOString();
}
function listOf(v:any):any[]{
  if(Array.isArray(v))return v;
  for(const k of ["list","positions","positionHistory","orders","items","data"]){
    if(Array.isArray(v?.[k]))return v[k];
  }
  return [];
}
function sideOf(v:any):"long"|"short"{
  const s=String(v?.positionSide||v?.side||v?.direction||"").toUpperCase();
  if(s.includes("SHORT")||s.includes("SELL"))return "short";
  if(s.includes("LONG")||s.includes("BUY"))return "long";
  return n(v?.positionAmt??v?.positionAmount??v?.amount)<0?"short":"long";
}
function symbolOf(v:any,fallback=""):string{
  const s=String(v?.symbol||fallback).toUpperCase().replace("/","-");
  return s.includes("-")?s:s.endsWith("USDT")?s.slice(0,-4)+"-USDT":s;
}
async function syncActualBingxHistory(){
  if(!API_KEY||!SECRET_KEY)throw new Error("BingX API key missing");
  const now=Date.now(),syncedAt=new Date(now).toISOString(),errors:string[]=[];
  const openData=await fetchSigned("prod-live",API_KEY,SECRET_KEY,"GET","/openApi/swap/v2/user/positions",{recvWindow:5000});
  const openRows=listOf(openData).filter((v:any)=>Math.abs(n(v?.positionAmt??v?.positionAmount??v?.amount))>0).map((v:any)=>{
    const symbol=symbolOf(v),side=sideOf(v),qty=Math.abs(n(v?.positionAmt??v?.positionAmount??v?.amount));
    const entry=n(v?.avgPrice??v?.entryPrice??v?.openPrice),lev=Math.max(1,Math.round(n(v?.leverage)||1));
    const pid=String(v?.positionId??v?.id??"");
    return {external_id:pid?"position:"+pid:`open:${symbol}:${side}`,position_id:pid||null,symbol,side,status:"open",
      entry_price:entry||null,close_price:null,quantity:qty||null,margin_usd:n(v?.initialMargin??v?.margin??v?.positionMargin)||(entry&&qty?entry*qty/lev:null),
      leverage:lev,realized_pnl_usd:null,unrealized_pnl_usd:n(v?.unrealizedProfit??v?.unrealizedPnl),fee_usd:null,
      opened_at:isoTime(v?.positionTime??v?.openTime??v?.createTime??v?.time),closed_at:null,raw:v,synced_at:syncedAt};
  });
  const closedRows:any[]=[];
  // 기본 종목과 최근 7일 동안 실제 주문이 있었던 후보군 A 종목만 조회한다. 매분 15종목
  // 전체를 호출하면 BingX 제한에 걸릴 수 있지만, 이 방식이면 새로 거래된 종목도 즉시 포함된다.
  // 다만 과거에 거부됐을 뿐 BingX에 애초에 없는 종목이 섞여 들어오면 매분 같은 오류가
  // 반복되므로, 존재하지 않는 것으로 이미 확인된 종목은 여기서 걸러낸다.
  const KNOWN_INVALID_SYMBOLS = new Set(["TON-USDT"]);
  const recentTracked=(await db(`real_trades?created_at=gte.${new Date(now-7*86400000).toISOString()}&select=bingx_symbol`))||[];
  const historySymbols=[...new Set([...TRACKED_SYMBOLS.slice(0,5),...openRows.map((x:any)=>x.symbol),...recentTracked.map((x:any)=>String(x.bingx_symbol||"")).filter(Boolean)])].filter(s=>!KNOWN_INVALID_SYMBOLS.has(s));
  for(let i=0;i<historySymbols.length;i++){
    const symbol=historySymbols[i];
    if(i>0)await sleep(550);
    try{
      const data=await fetchSigned("prod-live",API_KEY,SECRET_KEY,"GET","/openApi/swap/v1/trade/positionHistory",
        {symbol,currency:"USDT",startTs:now-7*86400000,endTs:now,pageIndex:1,pageSize:100,recvWindow:5000});
      const historyItems=listOf(data);
      if(!historyItems.length){
        const orderData=await fetchSigned("prod-live",API_KEY,SECRET_KEY,"GET","/openApi/swap/v2/trade/allOrders",
          {symbol,startTime:now-7*86400000,endTime:now,limit:1000,recvWindow:5000});
        const fills=listOf(orderData).filter((o:any)=>String(o?.status).toUpperCase()==="FILLED"&&n(o?.executedQty??o?.origQty)>0);
        const groups=new Map<string,any[]>();
        for(const o of fills){const pid=String(o?.positionID??o?.positionId??"");if(!pid)continue;const g=groups.get(pid)||[];g.push(o);groups.set(pid,g)}
        for(const [pid,g] of groups){
          const opens=g.filter((o:any)=>!Boolean(o?.reduceOnly));
          const closes=g.filter((o:any)=>Boolean(o?.reduceOnly));
          const openQty=opens.reduce((s:number,o:any)=>s+Math.abs(n(o?.executedQty??o?.origQty)),0);
          const closeQty=closes.reduce((s:number,o:any)=>s+Math.abs(n(o?.executedQty??o?.origQty)),0);
          if(!opens.length||!closes.length||closeQty+1e-12<openQty*0.999)continue;
          const wavg=(xs:any[])=>{const q=xs.reduce((s,o)=>s+Math.abs(n(o?.executedQty??o?.origQty)),0);return q?xs.reduce((s,o)=>s+n(o?.avgPrice??o?.price)*Math.abs(n(o?.executedQty??o?.origQty)),0)/q:0};
          const entry=wavg(opens),close=wavg(closes),lev=Math.max(1,Math.round(n(String(opens[0]?.leverage||"1").replace(/X/gi,""))||1));
          const gross=g.reduce((s:number,o:any)=>s+n(o?.profit),0),commission=g.reduce((s:number,o:any)=>s+n(o?.commission),0);
          const opened=Math.min(...opens.map((o:any)=>n(o?.time??o?.updateTime)).filter(Boolean));
          const closed=Math.max(...closes.map((o:any)=>n(o?.updateTime??o?.time)).filter(Boolean));
          const ps=String(opens[0]?.positionSide||"").toUpperCase();
          closedRows.push({external_id:"position:"+pid,position_id:pid,symbol,side:ps==="SHORT"?"short":"long",status:"closed",
            entry_price:entry||null,close_price:close||null,quantity:openQty||null,margin_usd:entry&&openQty?entry*openQty/lev:null,leverage:lev,
            realized_pnl_usd:gross+commission,unrealized_pnl_usd:null,fee_usd:Math.abs(commission),opened_at:isoTime(opened),closed_at:isoTime(closed),
            raw:{source:"allOrders",gross_pnl:gross,commission,open_order_ids:opens.map((o:any)=>String(o?.orderId||"")),close_order_ids:closes.map((o:any)=>String(o?.orderId||""))},synced_at:syncedAt});
        }
      }
      for(const v of historyItems){
        const sym=symbolOf(v,symbol),side=sideOf(v),qty=Math.abs(n(v?.positionAmt??v?.positionAmount??v?.openPositionAmt??v?.closePositionAmt??v?.quantity??v?.amount));
        const entry=n(v?.avgPrice??v?.avgOpenPrice??v?.openPrice??v?.entryPrice),close=n(v?.closeAvgPrice??v?.avgClosePrice??v?.closePrice);
        const lev=Math.max(1,Math.round(n(v?.leverage)||1)),pnl=n(v?.netProfit??v?.realizedProfit??v?.realisedProfit??v?.realizedPnl??v?.profit);
        const fee=Math.abs(n(v?.commission??v?.tradingFee??v?.fee)),closedAt=isoTime(v?.closeTime??v?.updateTime??v?.endTime);
        const pid=String(v?.positionId??v?.id??"");
        closedRows.push({external_id:pid?"position:"+pid:`closed:${sym}:${side}:${closedAt||String(v?.closeTime||v?.updateTime||"unknown")}`,
          position_id:pid||null,symbol:sym,side,status:"closed",entry_price:entry||null,close_price:close||null,quantity:qty||null,
          margin_usd:n(v?.initialMargin??v?.margin??v?.positionMargin)||(entry&&qty?entry*qty/lev:null),leverage:lev,
          realized_pnl_usd:pnl,unrealized_pnl_usd:null,fee_usd:fee||null,
          opened_at:isoTime(v?.positionTime??v?.openTime??v?.createTime??v?.time),closed_at:closedAt,raw:v,synced_at:syncedAt});
      }
    }catch(e){const msg=symbol+": "+String(e instanceof Error?e.message:e);errors.push(msg);console.error("BingX positionHistory:",msg)}
  }
  await db("bingx_trade_history?status=eq.open",{method:"PATCH",headers:{Prefer:"return=minimal"},body:JSON.stringify({status:"stale",synced_at:syncedAt})});
  const byId=new Map<string,any>(); for(const row of [...openRows,...closedRows])byId.set(row.external_id,row);
  const rows=[...byId.values()];
  for(let i=0;i<rows.length;i+=40){const chunk=rows.slice(i,i+40);await db("bingx_trade_history?on_conflict=external_id",{method:"POST",headers:{Prefer:"resolution=merge-duplicates,return=minimal"},body:JSON.stringify(chunk)})}
  // 동일 종목을 종료 직후 재진입해도 손익이 앞뒤 거래에 섞이지 않도록 BingX의 positionHistory
  // 한 건을 진입 시각이 가장 가까운 내부 주문 한 건에 1:1로 매칭한다.
  const internal=(await db(`real_trades?created_at=gte.${new Date(now-7*86400000).toISOString()}&status=eq.closed&select=id,signal_id,symbol,side,created_at,entry_filled_at`))||[];
  const matched=new Set<number>();
  for(const actual of closedRows.filter(x=>x.opened_at&&x.closed_at)){
    const opened=Date.parse(actual.opened_at),symbol=String(actual.symbol||"").replace("-USDT","");
    const match=internal.filter((x:any)=>!matched.has(Number(x.id))&&x.symbol===symbol&&x.side===actual.side)
      .map((x:any)=>({row:x,gap:Math.abs(Date.parse(x.entry_filled_at||x.created_at)-opened)}))
      .filter((x:any)=>x.gap<=120000).sort((a:any,b:any)=>a.gap-b.gap)[0]?.row;
    if(!match)continue;matched.add(Number(match.id));
    const pnl=actual.realized_pnl_usd==null?null:Number(actual.realized_pnl_usd),entry=Number(actual.entry_price||0),close=Number(actual.close_price||0);
    await db(`real_trades?id=eq.${match.id}`,{method:"PATCH",body:JSON.stringify({entry_price:entry||undefined,close_price:close||undefined,last_mark_price:close||undefined,closed_at:actual.closed_at,net_pnl_usd:pnl,fee_usd:actual.fee_usd,close_reason:"BingX positionHistory 주문별 동기화",measurement_updated_at:syncedAt,updated_at:syncedAt})});
    if(match.signal_id){
      const resultPct=entry&&close?(close/entry-1)*100*(actual.side==="long"?1:-1):null;
      await db(`trade_signals?id=eq.${match.signal_id}`,{method:"PATCH",body:JSON.stringify({status:pnl!=null&&pnl>0?"success":pnl!=null&&pnl<0?"failure":"neutral",closed_at:actual.closed_at,exit_price:close||null,result_pct:resultPct,net_pnl_usd:pnl,close_reason:"BingX positionHistory 주문별 동기화",updated_at:syncedAt})});
    }
  }
  return {ok:true,open:openRows.length,closed:closedRows.length,errors};
}

const CORS={"Access-Control-Allow-Origin":"https://minyoullee.github.io","Access-Control-Allow-Headers":"authorization, apikey, content-type, x-dashboard-session","Access-Control-Allow-Methods":"POST, OPTIONS","Cache-Control":"no-store"};
type DashboardAuth={password_salt:string;password_hash:string;session_secret:string};
let dashboardAuthCache:DashboardAuth|null=null;
async function dashboardAuth():Promise<DashboardAuth>{
  if(dashboardAuthCache)return dashboardAuthCache;
  const rows=await db("private_runtime_secrets?id=eq.bingx_dashboard_auth&select=secret_value&limit=1"),v=rows?.[0]?.secret_value||{};
  if(!v.password_salt||!v.password_hash||!v.session_secret)throw new Error("dashboard auth secrets are not configured");
  dashboardAuthCache={password_salt:String(v.password_salt),password_hash:String(v.password_hash),session_secret:String(v.session_secret)};
  return dashboardAuthCache;
}
const te=new TextEncoder();
function fromB64u(s:string){const p=s.replace(/-/g,"+").replace(/_/g,"/")+"===".slice((s.length+3)%4);return Uint8Array.from(atob(p),c=>c.charCodeAt(0))}
function toB64u(a:Uint8Array){return btoa(String.fromCharCode(...a)).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"")}
async function passwordHash(password:string,auth:DashboardAuth){const k=await crypto.subtle.importKey("raw",te.encode(password),"PBKDF2",false,["deriveBits"]);const bits=await crypto.subtle.deriveBits({name:"PBKDF2",salt:fromB64u(auth.password_salt),iterations:210000,hash:"SHA-256"},k,256);return toB64u(new Uint8Array(bits))}
function same(a:string,b:string){if(a.length!==b.length)return false;let d=0;for(let i=0;i<a.length;i++)d|=a.charCodeAt(i)^b.charCodeAt(i);return d===0}
async function sign(v:string,auth:DashboardAuth){const k=await crypto.subtle.importKey("raw",te.encode(auth.session_secret),{name:"HMAC",hash:"SHA-256"},false,["sign"]);return toB64u(new Uint8Array(await crypto.subtle.sign("HMAC",k,te.encode(v))))}
async function issueSession(auth:DashboardAuth){return planSessions.issue(auth.session_secret)}
async function validSession(t:string,auth:DashboardAuth){return planSessions.valid(t,auth.session_secret)}

Deno.serve(async(req:Request)=>{
 if(req.method==="OPTIONS")return new Response("ok",{headers:CORS});
 if(req.method!=="POST")return Response.json({ok:false,error:"POST required"},{status:405,headers:CORS});
 let body:Record<string,unknown>={};try{body=await req.json()}catch{}
 if(body.action==="login"){try{const auth=await dashboardAuth(),budget=await reserveLoginAttempt(req,"A",auth.session_secret,params=>db("rpc/dashboard_login_attempt",{method:"POST",body:JSON.stringify(params)}));if(!budget.allowed)return Response.json({ok:false,error:"로그인 시도 한도 초과 · 잠시 후 다시 시도하세요."},{status:429,headers:{...CORS,"Retry-After":String(budget.retry_after)}});const password=String(body.password||"");if(password.length>1024)return Response.json({ok:false,error:"invalid password length"},{status:400,headers:CORS});if(!same(await passwordHash(password,auth),auth.password_hash))return Response.json({ok:false,error:"비밀번호가 맞지 않습니다."},{status:401,headers:CORS});return Response.json({ok:true,session:await issueSession(auth),expires_in:14400},{headers:CORS})}catch(e){console.error("dashboard login unavailable");return Response.json({ok:false,error:"로그인 보호 상태 확인 실패 · 잠시 후 다시 시도하세요."},{status:503,headers:CORS})}}
 if(body.action==="internal_history_sync"){
   const supplied=req.headers.get("x-internal-key")||"";
   if(!INTERNAL_TRADE_SECRET||!same(supplied,INTERNAL_TRADE_SECRET))return Response.json({ok:false,error:"forbidden"},{status:403,headers:CORS});
   try{const result=await syncActualBingxHistory();if(Array.isArray(result?.errors)&&result.errors.length)console.error("internal_history_sync partial warnings",JSON.stringify(result.errors));return Response.json(result,{headers:CORS})}
   catch(e){console.error("internal_history_sync failed",e instanceof Error?(e.stack||e.message):String(e));return Response.json({ok:false,error:String(e instanceof Error?e.message:e)},{status:502,headers:CORS})}
 }
 // 거래 기록은 읽기 전용 공개 화면에서 사용한다. 계좌 조회·포지션 제어·주문
 // ON/OFF는 아래 세션 검증을 반드시 거치며, 공개 기록 요청은 BingX API를 직접
 // 호출하지 않고 주기적으로 동기화된 DB 스냅샷만 반환한다.
 const publicHistory=body.action==="trade_history";
 if(!publicHistory){
  let auth:DashboardAuth;try{auth=await dashboardAuth()}catch(e){console.error("dashboard auth unavailable",e instanceof Error?e.message:String(e));return Response.json({ok:false,error:"인증 설정을 불러오지 못했습니다."},{status:503,headers:CORS})}
  if(!await validSession(req.headers.get("x-dashboard-session")||"",auth))return Response.json({ok:false,locked:true,error:"잠금 해제가 필요합니다."},{status:401,headers:CORS});
 }

 // 실거래 긴급 정지 스위치 상태 조회. test_mode 여부와 상관없이 지금 도는 실제 주문을 전부 보여준다.
 if(body.action==="trading_state"){
   try{
     const rows=await db("real_trading_state?id=eq.singleton&select=*&limit=1");
     const state=rows?.[0]||null;
     const openTrades=await db("real_trades?status=eq.open&select=symbol,side,signal_type,margin_usd,leverage,notional_usd,entry_price,stop_price,target_price,test_mode,bingx_order_id,created_at&order=created_at.desc");
     const recentTrades=await db("real_trades?status=neq.open&select=symbol,side,signal_type,status,margin_usd,leverage,net_pnl_usd,test_mode,bingx_order_id,reject_reason,close_reason,created_at,closed_at&order=created_at.desc&limit=30");
     const pending=await db("trade_execution_reservations?select=execution_status,last_error");
     const snapshots=await db("coin_snapshots?id=eq.live&select=payload,updated_at");
     const snap=snapshots?.[0],c=snap?.payload?.signal_candidates;
     const diagnostics={pending_entries:pending?.length||0,recovery_errors:(pending||[]).filter((x:any)=>x.last_error).length,signal_status:!snap||Date.now()-Date.parse(snap.updated_at)>180000?"stale":c?.entry_recovery?.ok===false?"error":(snap.payload.active_signals||[]).some((x:any)=>x.signal_type==="answer_mdd30"&&x.status==="active")?"active":"no_signal",decision_status:c?.hourly_audit?.status||"unknown"};
     return Response.json({ok:true,state,diagnostics,open_trades:openTrades||[],recent_trades:recentTrades||[]},{headers:CORS});
   }catch(e){return Response.json({ok:false,error:"실거래 상태 조회 실패"},{status:502,headers:CORS})}
 }

 if(body.action==="trade_history"){
   try{
     // 공개 화면에서는 BingX 비밀 API를 직접 호출하지 않는다. 별도 내부 스케줄러가
     // 동기화한 실제 Position History만 읽어 API 키와 거래소 호출 한도를 보호한다.
     const sync={ok:true,source:"scheduled_snapshot"};
     const page=Math.max(1,Math.floor(Number(body.page||1))),limit=Math.max(1,Math.min(50,Math.floor(Number(body.limit||20)))),offset=(page-1)*limit;
     const all=await allHistoryPages((offset,limit)=>db(`bingx_trade_history?status=in.(open,closed)&select=*&order=opened_at.desc,external_id.desc&limit=${limit}&offset=${offset}`));
     const mapped=(all||[]).map((x:any)=>{
       const raw=x.raw||{},entry=n(x.entry_price),close=n(x.close_price),qty=n(x.quantity),margin=n(x.margin_usd),lev=n(x.leverage)||1;
       const notional=n(raw.positionValue??raw.openAmt??raw.totalOpen??raw.openValue)||(entry&&qty?entry*qty:0);
       const fee=n(x.fee_usd),closed=x.status==="closed";
       const pnl=closed?(x.realized_pnl_usd==null?null:n(x.realized_pnl_usd)):(x.unrealized_pnl_usd==null?null:n(x.unrealized_pnl_usd));
       const roi=margin>0&&pnl!=null?pnl/margin*100:null;
       const base=notional>0&&pnl!=null?pnl/notional*100:null;
       return {symbol:String(x.symbol||"").replace("-USDT",""),side:x.side,
         signal_type:"BingX API",status:x.status,test_mode:false,margin_usd:margin||null,leverage:lev||null,
         notional_usd:notional||null,quantity:qty||null,entry_price:entry||null,stop_price:null,target_price:null,
         fill_price:entry||null,fee_usd:fee||null,close_price:close||null,close_reason:closed?"BingX 포지션 종료":null,
         net_pnl_usd:pnl,reject_reason:null,created_at:x.opened_at,updated_at:x.synced_at,closed_at:x.closed_at,
         unrealized_pnl_usd:closed?null:pnl,base_return_pct:base,margin_return_pct:roi,r_multiple:null,
         evaluation:!closed?"진행 중":pnl!=null&&pnl>0?"성공":pnl!=null&&pnl<0?"실패":"중립"};
     });
     const rows=mapped.slice(offset,offset+limit),closed=mapped.filter((x:any)=>x.status==="closed"&&x.net_pnl_usd!=null);
     const pnls=closed.map((x:any)=>n(x.net_pnl_usd)),rois=closed.filter((x:any)=>n(x.margin_usd)>0).map((x:any)=>n(x.net_pnl_usd)/n(x.margin_usd)*100);
     const wins=pnls.filter((x:number)=>x>0),losses=pnls.filter((x:number)=>x<0),totalPnl=pnls.reduce((a:number,v:number)=>a+v,0);
      const totalFee=closed.reduce((a:number,x:any)=>a+Math.abs(n(x.fee_usd)),0);
      const winPnl=wins.reduce((a:number,v:number)=>a+v,0),lossPnl=losses.reduce((a:number,v:number)=>a+v,0);
      const openPnl=mapped.filter((x:any)=>x.status==="open"&&x.net_pnl_usd!=null).reduce((a:number,x:any)=>a+n(x.net_pnl_usd),0);
      // 실현 기준금은 시작 $100 + 확정 종료 손익이며 실제 계좌 담보금이 아니다.
      // 진행 중 포지션의 미실현 손익은 계속 변하므로 별도 equity 필드로 제공한다.
      const currentBalance=100+totalPnl;
      const equityIncludingOpen=currentBalance+openPnl;
     let equity=100,peak=100,maxDd=0;[...closed].reverse().forEach((x:any)=>{equity+=n(x.net_pnl_usd);peak=Math.max(peak,equity);if(peak>0)maxDd=Math.max(maxDd,(peak-equity)/peak*100)});
     return Response.json({ok:true,source:"bingx_position_history",sync,page,limit,total:mapped.length,pages:Math.max(1,Math.ceil(mapped.length/limit)),rows,stats:{
       closed:closed.length,wins:wins.length,losses:losses.length,win_rate:closed.length?wins.length/closed.length*100:0,
       total_pnl_usd:totalPnl,avg_pnl_usd:closed.length?totalPnl/closed.length:0,
       avg_margin_return_pct:rois.length?rois.reduce((a:number,v:number)=>a+v,0)/rois.length:0,
       account_return_pct:totalPnl,profit_factor:losses.length?wins.reduce((a:number,v:number)=>a+v,0)/Math.abs(losses.reduce((a:number,v:number)=>a+v,0)):wins.length?null:0,
       max_drawdown_pct:maxDd,total_fee_usd:totalFee,win_pnl_usd:winPnl,loss_pnl_usd:lossPnl,
       current_balance_usd:currentBalance,open_pnl_usd:openPnl,equity_including_open_usd:equityIncludingOpen
     }},{headers:CORS});
   }catch(e){console.error("trade_history failed",e instanceof Error?(e.stack||e.message):String(e));return Response.json({ok:false,error:"BingX 실제 포지션 기록 동기화 실패: "+(e instanceof Error?e.message:String(e))},{status:502,headers:CORS})}
 }

 if(body.action==="trading_toggle"){
   try{
     const enabled=!!body.enabled;
     const rows=await db("real_trading_state?id=eq.singleton",{method:"PATCH",headers:{Prefer:"return=representation"},body:JSON.stringify({enabled,updated_at:new Date().toISOString()})});
     return Response.json({ok:true,state:rows?.[0]||null},{headers:CORS});
   }catch(e){return Response.json({ok:false,error:"상태 변경 실패"},{status:502,headers:CORS})}
 }

 if(!API_KEY||!SECRET_KEY)return Response.json({ok:false,error:"BingX secrets are not configured"},{status:500,headers:CORS});
 try{const [account,rawPositions,fees]=await Promise.all([
  fetchSigned("prod-live",API_KEY,SECRET_KEY,"GET","/openApi/swap/v3/user/balance",{recvWindow:5000}),
  fetchSigned("prod-live",API_KEY,SECRET_KEY,"GET","/openApi/swap/v2/user/positions",{recvWindow:5000}),
  fetchSigned("prod-live",API_KEY,SECRET_KEY,"GET","/openApi/swap/v2/user/commissionRate",{recvWindow:5000})]);
 const accountRows=Array.isArray(account)?account:(Array.isArray(account?.balance)?account.balance:[account?.balance||account||{}]),b=accountRows.find((x:Record<string,unknown>)=>String(x?.asset||"").toUpperCase()==="USDT")||accountRows[0]||{},rows=Array.isArray(rawPositions)?rawPositions:(rawPositions?.positions||[]);
 const positions=rows.filter((p:Record<string,unknown>)=>Math.abs(n(p.positionAmt??p.positionAmount))>0).map((p:Record<string,unknown>)=>({symbol:String(p.symbol||""),side:String(p.positionSide||(n(p.positionAmt)>=0?"LONG":"SHORT")),amount:n(p.positionAmt??p.positionAmount),entry_price:n(p.avgPrice??p.entryPrice),mark_price:n(p.markPrice),unrealized_pnl:n(p.unrealizedProfit),liquidation_price:n(p.liquidationPrice),leverage:n(p.leverage)}));
 return Response.json({ok:true,connected:true,mode:"read_only",checked_at:new Date().toISOString(),account:{asset:String(b.asset||"USDT"),balance:n(b.balance),equity:n(b.equity),available_margin:n(b.availableMargin),used_margin:n(b.usedMargin),unrealized_pnl:n(b.unrealizedProfit)},open_position_count:positions.length,positions,commission:fees?.commission||fees||{}},{headers:CORS})
 }catch(e){console.error("BingX read failed:",e instanceof Error?e.message:String(e));return Response.json({ok:false,connected:false,error:"BingX 조회에 실패했습니다."},{status:502,headers:CORS})}
});
