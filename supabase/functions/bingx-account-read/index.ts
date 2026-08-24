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


const TRACKED_SYMBOLS=["BTC-USDT","ETH-USDT","XRP-USDT","SOL-USDT","BNB-USDT"];
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
  for(let i=0;i<TRACKED_SYMBOLS.length;i++){
    const symbol=TRACKED_SYMBOLS[i];
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
  return {ok:true,open:openRows.length,closed:closedRows.length,errors};
}

const CORS={"Access-Control-Allow-Origin":"https://minyoullee.github.io","Access-Control-Allow-Headers":"authorization, apikey, content-type, x-dashboard-session","Access-Control-Allow-Methods":"POST, OPTIONS","Cache-Control":"no-store"};
const PASSWORD_SALT="scv3Xkm5i8d6NhNjZ1JM6Q",PASSWORD_HASH="XH7wcnYgsa9H0KizBb6Ya2Y9KhnoNehg4IRFkGLFuGg",SESSION_SECRET="cxpJJemKx6_lG70gL3Ae23n42mmQZTx0mfB7cRqpzQQ";
const attempts=new Map<string,{count:number;reset:number}>(),te=new TextEncoder();
function fromB64u(s:string){const p=s.replace(/-/g,"+").replace(/_/g,"/")+"===".slice((s.length+3)%4);return Uint8Array.from(atob(p),c=>c.charCodeAt(0))}
function toB64u(a:Uint8Array){return btoa(String.fromCharCode(...a)).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"")}
async function passwordHash(password:string){const k=await crypto.subtle.importKey("raw",te.encode(password),"PBKDF2",false,["deriveBits"]);const bits=await crypto.subtle.deriveBits({name:"PBKDF2",salt:fromB64u(PASSWORD_SALT),iterations:210000,hash:"SHA-256"},k,256);return toB64u(new Uint8Array(bits))}
function same(a:string,b:string){if(a.length!==b.length)return false;let d=0;for(let i=0;i<a.length;i++)d|=a.charCodeAt(i)^b.charCodeAt(i);return d===0}
async function sign(v:string){const k=await crypto.subtle.importKey("raw",te.encode(SESSION_SECRET),{name:"HMAC",hash:"SHA-256"},false,["sign"]);return toB64u(new Uint8Array(await crypto.subtle.sign("HMAC",k,te.encode(v))))}
async function issueSession(){const p=toB64u(te.encode(JSON.stringify({exp:Date.now()+14400000,nonce:crypto.randomUUID()})));return p+"."+await sign(p)}
async function validSession(t:string){const [p,s]=t.split(".");if(!p||!s||!same(await sign(p),s))return false;try{return Number(JSON.parse(new TextDecoder().decode(fromB64u(p))).exp)>Date.now()}catch{return false}}

