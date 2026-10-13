import {allHistoryPages} from './history_pages.mjs';
const number=v=>v==null||String(v).trim()===''?null:Number.isFinite(Number(v))?Number(v):null;
export async function managedSettlements(sb,accountId){
 return allHistoryPages(async(offset,limit)=>{
  const {data,error}=await sb.from('managed_bingx_trades').select('id,status,realized_pnl_usdt').eq('account_id',accountId).eq('status','closed').order('id').range(offset,offset+limit-1);
  if(error)throw error;if(!Array.isArray(data))throw Error('invalid managed history page');
  return data.map(row=>({...row,external_id:String(row.id)}));
 });
}
export function managedBalanceSummary(account,closed){
 const start=number(account.starting_equity_usdt),equity=number(account.current_equity_usdt);
 let net=0,pending=0,settled=0;
 for(const row of closed){if(row.status!=='closed')continue;const pnl=number(row.realized_pnl_usdt);if(pnl==null){pending++;continue;}net+=pnl;settled++;}
 return {start,equity,net,realized:start==null?null:start+net,pending,settled}; // Stored realized PnL is already net: never subtract fees again.
}
export function managedBalanceText(account,closed){
 const s=managedBalanceSummary(account,closed),money=v=>v==null?'조회 불가':'$'+v.toFixed(2),sign=s.net>=0?'+':'-';
 return `시작 기준금 <b>${money(s.start)}</b>\n실현 기준금 <b>${money(s.realized)}</b>${s.pending?' · 확정분만':''}\n현재 Equity <b>${money(s.equity)}</b> · 저장된 조회값\n실현 순손익 <b>${sign}$${Math.abs(s.net).toFixed(2)}</b> · 확정 ${s.settled}건${s.pending?' · 정산 대기 '+s.pending+'건':''}`;
}
