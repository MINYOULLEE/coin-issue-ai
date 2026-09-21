import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "https://esm.sh/@supabase/supabase-js@2.49.8";

const PROJECT_URL=Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const sb=createClient(PROJECT_URL,SERVICE_KEY,{auth:{persistSession:false}});
const CORS={"Access-Control-Allow-Origin":"https://minyoullee.github.io","Access-Control-Allow-Headers":"authorization, apikey, content-type","Access-Control-Allow-Methods":"POST, OPTIONS","Cache-Control":"no-store"};

// 주차별 기록: A/B 각 플랜의 "실현 기준 자산(시작 자본 + 확정 손익)"을 매주 스냅샷으로 저장한다.
// 실제 거래소 지갑 잔액이 아니라 각 플랜의 trade_history 응답이 계산한 기준 자산을 재사용한다.
async function currentEquity(plan:"A"|"B"):Promise<number>{
  const path=plan==="A"?"bingx-account-read":"plan-b-account-read";
  const r=await fetch(`${PROJECT_URL}/functions/v1/${path}`,{
    method:"POST",
    headers:{"Content-Type":"application/json",apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY},
    body:JSON.stringify({action:"trade_history",page:1,limit:1}),
  });
  const j=await r.json().catch(()=>({}));
  if(!r.ok||!j.ok)throw new Error(`${plan} equity lookup failed: `+(j?.error||r.status));
  // A and B history endpoints expose the same canonical realized-basis field.
  const value=j.stats?.current_balance_usd;
  if(typeof value!=="number"||!Number.isFinite(value))throw new Error(`${plan} equity value missing from stats`);
  return value;
}

async function captureOne(plan:"A"|"B"){
  const balance=await currentEquity(plan);
  const {data:existing,error:selErr}=await sb.from("weekly_equity_snapshots").select("week_no").eq("plan",plan).order("week_no",{ascending:false}).limit(1);
  if(selErr)throw new Error(selErr.message);
  const nextWeek=existing&&existing.length?existing[0].week_no+1:0;
  const label=nextWeek===0?"시작":`${nextWeek}주차`;
  const {error:insErr}=await sb.from("weekly_equity_snapshots").insert({plan,week_no:nextWeek,label,balance_usd:balance});
  if(insErr)throw new Error(insErr.message);
  return {plan,week_no:nextWeek,label,balance_usd:balance};
}

Deno.serve(async(req:Request)=>{
  if(req.method==="OPTIONS")return new Response("ok",{headers:CORS});
  if(req.method!=="POST")return Response.json({ok:false,error:"POST required"},{status:405,headers:CORS});
  let body:Record<string,unknown>={};try{body=await req.json()}catch{}

  if(body.action==="weekly_history"){
    const {data,error}=await sb.from("weekly_equity_snapshots").select("plan,week_no,label,balance_usd,captured_at").order("plan",{ascending:true}).order("week_no",{ascending:true});
    if(error)return Response.json({ok:false,error:error.message},{status:502,headers:CORS});
    return Response.json({ok:true,rows:data||[]},{headers:CORS});
  }

  if(body.action==="capture"){
    const key=req.headers.get("x-scheduler-key");
    if(!key)return Response.json({ok:false},{status:403,headers:CORS});
    const {data:secret,error:authError}=await sb.from("private_runtime_secrets").select("secret_value").eq("id","scheduler_auth").maybeSingle();
    if(authError||key!==(secret?.secret_value as any)?.key)return Response.json({ok:false},{status:403,headers:CORS});
    const results:any[]=[];
    for(const plan of ["A","B"] as const){
      try{results.push(await captureOne(plan));}
      catch(e){results.push({plan,error:e instanceof Error?e.message:String(e)});}
    }
    return Response.json({ok:results.every((r:any)=>!r.error),results},{headers:CORS});
  }

  return Response.json({ok:false,error:"unknown action"},{status:400,headers:CORS});
});
