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
 const generic=error?.source==='supabase-http'&&(
  error?.status_code>=500||error?.status_code==null&&/timeout|dns|handshake/i.test(message)
 );
 if(!generic)return 'immediate';
 const snapshotAt=Date.parse(snapshot?.updated_at||'');
 const recovered=Number.isFinite(at)&&Number.isFinite(snapshotAt)&&snapshotAt>at&&['signals','execute','close'].every(id=>{
  const h=bHealth.find(x=>x.id===id),updated=Date.parse(h?.updated_at||'');
  return h?.payload?.ok===true&&Number.isFinite(updated)&&updated>at;
 });
 if(recovered)return 'recovered';
 return Number.isFinite(at)&&now-at<180000?'pending':'alert';
}
