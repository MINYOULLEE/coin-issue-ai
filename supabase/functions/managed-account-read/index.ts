import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "https://esm.sh/@supabase/supabase-js@2.49.8";
import postgres from "https://deno.land/x/postgresjs@v3.4.5/mod.js";
import {createHmac} from "node:crypto";
import {createDashboardSessions,reserveLoginAttempt} from "../_shared/dashboard_sessions.mjs";

const URL=Deno.env.get("SUPABASE_URL")!;
const SERVICE=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const sb=createClient(URL,SERVICE,{auth:{persistSession:false}});
const sql=postgres(Deno.env.get("SUPABASE_DB_URL")!,{prepare:false,max:1});
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
function cleanName(value:unknown){return String(value||"").replace(/[\r\n\t]/g," ").trim()}
function validAccountId(value:unknown){const id=String(value||"");return /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)?id:""}
async function bingxRead(apiKey:string,secret:string,path:string,params:Record<string,string|number>={}){
  const all={...params,recvWindow:5000,timestamp:Date.now()},query=Object.keys(all).sort().map(k=>k+"="+encodeURIComponent(String(all[k]))).join("&");
  const signature=createHmac("sha256",secret).update(query).digest("hex");
  const response=await fetch("https://open-api.bingx.com"+path+"?"+query+"&signature="+signature,{headers:{"X-BX-APIKEY":apiKey},signal:AbortSignal.timeout(8000)});
  const json=await response.json().catch(()=>({}));
  if(!response.ok||Number(json.code)!==0)throw Error("BingX 연결 확인 실패: "+String(json.code??response.status)+" "+String(json.msg??json.message??"").slice(0,100));
  return json.data;
}
function positivePositions(raw:any){const rows=Array.isArray(raw)?raw:raw?.positions;if(!Array.isArray(rows))throw Error("BingX 포지션 응답 형식 오류");return rows.filter((p:any)=>{const q=Number(p.positionAmt??p.positionAmount);if(!Number.isFinite(q))throw Error("BingX 포지션 수량 오류");return Math.abs(q)>0})}

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

  if(body.action==="register"){
    const displayName=cleanName(body.display_name),plan=String(body.assigned_plan||"").toUpperCase(),start=Number(body.starting_equity_usdt),apiKey=String(body.api_key||"").trim(),secretKey=String(body.secret_key||"").trim();
    if(displayName.length<1||displayName.length>60)return Response.json({ok:false,error:"이름은 1~60자로 입력하세요."},{status:400,headers:CORS});
    if(!["A","B"].includes(plan))return Response.json({ok:false,error:"A 또는 B 플랜을 선택하세요."},{status:400,headers:CORS});
    if(!Number.isFinite(start)||start<=0||start>100000000)return Response.json({ok:false,error:"시작금액을 정확히 입력하세요."},{status:400,headers:CORS});
    if(apiKey.length<16||apiKey.length>256||secretKey.length<16||secretKey.length>256)return Response.json({ok:false,error:"BingX API Key와 Secret Key 형식을 확인하세요."},{status:400,headers:CORS});
    try{
      const [balanceRaw,mode,positions]=await Promise.all([
        bingxRead(apiKey,secretKey,"/openApi/swap/v3/user/balance"),
        bingxRead(apiKey,secretKey,"/openApi/swap/v1/positionSide/dual"),
        bingxRead(apiKey,secretKey,"/openApi/swap/v2/user/positions")
      ]);
      if(String(mode?.dualSidePosition)!=="true")return Response.json({ok:false,error:"BingX 선물 계정이 헤지 모드가 아닙니다. 헤지 모드로 바꾼 뒤 다시 연결하세요."},{status:409,headers:CORS});
      const open=positivePositions(positions);
      if(open.length)return Response.json({ok:false,error:"기존 선물 포지션이 있어 자동 실행 연결을 막았습니다. 포지션 정리 후 다시 연결하세요."},{status:409,headers:CORS});
      const balances=Array.isArray(balanceRaw)?balanceRaw:Array.isArray(balanceRaw?.balance)?balanceRaw.balance:[balanceRaw?.balance||balanceRaw],usdt=balances.find((b:any)=>b?.asset==="USDT");
      const equity=Number(usdt?.equity),available=Number(usdt?.availableMargin);
      if(!Number.isFinite(equity)||equity<0||!Number.isFinite(available)||available<0)throw Error("BingX USDT 선물 잔고를 확인할 수 없습니다.");
      const accountId=crypto.randomUUID();
      await sql.begin(async tx=>{
        const apiRows=await tx`select vault.create_secret(${apiKey}, ${"managed_"+accountId+"_api"}, ${"Managed BingX API key"}) as id`;
        const secretRows=await tx`select vault.create_secret(${secretKey}, ${"managed_"+accountId+"_secret"}, ${"Managed BingX secret key"}) as id`;
        await tx`insert into public.managed_bingx_accounts(id,display_name,assigned_plan,starting_equity_usdt,current_equity_usdt,status,live_enabled,alerts_enabled,api_key_secret_id,secret_key_secret_id,last_synced_at,last_error)
          values(${accountId}::uuid,${displayName},${plan},${start},${equity},'connected',false,false,${apiRows[0].id}::uuid,${secretRows[0].id}::uuid,now(),null)`;
      });
      return Response.json({ok:true,account:{id:accountId,display_name:displayName,assigned_plan:plan,starting_equity_usdt:start,current_equity_usdt:equity,status:"connected",live_enabled:false},preflight:{bingx_authenticated:true,hedge_mode:true,open_positions:0,available_margin_usdt:available},execution:"locked_until_account_scoped_executor"},{headers:CORS});
    }catch(e){return Response.json({ok:false,error:String(e instanceof Error?e.message:e).slice(0,300)},{status:502,headers:CORS});}
  }

  if(body.action==="overview"){
    const{data,error}=await sb.from("managed_bingx_accounts").select("id,display_name,assigned_plan,starting_equity_usdt,current_equity_usdt,status,live_enabled,alerts_enabled,last_synced_at,last_error").order("display_name");
    if(error)return Response.json({ok:false,error:"연동 계정 목록 조회 실패"},{status:502,headers:CORS});
    return Response.json({ok:true,accounts:data||[]},{headers:CORS});
  }
  if(body.action==="verify"){
    const accountId=validAccountId(body.account_id);
    if(!accountId)return Response.json({ok:false,error:"invalid account"},{status:400,headers:CORS});
    try{
      const rows=await sql`select a.id,a.live_enabled,k.decrypted_secret as api_key,s.decrypted_secret as secret_key
        from public.managed_bingx_accounts a
        left join vault.decrypted_secrets k on k.id=a.api_key_secret_id
        left join vault.decrypted_secrets s on s.id=a.secret_key_secret_id
        where a.id=${accountId}::uuid limit 1`;
      const account=rows[0];
      if(!account)return Response.json({ok:false,error:"계정을 찾을 수 없습니다."},{status:404,headers:CORS});
      if(!account.api_key||!account.secret_key)throw Error("저장된 BingX 키를 찾을 수 없습니다.");
      const[balanceRaw,mode,positionsRaw]=await Promise.all([
        bingxRead(String(account.api_key),String(account.secret_key),"/openApi/swap/v3/user/balance"),
        bingxRead(String(account.api_key),String(account.secret_key),"/openApi/swap/v1/positionSide/dual"),
        bingxRead(String(account.api_key),String(account.secret_key),"/openApi/swap/v2/user/positions")
      ]);
      const balances=Array.isArray(balanceRaw)?balanceRaw:Array.isArray(balanceRaw?.balance)?balanceRaw.balance:[balanceRaw?.balance||balanceRaw],usdt=balances.find((b:any)=>b?.asset==="USDT"),equity=Number(usdt?.equity),available=Number(usdt?.availableMargin),hedge=String(mode?.dualSidePosition)==="true",open=positivePositions(positionsRaw);
      if(!Number.isFinite(equity)||equity<0||!Number.isFinite(available)||available<0)throw Error("BingX USDT 선물 잔고를 확인할 수 없습니다.");
      if(!hedge)throw Error("BingX 선물 계정이 헤지 모드가 아닙니다.");
      const checkedAt=new Date().toISOString();
      const{error}=await sb.from("managed_bingx_accounts").update({current_equity_usdt:equity,status:"connected",last_synced_at:checkedAt,last_error:null,updated_at:checkedAt}).eq("id",accountId);
      if(error)throw Error("연결 상태 저장 실패");
      return Response.json({ok:true,connection:{bingx_authenticated:true,usdt_futures_balance:true,hedge_mode:true,current_equity_usdt:equity,available_margin_usdt:available,open_positions:open.length,live_enabled:!!account.live_enabled,checked_at:checkedAt}},{headers:CORS});
    }catch(e){const message=String(e instanceof Error?e.message:e).slice(0,200);await sb.from("managed_bingx_accounts").update({status:"error",last_error:message,last_synced_at:new Date().toISOString(),updated_at:new Date().toISOString()}).eq("id",accountId);return Response.json({ok:false,error:message},{status:502,headers:CORS})}
  }
  if(body.action==="update_start"){
    const accountId=validAccountId(body.account_id),start=Number(body.starting_equity_usdt);
    if(!accountId)return Response.json({ok:false,error:"invalid account"},{status:400,headers:CORS});
    if(!Number.isFinite(start)||start<=0||start>100000000)return Response.json({ok:false,error:"시작금액을 정확히 입력하세요."},{status:400,headers:CORS});
    const{data,error}=await sb.from("managed_bingx_accounts").update({starting_equity_usdt:start,updated_at:new Date().toISOString()}).eq("id",accountId).select("id,starting_equity_usdt").maybeSingle();
    if(error)return Response.json({ok:false,error:"시작금액 수정 실패"},{status:502,headers:CORS});
    if(!data)return Response.json({ok:false,error:"계정을 찾을 수 없습니다."},{status:404,headers:CORS});
    return Response.json({ok:true,account:data},{headers:CORS});
  }
  if(body.action==="disconnect"){
    const accountId=validAccountId(body.account_id);
    if(!accountId)return Response.json({ok:false,error:"invalid account"},{status:400,headers:CORS});
    try{
      await sql.begin(async tx=>{
        const accounts=await tx`select id,live_enabled,api_key_secret_id,secret_key_secret_id from public.managed_bingx_accounts where id=${accountId}::uuid for update`,account=accounts[0];
        if(!account)throw Error("계정을 찾을 수 없습니다.");
        if(account.live_enabled)throw Error("자동매매가 켜진 계정은 연동을 취소할 수 없습니다.");
        const active=await tx`select count(*)::integer as count from public.managed_bingx_trades where account_id=${accountId}::uuid and status in ('reserved','open','closing','unknown')`;
        if(Number(active[0]?.count)>0)throw Error("진행 중인 거래가 있어 연동을 취소할 수 없습니다.");
        const history=await tx`select count(*)::integer as count from public.managed_bingx_trades where account_id=${accountId}::uuid`;
        if(Number(history[0]?.count)>0)throw Error("거래 기록이 있는 계정은 기록 보존을 위해 삭제할 수 없습니다.");
        await tx`delete from public.managed_bingx_accounts where id=${accountId}::uuid`;
        await tx`delete from vault.secrets where id in (${account.api_key_secret_id}::uuid,${account.secret_key_secret_id}::uuid)`;
      });
      return Response.json({ok:true,disconnected:true},{headers:CORS});
    }catch(e){return Response.json({ok:false,error:String(e instanceof Error?e.message:e).slice(0,200)},{status:409,headers:CORS})}
  }
  if(body.action==="trades"){
    const accountId=validAccountId(body.account_id);
    if(!accountId)return Response.json({ok:false,error:"invalid account"},{status:400,headers:CORS});
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
