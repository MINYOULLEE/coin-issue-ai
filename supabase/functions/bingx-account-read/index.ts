import { createHmac } from "node:crypto";
import JSONBig from "npm:json-bigint@1.0.0";

const JSONBigParse = JSONBig({ storeAsString: true });
const API_KEY = Deno.env.get("BINGX_API_KEY") || "";
const SECRET_KEY = Deno.env.get("BINGX_SECRET_KEY") || "";
const PROJECT_URL = Deno.env.get("SUPABASE_URL") || "";
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const BASE = {
  "prod-live": ["https://open-api.bingx.com", "https://open-api.bingx.pro"],
};

function isNetworkOrTimeout(e: unknown): boolean {
  if (e instanceof TypeError) return true;
  if (e instanceof DOMException && e.name === "AbortError") return true;
  if (e instanceof Error && e.name === "TimeoutError") return true;
  return false;
}

function validateParams(params: Record<string, unknown>): void {
  const FORBIDDEN = /[&=?#\r\n]/;
  for (const [k, v] of Object.entries(params)) {
    const s = String(v);
    if (FORBIDDEN.test(s)) throw new Error(`Param "${k}" has forbidden char in: "${s}"`);
  }
}

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
      const json = JSONBigParse.parse(await res.text());
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
  if (!r.ok) throw new Error("db " + path + " " + r.status + " " + await r.text());
  return r.status === 204 ? null : await r.json();
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
 if(!await validSession(req.headers.get("x-dashboard-session")||""))return Response.json({ok:false,locked:true,error:"잠금 해제가 필요합니다."},{status:401,headers:CORS});

 // 실거래 긴급 정지 스위치 상태 조회
 if(body.action==="trading_state"){
   try{
     const rows=await db("real_trading_state?id=eq.singleton&select=*&limit=1");
     const state=rows?.[0]||null;
     const openTrades=await db("real_trades?status=eq.open&select=symbol,side,signal_type,margin_usd,leverage,notional_usd,entry_price,stop_price,target_price,test_mode,created_at&order=created_at.desc");
     const recentTrades=await db("real_trades?status=neq.open&select=symbol,side,signal_type,status,margin_usd,leverage,net_pnl_usd,test_mode,reject_reason,close_reason,created_at,closed_at&order=created_at.desc&limit=30");
     return Response.json({ok:true,state,open_trades:openTrades||[],recent_trades:recentTrades||[]},{headers:CORS});
   }catch(e){return Response.json({ok:false,error:"실거래 상태 조회 실패"},{status:502,headers:CORS})}
 }

 // 긴급 정지 / 재개 토글. body.enabled: boolean
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
