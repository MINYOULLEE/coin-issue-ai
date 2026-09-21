import 'jsr:@supabase/functions-js/edge-runtime.d.ts';
import {createClient} from 'https://esm.sh/@supabase/supabase-js@2.49.8';
import {RLAB_MODEL_VERSION,seedDecision,scoreOutcome} from '../_shared/rlcd_shadow.mjs';

const URL=Deno.env.get('SUPABASE_URL')!;
const KEY=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
const sb=createClient(URL,KEY,{auth:{persistSession:false}});
const HORIZONS=[1,4,24];
const CORS={'Content-Type':'application/json','Cache-Control':'no-store','Access-Control-Allow-Origin':'https://minyoullee.github.io','Access-Control-Allow-Headers':'authorization, apikey, content-type, x-scheduler-key','Access-Control-Allow-Methods':'POST, OPTIONS'};

async function authorized(req:Request){
  const key=req.headers.get('x-scheduler-key');if(!key)return false;
  const {data}=await sb.from('private_runtime_secrets').select('secret_value').eq('id','scheduler_auth').maybeSingle();
  return key===(data?.secret_value as any)?.key;
}
function hourKey(d=new Date()){return new Date(Math.floor(d.getTime()/3600000)*3600000).toISOString()}

async function createDecisions(){
  const [{data:snapshot,error:snapshotError},{data:bRows,error:bError}]=await Promise.all([
    sb.from('coin_snapshots').select('payload,updated_at').eq('id','live').maybeSingle(),
    sb.from('plan_b_signals').select('id,symbol,side,status,confirmed_at,strategy_id').eq('status','active')
  ]);
  if(snapshotError||!snapshot?.payload?.market)throw Error(snapshotError?.message||'live market snapshot missing');
  if(bError)throw Error(bError.message);
  const market=snapshot.payload.market as Record<string,any>,bBySymbol=new Map((bRows||[]).map((x:any)=>[x.symbol,x]));
  const decisionBoundary=hourKey(),decidedAt=new Date().toISOString(),rows:any[]=[];
  for(const [symbol,m] of Object.entries(market)){
    const entry=Number(m?.price);if(!(entry>0))continue;
    const answer=m?.answer_mdd30?{...m.answer_mdd30,classes:[-1,0,1]}:null;
    const result=seedDecision({answer,micro:m?.micro_scenarios,bSignal:bBySymbol.get(symbol)||null});
    for(const horizon of HORIZONS)rows.push({
      decision_key:`${RLAB_MODEL_VERSION}:${symbol}:${decisionBoundary}:${horizon}`,
      model_version:RLAB_MODEL_VERSION,symbol,decided_at:decidedAt,horizon_hours:horizon,matures_at:new Date(Date.parse(decidedAt)+horizon*3600000).toISOString(),
      p_long:result.probabilities.long,p_short:result.probabilities.short,p_no_trade:result.probabilities.no_trade,
      action:result.action,confidence:result.confidence,entry_price:entry,status:'pending',
      source_snapshot_at:snapshot.updated_at,
      inputs:{sources:result.inputs,a_answer:answer,b_signal:bBySymbol.get(symbol)||null,market:{rsi:m?.rsi,volume_ratio:m?.volume_ratio,atr_1h_pct:m?.atr_1h_pct,funding_rate_pct:m?.funding_rate_pct,micro_scenarios:m?.micro_scenarios}}
    });
  }
  const {error}=await sb.from('rlcd_shadow_decisions').upsert(rows,{onConflict:'decision_key',ignoreDuplicates:true});
  if(error)throw Error(error.message);return rows.length;
}

async function candles(symbol:string,start:number,end:number){
  const u=`https://data-api.binance.vision/api/v3/klines?symbol=${symbol}USDT&interval=5m&startTime=${Math.floor(start/300000)*300000}&endTime=${end}&limit=300`;
  const r=await fetch(u,{signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error(`${symbol} candles ${r.status}`);
  const rows=await r.json();if(!Array.isArray(rows)||!rows.length)throw Error(`${symbol} candles empty`);return rows;
}
async function scoreMatured(){
  const {data,error}=await sb.from('rlcd_shadow_decisions').select('*').eq('status','pending').lte('matures_at',new Date().toISOString()).order('matures_at').limit(100);
  if(error)throw Error(error.message);let scored=0;const failures:any[]=[];
  for(const row of data||[]){
    try{
      const end=Date.parse(row.decided_at)+Number(row.horizon_hours)*3600000;
      const bars=await candles(row.symbol,Date.parse(row.decided_at),end);
      const eligible=bars.filter((b:any[])=>Number(b[6])<=end);if(!eligible.length)continue;
      const exit=Number(eligible.at(-1)[4]),high=Math.max(...eligible.map((b:any[])=>Number(b[2]))),low=Math.min(...eligible.map((b:any[])=>Number(b[3])));
      const result=scoreOutcome({action:row.action,entry:Number(row.entry_price),exit,high,low,horizonHours:Number(row.horizon_hours)});
      const {error:updateError}=await sb.from('rlcd_shadow_decisions').update({status:'scored',exit_price:exit,scored_at:new Date().toISOString(),...result}).eq('id',row.id).eq('status','pending');
      if(updateError)throw Error(updateError.message);scored++;
    }catch(e){failures.push({id:row.id,error:e instanceof Error?e.message:String(e)});}
  }
  return {scored,failures};
}

Deno.serve(async(req:Request)=>{
  if(req.method==='OPTIONS')return new Response('ok',{headers:CORS});
  if(req.method!=='POST')return new Response(JSON.stringify({ok:false,error:'POST required'}),{status:405,headers:CORS});
  let body:any={};try{body=await req.json()}catch{}
  if(body.action==='dashboard'){
    const [{data:recent,error:recentError},{data:calibration,error:calibrationError}]=await Promise.all([
      sb.from('rlcd_shadow_decisions').select('action,status,net_return_pct,successful,decided_at').order('decided_at',{ascending:false}).limit(5000),
      sb.from('rlcd_shadow_calibration').select('*').order('horizon_hours').order('confidence_bucket')
    ]);
    if(recentError||calibrationError)return new Response(JSON.stringify({ok:false,error:(recentError||calibrationError)?.message}),{status:502,headers:CORS});
    const rows=recent||[],scored=rows.filter((x:any)=>x.status==='scored'),pending=rows.filter((x:any)=>x.status==='pending');
    const stats={total:rows.length,scored:scored.length,pending:pending.length,wins:scored.filter((x:any)=>x.successful).length,mean_net_return_pct:scored.length?scored.reduce((a:number,x:any)=>a+Number(x.net_return_pct||0),0)/scored.length:null,last_decision_at:rows[0]?.decided_at||null,actions:{long:rows.filter((x:any)=>x.action==='long').length,short:rows.filter((x:any)=>x.action==='short').length,no_trade:rows.filter((x:any)=>x.action==='no_trade').length}};
    return new Response(JSON.stringify({ok:true,name:'R-Lab',model:RLAB_MODEL_VERSION,mode:'SHADOW_ONLY',stats,calibration:calibration||[]}),{headers:CORS});
  }
  if(!(await authorized(req)))return new Response(JSON.stringify({ok:false,error:'forbidden'}),{status:403,headers:CORS});
  try{const scored=await scoreMatured(),created=await createDecisions();return new Response(JSON.stringify({ok:scored.failures.length===0,model:RLAB_MODEL_VERSION,created,scored}),{headers:CORS});}
  catch(e){return new Response(JSON.stringify({ok:false,error:e instanceof Error?e.message:String(e)}),{status:500,headers:CORS});}
});
