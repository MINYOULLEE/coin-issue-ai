// Read-only diagnostics. This module never changes trading authorization.
export function healthProblems({snapshot,bHealth=[],bState,now=Date.now()}) {
 const out={};
 for(const [name,s] of Object.entries(snapshot?.payload?.status||{})) {
  if(name==='클라우드 수집기')continue;
  if(s.ok===false||s.warning)out['news:'+name]=name+': '+(s.warning||s.error||'수집 실패');
 }
 if(snapshot?.payload?.signal_candidates?.entry_recovery?.ok===false)out.a_recovery='A 체결 복구 오류';
 const expected=['signals','close',...(bState?.enabled&&!bState?.test_mode?['execute']:[])];
 for(const id of expected){
  const h=bHealth.find(x=>x.id===id),age=now-Date.parse(h?.updated_at||'');
  if(!h||!Number.isFinite(age)||age>180000)out['B:'+id]='B '+id+' 상태 갱신이 3분 이상 지연되거나 기록이 없습니다.';
  else if(h.payload?.ok===false)out['B:'+id]='B '+id+' 오류: '+JSON.stringify(h.payload.errors||h.payload.recovery_errors||h.payload.error||h.payload.results||[]).slice(0,300);
 }
 return out;
}
export function healthTransitions(previous={},current={}){
 return {opened:Object.entries(current).filter(([k,v])=>previous[k]!==v),resolved:Object.keys(previous).filter(k=>!(k in current))};
}
export function outcomeErrors(result){return (result?.results||[]).filter(x=>x.error||x.ok===false);}

export function transportErrorDisposition({error,snapshot,bHealth=[],now=Date.now()}){
 const at=Date.parse(error?.created_at||''),message=String(error?.message||'');
 const source=String(error?.source||'');
 const transientTransport=(source==='supabase-http'||source==='plan-b-http')&&(
  error?.status_code>=500||
  error?.status_code==null&&/timeout|dns|handshake/i.test(message)||
  (error?.status_code===401||error?.status_code===403)&&(/scheduler authorization required/i.test(message)||/^\s*\{\s*"ok"\s*:\s*false\s*\}\s*$/i.test(message))
 );
 if(!transientTransport)return 'immediate';
 const snapshotAt=Date.parse(snapshot?.updated_at||'');
 const bRecovered=Number.isFinite(at)&&['signals','execute','close'].every(id=>{
  const h=bHealth.find(x=>x.id===id),updated=Date.parse(h?.updated_at||'');
  return h?.payload?.ok===true&&Number.isFinite(updated)&&updated>at;
 });
 // A collector heartbeat is unrelated to a Plan B Edge transport retry.  Requiring
 // it here caused an already-recovered B timeout to be announced as a live error.
 const recovered=source==='plan-b-http'
  ? bRecovered
  : bRecovered&&Number.isFinite(snapshotAt)&&snapshotAt>at;
 if(recovered)return 'recovered';
 return Number.isFinite(at)&&now-at<180000?'pending':'alert';
}