Deno.serve(async(req:Request)=>{
 if(req.method==="OPTIONS")return new Response("ok",{headers:CORS});
 if(req.method!=="POST")return Response.json({ok:false,error:"POST required"},{status:405,headers:CORS});
 let body:Record<string,unknown>={};try{body=await req.json()}catch{}
 if(body.action==="login"){const ip=req.headers.get("x-forwarded-for")?.split(",")[0]?.trim()||"unknown",now=Date.now(),a=attempts.get(ip);if(a&&a.reset>now&&a.count>=5)return Response.json({ok:false,error:"15분 후 다시 시도하세요."},{status:429,headers:{...CORS,"Retry-After":"900"}});const ok=same(await passwordHash(String(body.password||"")),PASSWORD_HASH);if(!ok){attempts.set(ip,{count:a&&a.reset>now?a.count+1:1,reset:now+900000});return Response.json({ok:false,error:"비밀번호가 맞지 않습니다."},{status:401,headers:CORS})}attempts.delete(ip);return Response.json({ok:true,session:await issueSession(),expires_in:14400},{headers:CORS})}
 if(body.action==="internal_history_sync"){
   const supplied=req.headers.get("x-internal-key")||"";
   if(!INTERNAL_TRADE_SECRET||!same(supplied,INTERNAL_TRADE_SECRET))return Response.json({ok:false,error:"forbidden"},{status:403,headers:CORS});
   try{const result=await syncActualBingxHistory();if(Array.isArray(result?.errors)&&result.errors.length){console.error("internal_history_sync errors",JSON.stringify(result.errors));return Response.json(result,{status:502,headers:CORS})}return Response.json(result,{headers:CORS})}
   catch(e){console.error("internal_history_sync failed",e instanceof Error?(e.stack||e.message):String(e));return Response.json({ok:false,error:String(e instanceof Error?e.message:e)},{status:502,headers:CORS})}
 }
 if(!await validSession(req.headers.get("x-dashboard-session")||""))return Response.json({ok:false,locked:true,error:"잠금 해제가 필요합니다."},{status:401,headers:CORS});

 // 실거래 긴급 정지 스위치 상태 조회. test_mode 여부와 상관없이 지금 도는 실제 주문을 전부 보여준다.
 if(body.action==="trading_state"){
   try{
     const rows=await db("real_trading_state?id=eq.singleton&select=*&limit=1");
     const state=rows?.[0]||null;
     const openTrades=await db("real_trades?status=eq.open&select=symbol,side,signal_type,margin_usd,leverage,notional_usd,entry_price,stop_price,target_price,test_mode,bingx_order_id,created_at&order=created_at.desc");
     const recentTrades=await db("real_trades?status=neq.open&select=symbol,side,signal_type,status,margin_usd,leverage,net_pnl_usd,test_mode,bingx_order_id,reject_reason,close_reason,created_at,closed_at&order=created_at.desc&limit=30");
     return Response.json({ok:true,state,open_trades:openTrades||[],recent_trades:recentTrades||[]},{headers:CORS});
   }catch(e){return Response.json({ok:false,error:"실거래 상태 조회 실패"},{status:502,headers:CORS})}
 }

 if(body.action==="trade_history"){
   try{
     // 페이지를 열 때 BingX의 현재 포지션 + 실제 Position History를 먼저 동기화한다.
     // 봇 내부 주문(real_trades)은 절대 이 화면의 거래내역으로 사용하지 않는다.
     const sync=await syncActualBingxHistory();
     const page=Math.max(1,Math.floor(Number(body.page||1))),limit=Math.max(1,Math.min(50,Math.floor(Number(body.limit||20)))),offset=(page-1)*limit;
     const all=await db("bingx_trade_history?status=in.(open,closed)&select=*&order=opened_at.desc&limit=2000");
     const mapped=(all||[]).map((x:any)=>{
       const raw=x.raw||{},entry=n(x.entry_price),close=n(x.close_price),qty=n(x.quantity),margin=n(x.margin_usd),lev=n(x.leverage)||1;
       const notional=n(raw.positionValue??raw.openAmt??raw.totalOpen??raw.openValue)||(entry&&qty?entry*qty:0);
       const fee=n(x.fee_usd),closed=x.status==="closed";
       const pnl=closed?(x.realized_pnl_usd==null?null:n(x.realized_pnl_usd)):(x.unrealized_pnl_usd==null?null:n(x.unrealized_pnl_usd));
       const roi=margin>0&&pnl!=null?pnl/margin*100:null;
       const base=notional>0&&pnl!=null?pnl/notional*100:null;
       return {id:x.external_id,position_id:x.position_id,signal_id:null,
         symbol:String(x.symbol||"").replace("-USDT",""),bingx_symbol:x.symbol,side:x.side,
         signal_type:"BingX API",status:x.status,test_mode:false,margin_usd:margin||null,leverage:lev||null,
         notional_usd:notional||null,quantity:qty||null,entry_price:entry||null,stop_price:null,target_price:null,
         fill_price:entry||null,fee_usd:fee||null,close_price:close||null,close_reason:closed?"BingX 포지션 종료":null,
         net_pnl_usd:pnl,reject_reason:null,created_at:x.opened_at,updated_at:x.synced_at,closed_at:x.closed_at,
         unrealized_pnl_usd:closed?null:pnl,base_return_pct:base,margin_return_pct:roi,r_multiple:null,
         evaluation:!closed?"진행 중":pnl!=null&&pnl>0?"성공":pnl!=null&&pnl<0?"실패":"중립",raw};
     });
     const rows=mapped.slice(offset,offset+limit),closed=mapped.filter((x:any)=>x.status==="closed"&&x.net_pnl_usd!=null);
     const pnls=closed.map((x:any)=>n(x.net_pnl_usd)),rois=closed.filter((x:any)=>n(x.margin_usd)>0).map((x:any)=>n(x.net_pnl_usd)/n(x.margin_usd)*100);
     const wins=pnls.filter((x:number)=>x>0),losses=pnls.filter((x:number)=>x<0),totalPnl=pnls.reduce((a:number,v:number)=>a+v,0);
      const totalFee=closed.reduce((a:number,x:any)=>a+Math.abs(n(x.fee_usd)),0);
      const winPnl=wins.reduce((a:number,v:number)=>a+v,0),lossPnl=losses.reduce((a:number,v:number)=>a+v,0);
      const openPnl=mapped.filter((x:any)=>x.status==="open"&&x.net_pnl_usd!=null).reduce((a:number,x:any)=>a+n(x.net_pnl_usd),0);
      const currentBalance=100+totalPnl+openPnl;
     let equity=100,peak=100,maxDd=0;[...closed].reverse().forEach((x:any)=>{equity+=n(x.net_pnl_usd);peak=Math.max(peak,equity);if(peak>0)maxDd=Math.max(maxDd,(peak-equity)/peak*100)});
     return Response.json({ok:true,source:"bingx_position_history",sync,page,limit,total:mapped.length,pages:Math.max(1,Math.ceil(mapped.length/limit)),rows,stats:{
       closed:closed.length,wins:wins.length,losses:losses.length,win_rate:closed.length?wins.length/closed.length*100:0,
       total_pnl_usd:totalPnl,avg_pnl_usd:closed.length?totalPnl/closed.length:0,
       avg_margin_return_pct:rois.length?rois.reduce((a:number,v:number)=>a+v,0)/rois.length:0,
       account_return_pct:totalPnl,profit_factor:losses.length?wins.reduce((a:number,v:number)=>a+v,0)/Math.abs(losses.reduce((a:number,v:number)=>a+v,0)):wins.length?null:0,
       max_drawdown_pct:maxDd,total_fee_usd:totalFee,win_pnl_usd:winPnl,loss_pnl_usd:lossPnl,current_balance_usd:currentBalance
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
