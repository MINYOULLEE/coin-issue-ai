import {createHmac} from 'node:crypto';
import {positionStatusText} from './telegram_position_status.mjs';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export async function managedPositionSnapshot(accountId,{credentials,fetchImpl=globalThis.fetch,now=()=>Date.now()}) {
 try {
  if(!uuid.test(String(accountId)))throw Error('invalid account');
  const {api_key,secret_key}=await credentials(accountId);
  if(!api_key||!secret_key)throw Error('missing managed credentials');
  const query=`recvWindow=5000&timestamp=${now()}`,signature=createHmac('sha256',secret_key).update(query).digest('hex');
  const r=await fetchImpl(`https://open-api.bingx.com/openApi/swap/v2/user/positions?${query}&signature=${signature}`,{method:'GET',headers:{'X-BX-APIKEY':api_key},signal:AbortSignal.timeout(8000)});
  const j=await r.json();if(!r.ok||Number(j.code)!==0)throw Error('exchange read failed');
  const rows=Array.isArray(j.data)?j.data:j.data?.positions;if(!Array.isArray(rows))throw Error('invalid positions');
  const positions=[];
  for(const p of rows){const raw=p.positionAmt??p.positionAmount,q=raw==null||String(raw).trim()===''?NaN:Number(raw);if(!Number.isFinite(q))throw Error('invalid quantity');if(q===0)continue;
   // Return only display fields; never credentials, signatures or full exchange responses.
   const out={};for(const k of ['symbol','positionSide','positionAmt','positionAmount','leverage','unrealizedProfit','unrealizedPnl','initialMargin','positionMargin','margin','avgPrice','entryPrice','markPrice','liquidationPrice'])if(p[k]!=null)out[k]=p[k];positions.push(out);
  }
  return {ok:true,positions,checkedAt:new Date(now()).toISOString()};
 }catch{return {ok:false,positions:null,error:'진행 포지션 조회 실패 · 잠시 후 다시 눌러주세요.'};}
}
export function managedPositionPages(header,snapshot,footer='') {
 const time=snapshot.ok?new Date(snapshot.checkedAt).toLocaleString('sv-SE',{timeZone:'Asia/Bangkok',hour12:false}):'';
 const sections=!snapshot.ok?[snapshot.error]:[`<b>진행 중 ${snapshot.positions.length}건</b> · 계정 전체(수동 포함)\n조회 ${time} 태국시간`,...(snapshot.positions.length?snapshot.positions.map(p=>positionStatusText(p)):['열린 포지션 없음'])];
 const pages=[];let page=header;
 for(const block of [...sections,footer].filter(Boolean)){
  if((page+'\n\n'+block).length>3800){pages.push(page);page=header;}
  page+='\n\n'+block;
 }
 if(page)pages.push(page);return pages;
}
