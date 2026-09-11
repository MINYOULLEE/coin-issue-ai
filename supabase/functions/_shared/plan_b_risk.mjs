const H=3600000;

export function btcRegime(candles,boundary,lookbackHours=72,threshold=-0.06){
 if(!Number.isFinite(boundary)||boundary%H||!Array.isArray(candles))return {available:false,reason:'invalid_btc_history'};
 const byTime=new Map(candles.map(row=>[Number(row.t),row]));
 const latest=byTime.get(boundary-H),prior=byTime.get(boundary-(lookbackHours+1)*H);
 if(!latest||!prior||![latest.c,prior.c].every(v=>Number.isFinite(Number(v))&&Number(v)>0))return {available:false,reason:'missing_or_stale_btc_history'};
 const returnFraction=Number(latest.c)/Number(prior.c)-1;
 return {available:true,blocked:returnFraction<=threshold,returnFraction,latestCloseAt:latest.t+H,priorCloseAt:prior.t+H};
}

export function applyBtcEntryGuard(decisions,regime,protectedSymbols){
 const protectedSet=new Set(protectedSymbols),next={...decisions};
 for(const symbol of protectedSet){
  const d=next[symbol];if(!d)continue;
  const blocked=!regime.available||regime.blocked;
  next[symbol]={...d,side:blocked?null:d.side,diagnostic:{...(d.diagnostic||{}),btc_regime:{...regime,protected:true,entry_blocked:blocked}}};
 }
 return next;
}
