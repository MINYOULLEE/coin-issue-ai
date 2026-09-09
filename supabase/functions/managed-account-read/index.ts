import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "https://esm.sh/@supabase/supabase-js@2.49.8";
import {createDashboardSessions,reserveLoginAttempt} from "../_shared/dashboard_sessions.mjs";

const URL=Deno.env.get("SUPABASE_URL")!;
const SERVICE=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const sb=createClient(URL,SERVICE,{auth:{persistSession:false}});
const sessions=createDashboardSessions("M");
const CORS={
  "Access-Control-Allow-Origin":"https://minyoullee.github.io",
  "Access-Control-Allow-Headers":"authorization, apikey, content-type, x-dashboard-session",
  "Access-Control-Allow-Methods":"POST, OPTIONS",
  "Cache-Control":"no-store"
};
const te=new TextEncoder();
function b64u(a:Uint8Array){return btoa(String.fromCharCode(...a)).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/g,"")}
function unb64(s:string){const p=s.replace(/-/g,"+").replace(/_/g,"/")+"===".slice((s.length+3)%4);return Uint8Array.from(atob(p),c=>c.charCodeAt(0))}
function same(a:string,b:string){if(a.length!==b.length)return false;let d=0;for(let i=0;i<a.length;i++)d|=a.charCodeAt(i)^b.charCodeAt(i);return d===0}
async function dashboardAuth(){const{data,error}=await sb.from("private_runtime_secrets").select("secret_value").eq("id","bingx_dashboard_auth").single();if(error)throw error;return data.secret_value}
async function passwordHash(password:string,a:any){const k=await crypto.subtle.importKey("raw",te.encode(password),"PBKDF2",false,["deriveBits"]),bits=await crypto.subtle.deriveBits({name:"PBKDF2",salt:unb64(a.password_salt),iterations:210000,hash:"SHA-256"},k,256);return b64u(new Uint8Array(bits))}

Deno.serve(async req=>{
  if(req.method==="OPTIONS")return new Response("ok",{headers:CORS});
  if(req.method!=="POST")return Response.json({ok:false},{status:405,headers:CORS});
  const body=await req.json().catch(()=>({}));
  if(body.action==="login"){
    try{
      const auth=await dashboardAuth();
      const budget=await reserveLoginAttempt(req,"M",auth.session_secret,async params=>{const{data,error}=await sb.rpc("dashboard_login_attempt",params);if(error)throw error;return data});
      if(!budget.allowed)return Response.json({ok:false,error:"로그인 시도 한도 초과 · 잠시 후 다시 시도하세요."},{status:429,headers:{...CORS,"Retry-After":String(budget.retry_after)}});
      const password=String(body.password||"");
      if(password.length>1024)return Response.json({ok:false,error:"invalid password length"},{status:400,headers:CORS});
      if(!same(await passwordHash(password,auth),auth.password_hash))return Response.json({ok:false,error:"비밀번호가 맞지 않습니다."},{status:401,headers:CORS});
      return Response.json({ok:true,session:sessions.issue(auth.session_secret),expires_in:14400},{headers:CORS});
    }catch{return Response.json({ok:false,error:"로그인 보호 상태 확인 실패 · 잠시 후 다시 시도하세요."},{status:503,headers:CORS})}
  }
  let auth:any;
  try{auth=await dashboardAuth()}catch{return Response.json({ok:false,error:"인증 설정 오류"},{status:503,headers:CORS})}
  if(!sessions.valid(req.headers.get("x-dashboard-session")||"",auth.session_secret))return Response.json({ok:false,locked:true,error:"잠금 해제가 필요합니다."},{status:401,headers:CORS});

  if(body.action==="overview"){
    const{data,error}=await sb.from("managed_bingx_accounts").select("id,display_name,assigned_plan,starting_equity_usdt,current_equity_usdt,status,live_enabled,alerts_enabled,last_synced_at").order("display_name");
    if(error)return Response.json({ok:false,error:"연동 계정 목록 조회 실패"},{status:502,headers:CORS});
    return Response.json({ok:true,accounts:data||[]},{headers:CORS});
  }
  if(body.action==="trades"){
    const accountId=String(body.account_id||"");
    if(!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(accountId))return Response.json({ok:false,error:"invalid account"},{status:400,headers:CORS});
    const page=Math.max(1,Math.floor(Number(body.page)||1)),limit=Math.min(50,Math.max(1,Math.floor(Number(body.limit)||20))),from=(page-1)*limit;
    const[{data:account,error:accountError},{data,count,error}]=await Promise.all([
      sb.from("managed_bingx_accounts").select("id,display_name,assigned_plan").eq("id",accountId).maybeSingle(),
      sb.from("managed_bingx_trades").select("id,assigned_plan,symbol,side,status,quantity,leverage,margin_usdt,entry_price,close_price,realized_pnl_usdt,fee_usdt,opened_at,closed_at,created_at",{count:"exact"}).eq("account_id",accountId).order("created_at",{ascending:false}).range(from,from+limit-1)
    ]);
    if(accountError||error)return Response.json({ok:false,error:"거래내역 조회 실패"},{status:502,headers:CORS});
    if(!account)return Response.json({ok:false,error:"계정을 찾을 수 없습니다."},{status:404,headers:CORS});
    return Response.json({ok:true,account,page,limit,total:count||0,pages:Math.max(1,Math.ceil((count||0)/limit)),rows:data||[]},{headers:CORS});
  }
  return Response.json({ok:false,error:"unknown action"},{status:400,headers:CORS});
});
