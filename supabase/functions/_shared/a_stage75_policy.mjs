export const A_STAGE75 = Object.freeze({
  strategyId: 'answer_mdd30', version: 'mdd30_intraday_rally_guard_stage135_v1',
  assets: Object.freeze(['BTC','ETH','XRP','TRX','SOL']), leverage: 3,
  normalScale: 1.4, guardedScale: 1.05, maxGross: 2.24,
  stopFraction: .15, guardTrigger: .35, guardRecovery: .175,
  selectiveResizeThreshold: .0125,
  rallyGuard: Object.freeze({btcFirst:.005,breadthFirst:.0275,breadthCount:3,confirmHours:2,
    firstRemainingFraction:.05,btcSecond:.02,breadthSecond:.0375,secondRemainingFraction:0,
    symbols:Object.freeze(['ETH','XRP','SOL'])}),
});

const finitePositive=(value,name)=>{const x=Number(value);if(!Number.isFinite(x)||x<=0)throw Error(`invalid ${name}`);return x};

export function nextDrawdownGuard({equity,peak,active=false}){
  const e=finitePositive(equity,'A equity'),priorPeak=Math.max(e,finitePositive(peak||e,'A equity peak'));
  const drawdown=Math.max(0,1-e/priorPeak);
  const epsilon=1e-12;
  const nextActive=active ? drawdown>A_STAGE75.guardRecovery+epsilon : drawdown+epsilon>=A_STAGE75.guardTrigger;
  return {peak:priorPeak,equity:e,drawdown,active:nextActive,
    exposureScale:nextActive?A_STAGE75.guardedScale:A_STAGE75.normalScale};
}

export function stage75Target({baseExposure,equity,price,guardActive}){
  const base=Number(baseExposure);if(!Number.isFinite(base))throw Error('invalid A base exposure');
  const e=finitePositive(equity,'A equity'),p=finitePositive(price,'A price');
  const scale=guardActive?A_STAGE75.guardedScale:A_STAGE75.normalScale;
  const signedNotional=base*scale*e;
  return {scale,signedNotional,signedQuantity:signedNotional/p};
}

export function stage75StopPrice({fillPrice,side}){
  const p=finitePositive(fillPrice,'A fill price');
  if(!['long','short'].includes(side))throw Error('invalid A side');
  return p*(side==='long'?1-A_STAGE75.stopFraction:1+A_STAGE75.stopFraction);
}

export function rebalanceDelta({actualSignedQuantity,targetSignedQuantity,step,minQuantity,minNotional,price}){
  const p=finitePositive(price,'A price'),s=finitePositive(step,'A quantity step');
  const actual=Number(actualSignedQuantity),target=Number(targetSignedQuantity);
  if(!Number.isFinite(actual)||!Number.isFinite(target))throw Error('invalid A quantity');
  const raw=target-actual,amount=Math.floor((Math.abs(raw)+1e-12)/s)*s;
  if(amount<Number(minQuantity)||amount*p<Number(minNotional))return {action:'hold',quantity:0,reason:'below_minimum_delta'};
  return {action:raw>0?'buy':'sell',quantity:amount,reduceFirst:actual!==0&&Math.sign(raw)!==Math.sign(actual)};
}

export function selectiveResizeHold({symbol,side,actualQuantity,targetQuantity,price,equity}){
  const p=finitePositive(price,'A price'),e=finitePositive(equity,'A equity');
  const actual=Math.abs(Number(actualQuantity)),target=Math.abs(Number(targetQuantity));
  if(!Number.isFinite(actual)||!Number.isFinite(target))throw Error('invalid A selective resize quantity');
  const sameDirectionDecrease=actual>0&&target>0&&target<actual;
  const selected=(symbol==='SOL'&&side==='long')||(symbol==='BTC'&&side==='short');
  const deltaNotional=(actual-target)*p;
  const thresholdNotional=e*A_STAGE75.selectiveResizeThreshold;
  return {hold:sameDirectionDecrease&&selected&&deltaNotional<thresholdNotional,
    deltaNotional,thresholdNotional,selected,sameDirectionDecrease};
}

export function transitionCapacity({equity,currentGross,targetGross}){
  const e=finitePositive(equity,'A equity'),current=Math.max(0,Number(currentGross)),target=Math.max(0,Number(targetGross));
  const targetMargin=target/A_STAGE75.leverage;
  return {targetMargin,targetMarginRatio:targetMargin/e,withinEntryCap:targetMargin<=e*.80,
    reductionsFirst:target<current,additionalMarginNeeded:Math.max(0,targetMargin-current/A_STAGE75.leverage)};
}
