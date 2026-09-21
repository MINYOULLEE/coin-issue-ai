export const RLAB_MODEL_VERSION='rlab_seed_observer_v1';

const clamp=(n,a=0,b=1)=>Math.max(a,Math.min(b,Number(n)||0));

export function normalizeProbabilities(input={}){
  const long=clamp(input.long),short=clamp(input.short),noTrade=clamp(input.no_trade);
  const total=long+short+noTrade;
  if(!(total>0))return {long:1/3,short:1/3,no_trade:1/3};
  return {long:long/total,short:short/total,no_trade:noTrade/total};
}

export function seedDecision({answer=null,micro=null,bSignal=null}={}){
  let base={long:.25,short:.25,no_trade:.5};
  const inputs=[];
  if(answer&&Array.isArray(answer.probabilities)&&answer.probabilities.length===3){
    const classes=Array.isArray(answer.classes)&&answer.classes.length===3?answer.classes:[-1,0,1];
    const mapped={long:0,short:0,no_trade:0};
    for(let i=0;i<3;i++){
      if(Number(classes[i])>0)mapped.long=Number(answer.probabilities[i])||0;
      else if(Number(classes[i])<0)mapped.short=Number(answer.probabilities[i])||0;
      else mapped.no_trade=Number(answer.probabilities[i])||0;
    }
    base=normalizeProbabilities(mapped);inputs.push('A_TREE');
  }
  if(micro){
    const m=normalizeProbabilities({long:Number(micro.long)/100,short:Number(micro.short)/100,no_trade:Number(micro.range)/100});
    base=normalizeProbabilities({long:.7*base.long+.3*m.long,short:.7*base.short+.3*m.short,no_trade:.7*base.no_trade+.3*m.no_trade});
    inputs.push('MARKET_MICRO');
  }
  if(bSignal?.side==='long'||bSignal?.side==='short'){
    const vote=bSignal.side;
    base=normalizeProbabilities({long:base.long+(vote==='long'?.2:0),short:base.short+(vote==='short'?.2:0),no_trade:base.no_trade*.85});
    inputs.push('B_SIGNAL');
  }
  const ranked=Object.entries(base).sort((a,b)=>b[1]-a[1]);
  const directional=Math.max(base.long,base.short),spread=ranked[0][1]-ranked[1][1];
  const action=directional<.55||spread<.10?'no_trade':base.long>base.short?'long':'short';
  return {probabilities:base,action,confidence:base[action],inputs};
}

export function scoreOutcome({action,entry,exit,high,low,horizonHours,feeRate=.0005,slippageRate=.0002,fundingHourly=.0000125}){
  for(const v of [entry,exit,high,low])if(!(Number(v)>0))throw Error('invalid shadow price');
  const longGross=exit/entry-1,shortGross=entry/exit-1;
  const cost=2*(feeRate+slippageRate)+fundingHourly*horizonHours;
  const longNet=longGross-cost,shortNet=shortGross-cost;
  const longMae=Math.min(0,low/entry-1),longMfe=Math.max(0,high/entry-1);
  const shortMae=Math.min(0,entry/high-1),shortMfe=Math.max(0,entry/low-1);
  const bothLose=longNet<=0&&shortNet<=0;
  const net=action==='long'?longNet:action==='short'?shortNet:0;
  const mae=action==='long'?longMae:action==='short'?shortMae:0;
  const mfe=action==='long'?longMfe:action==='short'?shortMfe:0;
  const successful=action==='no_trade'?bothLose:net>0;
  return {net_return_pct:net*100,gross_return_pct:(action==='long'?longGross:action==='short'?shortGross:0)*100,mae_pct:mae*100,mfe_pct:mfe*100,cost_pct:cost*100,successful,counterfactual:{long_net_pct:longNet*100,short_net_pct:shortNet*100,no_trade_net_pct:0}};
}
