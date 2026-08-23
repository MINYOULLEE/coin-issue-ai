const PROJECT_URL = Deno.env.get("SUPABASE_URL");
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
const COINS = ["BTC","ETH","XRP","SOL","BNB"];
const SOURCES = [
  ["CFTC Press","https://www.cftc.gov/RSS/RSSGP/rssgp.xml","official"],
  ["CFTC Speeches","https://www.cftc.gov/RSS/RSSST/rssst.xml","official"],
  ["SEC Press","https://www.sec.gov/news/pressreleases.rss","official"],
  ["Federal Reserve","https://www.federalreserve.gov/feeds/press_all.xml","official"],
  ["Fed Speeches","https://www.federalreserve.gov/feeds/speeches.xml","official"],
  ["CoinDesk","https://www.coindesk.com/arc/outboundfeeds/rss/","media"],
  ["Cointelegraph","https://cointelegraph.com/rss","media"],
  ["Decrypt","https://decrypt.co/feed","media"],
  ["Coinbase","https://www.coinbase.com/blog/rss.xml","exchange"],
  ["Kraken","https://blog.kraken.com/feed","exchange"]
];
const POS=["approve","approved","launch","adoption","partnership","inflow","legal clarity","clarity act","허용","승인","채택","유입"];
const NEG=["ban","banned","hack","exploit","lawsuit","charges","reject","outflow","liquidation","shutdown","fraud","금지","해킹","기소","거부","유출","청산","중단","사기"];
const RELEVANT=["crypto","cryptocurrency","digital asset","bitcoin","ethereum","ether","xrp","ripple","solana","blockchain","token","stablecoin","usdt","usdc","defi","web3","binance","coinbase","etf","cftc","sec ","federal reserve","interest rate","inflation","가상자산","암호화폐","비트코인","이더리움","리플","솔라나","코인","토큰","거래소","금리"];

function text(s=""){return s.replace(/<!\[CDATA\[|\]\]>/g,"").replace(/<[^>]+>/g," ").replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/\s+/g," ").trim()}
function tag(block,names){for(const name of names){const m=block.match(new RegExp("<(?:\\w+:)?"+name+"[^>]*>([\\s\\S]*?)<\\/(?:\\w+:)?"+name+">","i"));if(m)return text(m[1]);}return ""}
function link(block){const direct=tag(block,["link"]);if(direct)return direct;const m=block.match(/<link[^>]+href=["']([^"']+)/i);return m?m[1]:""}
function hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return (h>>>0).toString(16)}
function ema(a,n){const k=2/(n+1);return a.reduce((v,x,i)=>i?x*k+v*(1-k):x,0)}
function clamp(n,a,b){return Math.max(a,Math.min(b,n))}
function atrFromKlines(rows,period=14){
  if(!Array.isArray(rows)||rows.length<period+1)return 0;
  const tr=[];for(let i=1;i<rows.length;i++){const high=Number(rows[i][2]),low=Number(rows[i][3]),prev=Number(rows[i-1][4]);tr.push(Math.max(high-low,Math.abs(high-prev),Math.abs(low-prev)))}
  return tr.slice(-period).reduce((a,b)=>a+b,0)/period;
}
function emaTrend(rows){
  const closes=(rows||[]).map(x=>Number(x[4])).filter(Number.isFinite);
  if(closes.length<30)return "neutral";
  const fast=ema(closes.slice(-80),12),slow=ema(closes.slice(-80),26),gap=(fast/slow-1)*100;
  return gap>.08?"up":gap<-.08?"down":"neutral";
}
function fundingGuard(ratePct,side){
  const extreme=Math.abs(Number(ratePct||0))>=.05;
  const crowded=extreme&&((side==="long"&&ratePct>0)||(side==="short"&&ratePct<0));
  return {extreme,crowded};
}
function scenarios(price,change,rsi,vr,days){
  let bias=clamp(change*(days===1?.18:.35)+(vr-1)*1.2+(50-rsi)*.015,-8,8);
  const vol=clamp(Math.abs(change)*.45+2.2,2.5,12)*(days===1?1:2.2);
  let bull=clamp(Math.round(28+bias*2),12,58),bear=clamp(Math.round(28-bias*2),12,58),base=100-bull-bear;
  if(base<20){base=20;const over=bull+bear-80;bull-=Math.ceil(over/2);bear-=Math.floor(over/2)}
  const make=(prob,move,trigger)=>({prob,center:price*(1+move/100),low:price*(1+(move-vol*.45)/100),high:price*(1+(move+vol*.45)/100),change:move,trigger});
  return {base:make(base,bias*.45,"현재 추세·거래량 유지"),bull:make(bull,Math.abs(bias)+vol*.38,"거래량 증가와 저항 돌파"),bear:make(bear,-Math.abs(bias)-vol*.32,"지지 이탈 또는 위험자산 약세")};
}
async function json(url,timeout=12000){const ac=new AbortController();const t=setTimeout(()=>ac.abort(),timeout);try{const r=await fetch(url,{headers:{"User-Agent":"CoinIssueAI-Cloud/1.0","Accept":"application/json"},signal:ac.signal});if(!r.ok)throw Error(url+" "+r.status);return await r.json()}finally{clearTimeout(t)}}
async function fetchMarket(){
  const symbols=encodeURIComponent(JSON.stringify(COINS.map(x=>x+"USDT")));
  const tickers=await json("https://api.binance.com/api/v3/ticker/24hr?symbols="+symbols);
  const entries=await Promise.all(tickers.map(async t=>{
    const s=t.symbol.replace("USDT",""),price=Number(t.lastPrice),change=Number(t.priceChangePercent);
    let closes=[],vols=[],micro=[],hourRows=[],fourHourRows=[],dayRows=[],depth={bids:[],asks:[]},fundingRaw=0;
    try{
      const [rows,oneMinute,book,fourHour,day,premium]=await Promise.all([
        json("https://api.binance.com/api/v3/klines?symbol="+s+"USDT&interval=1h&limit=200"),
        json("https://api.binance.com/api/v3/klines?symbol="+s+"USDT&interval=1m&limit=60"),
        json("https://api.binance.com/api/v3/depth?symbol="+s+"USDT&limit=20"),
        json("https://api.binance.com/api/v3/klines?symbol="+s+"USDT&interval=4h&limit=120"),
        json("https://api.binance.com/api/v3/klines?symbol="+s+"USDT&interval=1d&limit=90"),
        json("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex?symbol="+s+"-USDT")
      ]);
      hourRows=rows;fourHourRows=fourHour;dayRows=day;closes=rows.map(x=>Number(x[4]));vols=rows.map(x=>Number(x[5]));micro=oneMinute;depth=book;
      const pd=premium?.data||premium||{};fundingRaw=Number(pd.lastFundingRate??pd.fundingRate??pd.rate??0)||0;
    }catch{}
    let rsi=50,vr=1,mom=change,trend=0,m1=0,m3=0,volumePace=1,buySell=1,sellBuy=1,bookImbalance=0,microVol=.25,longPressure=0,shortPressure=0;
    let support=price*.99,resistance=price*1.01,boxPosition=.5,boxWidth=2,supportTouches=0,resistanceTouches=0,regime="range",profitTaking=0,shortCovering=0,falseBreakout="none",poc=price;
    const atr1h=atrFromKlines(hourRows),atr1m=atrFromKlines(micro),trend4h=emaTrend(fourHourRows),trend1d=emaTrend(dayRows),fundingRatePct=fundingRaw*100,fundingExtreme=Math.abs(fundingRatePct)>=.05;
    if(closes.length>30){
      let gain=0,loss=0;for(let i=closes.length-14;i<closes.length;i++){const d=closes[i]-closes[i-1];gain+=Math.max(d,0);loss+=Math.max(-d,0)}rsi=loss?100-100/(1+gain/loss):100;
      const v1=vols.slice(-24).reduce((a,b)=>a+b,0),v0=vols.slice(-48,-24).reduce((a,b)=>a+b,0)||1;vr=v1/v0;
      mom=(closes.at(-1)/closes.at(-25)-1)*100;trend=(ema(closes.slice(-80),12)/ema(closes.slice(-80),26)-1)*100;
    }
    if(micro.length>=45){
      const mc=micro.map(x=>Number(x[4])),mv=micro.map(x=>Number(x[5])),mh=micro.map(x=>Number(x[2])),ml=micro.map(x=>Number(x[3])),mo=micro.map(x=>Number(x[1])),last=micro.at(-1);
      m1=(mc.at(-1)/mc.at(-2)-1)*100;m3=(mc.at(-1)/mc.at(-4)-1)*100;
      const elapsed=clamp((Date.now()-Number(last[0]))/1000,5,60),baseV=mv.slice(-21,-1).reduce((a,b)=>a+b,0)/20||1;
      volumePace=clamp((Number(last[5])/baseV)*(60/elapsed),0,12);
      const recent=micro.slice(-3),buy=recent.reduce((a,x)=>a+Number(x[9]||0),0),total=recent.reduce((a,x)=>a+Number(x[5]||0),0),sell=Math.max(0,total-buy);
      buySell=buy/(sell||1);sellBuy=sell/(buy||1);
      const returns=[];for(let i=mc.length-20;i<mc.length;i++)returns.push(Math.abs((mc[i]/mc[i-1]-1)*100));
      microVol=clamp(returns.reduce((a,b)=>a+b,0)/(returns.length||1),.08,2);
      const bid=(depth.bids||[]).reduce((a,x)=>a+Number(x[0])*Number(x[1]),0),ask=(depth.asks||[]).reduce((a,x)=>a+Number(x[0])*Number(x[1]),0);
      bookImbalance=(bid-ask)/(bid+ask||1);
      const impulse=Math.max(0,volumePace-1);
      longPressure=clamp(Math.round(Math.max(0,m1)*42+Math.max(0,m3)*25+Math.max(0,buySell-1)*18+impulse*10+Math.max(0,bookImbalance)*35),0,100);
      shortPressure=clamp(Math.round(Math.max(0,-m1)*42+Math.max(0,-m3)*25+Math.max(0,sellBuy-1)*18+impulse*10+Math.max(0,-bookImbalance)*35),0,100);

      const lookback=micro.slice(-46,-1),highs=lookback.map(x=>Number(x[2])).sort((a,b)=>a-b),lows=lookback.map(x=>Number(x[3])).sort((a,b)=>a-b);
      support=lows[Math.floor(lows.length*.18)]||Math.min(...lows);resistance=highs[Math.floor(highs.length*.82)]||Math.max(...highs);
      if(resistance<=support){support=Math.min(...lows);resistance=Math.max(...highs)}
      boxWidth=(resistance/support-1)*100;boxPosition=clamp((price-support)/(resistance-support||1),0,1);
      const tol=Math.max(price*microVol*.006,price*.00035);
      supportTouches=lookback.filter(x=>Math.abs(Number(x[3])-support)<=tol&&Number(x[4])>Number(x[3])).length;
      resistanceTouches=lookback.filter(x=>Math.abs(Number(x[2])-resistance)<=tol&&Number(x[4])<Number(x[2])).length;
      const bins=12,minP=Math.min(...lows),maxP=Math.max(...highs),profile=Array(bins).fill(0);
      lookback.forEach(x=>{const typical=(Number(x[2])+Number(x[3])+Number(x[4]))/3,idx=clamp(Math.floor((typical-minP)/(maxP-minP||1)*bins),0,bins-1);profile[idx]+=Number(x[5])});
      const pidx=profile.indexOf(Math.max(...profile));poc=minP+(pidx+.5)*(maxP-minP)/bins;
      const priorClose=mc.at(-2),lastHigh=mh.at(-1),lastLow=ml.at(-1),lastOpen=mo.at(-1),lastClose=mc.at(-1);
      if(lastHigh>resistance&&lastClose<resistance&&sellBuy>1.05)falseBreakout="up";
      if(lastLow<support&&lastClose>support&&buySell>1.05)falseBreakout="down";
      const above=price>resistance+tol,below=price<support-tol,strongTrend=Math.abs(trend)>=.18;
      regime=above&&volumePace>=1.4?"breakout_up":below&&volumePace>=1.4?"breakout_down":falseBreakout==="up"?"false_breakout_up":falseBreakout==="down"?"false_breakout_down":boxPosition<=.2?"support_test":boxPosition>=.8?"resistance_test":strongTrend?(trend>0?"trend_up":"trend_down"):"range";
      const rise20=(price/mc.at(-21)-1)*100,fall20=-rise20;
      profitTaking=clamp(Math.round(Math.max(0,rise20)*7+Math.max(0,sellBuy-1)*22+Math.max(0,-m1)*30+Math.max(0,volumePace-1)*8+(boxPosition>=.8?12:0)),0,100);
      shortCovering=clamp(Math.round(Math.max(0,fall20)*7+Math.max(0,buySell-1)*22+Math.max(0,m1)*30+Math.max(0,volumePace-1)*8+(boxPosition<=.2?12:0)),0,100);
    }
    let flowAction="wait";
    const breakoutLong=regime==="breakout_up"&&longPressure>=62,breakoutShort=regime==="breakout_down"&&shortPressure>=62;
    const rangeLong=(regime==="support_test"||regime==="false_breakout_down")&&longPressure>=62&&supportTouches>=1;
    const rangeShort=(regime==="resistance_test"||regime==="false_breakout_up")&&shortPressure>=62&&resistanceTouches>=1;
    if(breakoutLong||rangeLong)flowAction="long";if(breakoutShort||rangeShort)flowAction="short";
    if(flowAction!=="wait"&&fundingGuard(fundingRatePct,flowAction).crowded)flowAction="wait";
    const longScore=clamp(5+longPressure+(regime==="breakout_up"?12:0)+(regime==="support_test"||regime==="false_breakout_down"?10:0)-profitTaking*.18,0,100);
    const shortScore=clamp(5+shortPressure+(regime==="breakout_down"?12:0)+(regime==="resistance_test"||regime==="false_breakout_up"?10:0)-shortCovering*.18,0,100);
    const rangeScore=clamp(72-Math.abs(longScore-shortScore)-Math.max(longScore,shortScore)*.25+(regime==="range"?18:0),5,80);
    const totalScore=longScore+shortScore+rangeScore||1,longProb=Math.round(longScore/totalScore*100),shortProb=Math.round(shortScore/totalScore*100),rangeProb=100-longProb-shortProb;
    const flowConfidence=Math.max(longScore,shortScore),extreme=flowAction!=="wait"&&flowConfidence>=82&&volumePace>=2.5&&((flowAction==="long"?buySell:sellBuy)>=1.5);
    const direction=trend+mom*.08,confidence=clamp(Math.round(55+Math.abs(direction)*10+Math.min(vr,3)*4-Math.max(0,rsi-75)*1.2),40,88);
    const rec=direction>.2?(rsi>75?"상승 추세·과열 주의":"상승 우세"):direction<-.2?(rsi<28?"하락 추세·과매도 주의":"하락 우세"):"중립·확인 대기";
    const regimeLabel={breakout_up:"상단 돌파",breakout_down:"하단 이탈",false_breakout_up:"상단 가짜 돌파",false_breakout_down:"하단 가짜 이탈",support_test:"지지 테스트",resistance_test:"저항 테스트",trend_up:"상승 추세",trend_down:"하락 추세",range:"박스 횡보"}[regime]||regime;
    const flowReason=flowAction==="long"?regimeLabel+"·매수 체결 확인":flowAction==="short"?regimeLabel+"·매도 체결 확인":regimeLabel+"·확정 대기";
    return [s,{price,change,quoteVolume:Number(t.quoteVolume),volume_ratio:vr,rsi,recommendation:rec,direction_confidence:confidence,trend_strength:clamp(Math.round(50+direction*15),0,100),trend_4h:trend4h,trend_1d:trend1d,atr_1h:atr1h,atr_1h_pct:price?atr1h/price*100:0,atr_1m:atr1m,atr_1m_pct:price?atr1m/price*100:0,funding_rate:fundingRaw,funding_rate_pct:fundingRatePct,funding_extreme:fundingExtreme,funding_bias:fundingRatePct>0?"long_crowded":fundingRatePct<0?"short_crowded":"neutral",scenarios24:scenarios(price,change,rsi,vr,1),scenarios7d:scenarios(price,change,rsi,vr,7),momentum_1m:m1,momentum_3m:m3,one_minute_volume_pace:volumePace,buy_sell_ratio:buySell,sell_buy_ratio:sellBuy,orderbook_imbalance:bookImbalance,micro_volatility_pct:microVol,long_pressure:Math.round(longScore),short_pressure:Math.round(shortScore),flow_action:flowAction,flow_confidence:Math.round(flowConfidence),flow_extreme:extreme,flow_reason:flowReason,market_structure:{regime,label:regimeLabel,support,resistance,poc,box_position:boxPosition,box_width_pct:boxWidth,support_touches:supportTouches,resistance_touches:resistanceTouches,false_breakout:falseBreakout,profit_taking_risk:profitTaking,short_covering_risk:shortCovering},micro_scenarios:{long:longProb,short:shortProb,range:rangeProb},risks:[fundingExtreme?(fundingRatePct>0?"롱 펀딩 과열·롱 신규 차단":"숏 펀딩 과열·숏 신규 차단"):profitTaking>=60?"차익실현 압력 높음":shortCovering>=60?"숏커버 반등 위험 높음":falseBreakout!=="none"?"가짜 돌파 감지":regime==="range"?"박스 중앙 추격 금지":"급등락·뉴스 변수"],reasons:[regimeLabel,`4H ${trend4h} / 1D ${trend1d}`,`펀딩 ${fundingRatePct.toFixed(4)}%`,`지지 ${support.toFixed(price<10?4:2)} / 저항 ${resistance.toFixed(price<10?4:2)}`,`1분 거래량 ${volumePace.toFixed(2)}배`],updated:new Date().toISOString()}];
  }));
  const market=Object.fromEntries(entries);
  try{const u=(await json("https://api.upbit.com/v1/ticker?markets=KRW-USDT"))[0];market.USDT={price:Number(u.trade_price),change:Number(u.signed_change_rate)*100,quoteVolume:Number(u.acc_trade_price_24h||0),currency:"KRW",source:"Upbit",updated:new Date().toISOString()}}catch{}
  return market;
}
async function feed(source){
  const [name,url,type]=source;const ac=new AbortController(),timer=setTimeout(()=>ac.abort(),10000);
  try{const r=await fetch(url,{headers:{"User-Agent":"CoinIssueAI-Cloud/1.0","Accept":"application/rss+xml, application/atom+xml, text/xml"},signal:ac.signal});if(!r.ok)throw Error(String(r.status));const xml=await r.text();const blocks=[...xml.matchAll(/<(?:item|entry)\b[^>]*>([\s\S]*?)<\/(?:item|entry)>/gi)].slice(0,25).map(x=>x[1]);const now=Date.now();const issues=[];
    for(const b of blocks){const title=tag(b,["title"]),summary=tag(b,["description","summary","content","encoded"]),url2=link(b),dateRaw=tag(b,["pubDate","published","updated","date"]);if(!title)continue;const all=(title+" "+summary).toLowerCase();if(!RELEVANT.some(k=>all.includes(k)))continue;const ts=Date.parse(dateRaw);if(Number.isFinite(ts)&&(now-ts>86400000||ts-now>21600000))continue;const pos=POS.filter(k=>all.includes(k)).length,neg=NEG.filter(k=>all.includes(k)).length;const direction=pos>neg?"호재":neg>pos?"악재":"중립";const score=clamp(45+(type==="official"?20:type==="exchange"?12:5)+Math.abs(pos-neg)*8,45,96);const grade=score>=85?"S":score>=65?"A":"B";const assets=[];if(/bitcoin|\bbtc\b|비트코인/.test(all))assets.push("BTC");if(/ethereum|ether|\beth\b|이더리움/.test(all))assets.push("ETH");if(/xrp|ripple|리플/.test(all))assets.push("XRP");if(/solana|\bsol\b|솔라나/.test(all))assets.push("SOL");if(/bnb|binance/.test(all))assets.push("BNB");if(!assets.length)assets.push("시장전체");issues.push({id:hash(url2||title),source:name,source_type:type,title,summary:(summary||title).slice(0,600),url:url2,published:Number.isFinite(ts)?new Date(ts).toISOString():dateRaw,detected:new Date().toISOString(),delay_sec:Number.isFinite(ts)?Math.max(0,Math.floor((now-ts)/1000)):0,grade,score,direction,confidence:clamp(58+(type==="official"?25:10),55,95),assets:assets.join(","),category:type==="exchange"?"거래소 공지":/cftc|sec |regulat|etf/.test(all)?"규제·ETF":"시장 이슈",reaction:"시장 가격·거래량 동시 확인 필요",investor_note:"공식 원문과 실제 가격 반응을 확인하고 선반영 여부를 구분하세요.",horizon:"즉시~24시간",ai:0})}
    return {name,issues,status:{ok:true,checked:new Date().toISOString(),items:blocks.length,new:issues.length,error:""}};
  }catch(e){return {name,issues:[],status:{ok:false,checked:new Date().toISOString(),items:0,new:0,error:String(e).slice(0,150)}}}finally{clearTimeout(timer)}
}
function themes(issues){const specs=[["미국 CLARITY 법안·시장구조",["clarity","market structure"]],["미국 CFTC·SEC 암호화폐 정책",["cftc","sec ","digital asset regulation"]],["현물 ETF·기관 자금 흐름",["etf","institutional inflow"]],["대형 해킹·네트워크 위험",["hack","exploit","breach"]]];return specs.map(([title,keys])=>{const hits=issues.filter(x=>keys.some(k=>(x.title+" "+x.summary).toLowerCase().includes(k)));if(!hits.length)return null;return {title,grade:hits.some(x=>x.grade==="S")?"S":hits.length>1?"A":"B",direction:hits.filter(x=>x.direction==="호재").length>hits.filter(x=>x.direction==="악재").length?"호재 우세":"방향 확인 중",reason:"최근 공식 발표와 주요 보도에서 반복 감지되는 시장 핵심 테마입니다.",watch:"확정 문서·시행 시점과 가격·거래량의 동시 반응을 확인하세요.",evidence_count:hits.length,assets:[...new Set(hits.flatMap(x=>x.assets.split(",")))].join(","),url:hits[0].url,source:"클라우드 복수 출처 종합"}}).filter(Boolean)}

function adminHeaders(extra={}){return {apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY,"Content-Type":"application/json",...extra}}
const INTERNAL_TRADE_SECRET=Deno.env.get("INTERNAL_TRADE_SECRET")||"";
// 새 신호가 확정되는 즉시 실거래 실행 함수를 내부 호출한다. 실거래 자체의 성공/실패/거절은
// bingx-order-execute와 real_trades 테이블에서 전적으로 처리하며, 여기서는 절대 신호 엔진의
// 흐름을 막지 않도록 실패를 삼키고 로그만 남긴다.
async function triggerRealTrade(signal){
  if(!INTERNAL_TRADE_SECRET)return;
  try{
    const r=await fetch(PROJECT_URL+"/functions/v1/bingx-order-execute",{method:"POST",headers:{"Content-Type":"application/json","x-internal-key":INTERNAL_TRADE_SECRET},body:JSON.stringify(signal)});
    const j=await r.json().catch(()=>({}));
    if(!j.ok)console.error("real trade not placed:",signal.symbol,signal.side,signal.signal_type,j.error||j.skipped);
  }catch(e){console.error("triggerRealTrade failed:",e instanceof Error?e.message:String(e))}
}
async function activeSignals(){
  const url=PROJECT_URL+"/rest/v1/trade_signals?status=in.(active,weakening)&select=*&order=created_at.desc";
  const r=await fetch(url,{headers:adminHeaders()});if(!r.ok)throw Error("signal fetch "+r.status+" "+await r.text());return await r.json();
}
async function recentSignals(){
  const url=PROJECT_URL+"/rest/v1/trade_signals?status=in.(success,failure,neutral,expired,invalidated)&select=*&order=closed_at.desc&limit=50";
  const r=await fetch(url,{headers:adminHeaders()});if(!r.ok)throw Error("history fetch "+r.status+" "+await r.text());return await r.json();
}
async function patchSignal(id,body){
  const r=await fetch(PROJECT_URL+"/rest/v1/trade_signals?id=eq."+id,{method:"PATCH",headers:adminHeaders({Prefer:"return=representation"}),body:JSON.stringify(body)});
  if(!r.ok)throw Error("signal patch "+r.status+" "+await r.text());const rows=await r.json();return rows[0]||{...body,id};
}
async function insertSignal(body){
  const r=await fetch(PROJECT_URL+"/rest/v1/trade_signals",{method:"POST",headers:adminHeaders({Prefer:"return=representation"}),body:JSON.stringify(body)});
  if(!r.ok)throw Error("signal insert "+r.status+" "+await r.text());const rows=await r.json();return rows[0];
}
function swingSide(m){
  const rec=String(m.live_recommendation||m.recommendation||"");
  const macroLong=m.trend_4h!=="down"&&m.trend_1d!=="down",macroShort=m.trend_4h!=="up"&&m.trend_1d!=="up";
  const longFundingOk=!fundingGuard(Number(m.funding_rate_pct||0),"long").crowded,shortFundingOk=!fundingGuard(Number(m.funding_rate_pct||0),"short").crowded;
  const long=rec.startsWith("상승")&&m.direction_confidence>=70&&m.volume_ratio>=.9&&m.rsi>=35&&m.rsi<=72&&m.trend_strength>=58&&macroLong&&longFundingOk;
  const short=rec.startsWith("하락")&&m.direction_confidence>=70&&m.volume_ratio>=.9&&m.rsi>=28&&m.rsi<=65&&m.trend_strength<=42&&macroShort&&shortFundingOk;
  return long?"long":short?"short":null;
}
function tacticalSide(m){
  const side=m.flow_action==="long"||m.flow_action==="short"?m.flow_action:null;
  return side&&!fundingGuard(Number(m.funding_rate_pct||0),side).crowded?side:null;
}
function signalView(s,price){
  const side=s.side,entry=Number(s.entry_price),pnl=(price/entry-1)*100*(side==="long"?1:-1);
  const notional=Number(s.notional_usd||0),margin=Number(s.margin_usd||0),fee=Number(s.fee_usd||0),net=notional?notional*pnl/100-fee:null;
  return {...s,signal_type:s.signal_type||"swing",horizon_minutes:Number(s.horizon_minutes||1440),entry_price:entry,current_net_pnl_usd:net,current_leveraged_return_pct:margin&&net!=null?net/margin*100:null,invalidation_price:Number(s.invalidation_price),target_price:Number(s.target_price),current_price:price,current_pnl_pct:pnl,remaining_sec:Math.max(0,Math.floor((Date.parse(s.expires_at)-Date.now())/1000))};
}
function positionPlan(entry,invalidation,confidence,type,microVol,availableMargin=1000,equity=1000,market={}){
  const stopPct=Math.max(.001,Math.abs(entry-invalidation)/entry);
  const vol=Number(microVol||0),baseLeverage=confidence>=90&&vol<=.35?10:confidence>=85&&vol<=.55?7:confidence>=78?5:confidence>=70?3:2;
  const macroMixed=market.trend_4h==="neutral"||market.trend_1d==="neutral"||market.trend_4h!==market.trend_1d;
  const leverage=Math.min(baseLeverage,market.funding_extreme||macroMixed?5:10);
  const riskPct=type==="tactical"?.75:1.25,riskUsd=equity*riskPct/100,marginCap=equity*(type==="tactical"?.25:.35);
  const margin=Math.round(Math.max(0,Math.min(marginCap,availableMargin,riskUsd/(stopPct*leverage)))*100)/100;
  const notional=Math.round(margin*leverage*100)/100,fee=Math.round(notional*.001*100)/100;
  return {account_equity_usd:equity,margin_usd:margin,leverage,notional_usd:notional,fee_usd:fee,risk_usd:riskUsd,risk_pct:riskPct};
}
async function manageSignals(market,old){
  let active=await activeSignals();const perf=await historyStats(),candidates={...(old.signal_candidates||{})};const health={...(old.signal_health||{})};const cooldowns={...(old.signal_cooldowns||{})};const now=new Date();
  const key=(symbol,type)=>symbol+":"+type,byKey=Object.fromEntries(active.map(x=>[key(x.symbol,x.signal_type||"swing"),x]));let realizedPnl=Number(perf.net_pnl_usd||0);
  for(const [k,v] of Object.entries(cooldowns))if(Date.parse(String(v))<=Date.now())delete cooldowns[k];
  for(const symbol of COINS){
    const m=market[symbol];if(!m)continue;m.live_recommendation=m.recommendation;
    for(const type of ["swing","tactical"]){
      const k=key(symbol,type),sideNow=type==="swing"?swingSide(m):tacticalSide(m),horizon=type==="swing"?1440:60;
      let s=byKey[k];
      if(s){
        const price=Number(m.price),expired=Date.now()>=Date.parse(s.expires_at);
        const invalid=s.side==="long"?price<=Number(s.invalidation_price):price>=Number(s.invalidation_price);
        const target=s.side==="long"?price>=Number(s.target_price):price<=Number(s.target_price);
        if(expired||invalid||target){
          const result=(price/Number(s.entry_price)-1)*100*(s.side==="long"?1:-1);
          const threshold=type==="tactical"?.2:.5,outcome=target?"success":invalid?"failure":result>=threshold?"success":result<=-threshold?"failure":"neutral";
          const reason=target?"목표가 도달·익절":invalid?"손상 기준 도달·손절":outcome==="success"?horizon+"분 만료·수익 종료":outcome==="failure"?horizon+"분 만료·손실 종료":horizon+"분 만료·보합";
          const notional=Number(s.notional_usd||0),margin=Number(s.margin_usd||0),fee=Number(s.fee_usd||0),gross=notional*result/100,net=gross-fee,leveraged=margin?net/margin*100:null;
          await patchSignal(s.id,{status:outcome,closed_at:now.toISOString(),exit_price:price,result_pct:result,net_pnl_usd:notional?net:null,leveraged_return_pct:leveraged,close_reason:reason,updated_at:now.toISOString()});if(notional)realizedPnl+=net;
          if(outcome==="failure")cooldowns[k+":"+s.side]=new Date(now.getTime()+(type==="tactical"?900000:3600000)).toISOString();
          delete byKey[k];delete candidates[k];delete health[k];s=null;
        }else{
          const supported=sideNow===s.side,h=health[k]||{support_fail:0,support_ok:0};
          h.support_fail=supported?0:Number(h.support_fail||0)+1;h.support_ok=supported?Number(h.support_ok||0)+1:0;h.last_checked=now.toISOString();health[k]=h;
          const failLimit=type==="tactical"?2:3,recoverLimit=type==="tactical"?1:2;let next=s.status;
          if(s.status==="active"&&h.support_fail>=failLimit)next="weakening";if(s.status==="weakening"&&h.support_ok>=recoverLimit)next="active";
          if(next!==s.status)s=await patchSignal(s.id,{status:next,updated_at:now.toISOString()});
          byKey[k]=s;delete candidates[k];
        }
      }
      if(!s&&sideNow){
        const cooldownKey=k+":"+sideNow,cooling=Date.parse(String(cooldowns[cooldownKey]||0))>Date.now();
        if(!cooling){
          const prev=candidates[k],count=prev?.side===sideNow?Number(prev.count||0)+1:1,required=type==="tactical"?(m.flow_extreme?1:2):3;
          candidates[k]={side:sideNow,count,required,first_seen:prev?.side===sideNow?prev.first_seen:now.toISOString(),last_seen:now.toISOString()};
          if(count>=required){
            const entry=Number(m.price),created=now.toISOString(),expires=new Date(now.getTime()+horizon*60000).toISOString();
            let invalidation,target,confidence,reasons;
            if(type==="swing"){
              const sc=m.scenarios24,scenarioStop=sideNow==="long"?Number(sc.base.low):Number(sc.base.high),atrStop=entry+(sideNow==="long"?-1:1)*Number(m.atr_1h||0)*1.5;
              invalidation=sideNow==="long"?Math.min(scenarioStop,atrStop):Math.max(scenarioStop,atrStop);target=sideNow==="long"?Number(sc.bull.center):Number(sc.bear.center);confidence=Number(m.direction_confidence);reasons=[...(m.reasons||[]),`ATR14(1H) 손절 ${Number(m.atr_1h_pct||0).toFixed(2)}%`]
            }
            else{
              const vol=Number(m.micro_volatility_pct||.25),tp=clamp(vol*2.2,.5,2.5)/100,sl=clamp(vol*1.2,.35,1.5)/100,percentStop=entry*(sideNow==="long"?1-sl:1+sl),atrStop=entry+(sideNow==="long"?-1:1)*Number(m.atr_1m||0)*1.5;
              target=entry*(sideNow==="long"?1+tp:1-tp);invalidation=sideNow==="long"?Math.min(percentStop,atrStop):Math.max(percentStop,atrStop);confidence=Number(m.flow_confidence);reasons=[m.flow_reason,`1분 거래량 속도 ${Number(m.one_minute_volume_pace).toFixed(2)}배`,`호가 불균형 ${(Number(m.orderbook_imbalance)*100).toFixed(1)}%`,`ATR14(1M) 손절 ${Number(m.atr_1m_pct||0).toFixed(3)}%`]
            }
            try{
              const openNow=Object.values(byKey),usedMargin=openNow.reduce((sum,x)=>sum+Number(x.margin_usd||0),0),unrealized=openNow.reduce((sum,x)=>{const px=Number(market[x.symbol]?.price||x.entry_price),raw=(px/Number(x.entry_price)-1)*100*(x.side==="long"?1:-1);return sum+(Number(x.notional_usd||0)?Number(x.notional_usd)*raw/100-Number(x.fee_usd||0):0)},0),balance=Math.max(0,1000+realizedPnl),equity=Math.max(0,balance+unrealized),available=Math.max(0,equity-usedMargin),plan=positionPlan(entry,invalidation,confidence,type,m.micro_volatility_pct,available,equity,m);
              if(plan.margin_usd<25){candidates[k].blocked="담보 부족";continue}
              s=await insertSignal({symbol,side:sideNow,signal_type:type,horizon_minutes:horizon,status:"active",entry_price:entry,invalidation_price:invalidation,target_price:target,confidence,reasons,...plan,entry_metrics:{rsi:m.rsi,volume_ratio:m.volume_ratio,trend_strength:m.trend_strength,trend_4h:m.trend_4h,trend_1d:m.trend_1d,atr_1h:m.atr_1h,atr_1m:m.atr_1m,funding_rate_pct:m.funding_rate_pct,funding_extreme:m.funding_extreme,momentum_1m:m.momentum_1m,momentum_3m:m.momentum_3m,one_minute_volume_pace:m.one_minute_volume_pace,buy_sell_ratio:m.buy_sell_ratio,sell_buy_ratio:m.sell_buy_ratio,orderbook_imbalance:m.orderbook_imbalance,long_pressure:m.long_pressure,short_pressure:m.short_pressure,market_structure:m.market_structure,micro_scenarios:m.micro_scenarios},created_at:created,expires_at:expires,updated_at:created});
              byKey[k]=s;delete candidates[k];
              await triggerRealTrade(s);
            }catch(e){if(!String(e).includes("409"))throw e}
          }
        }
      }else if(!s&&!sideNow)delete candidates[k];
    }
    const swing=byKey[key(symbol,"swing")],tactical=byKey[key(symbol,"tactical")];
    m.trade_signal=swing?signalView(swing,Number(m.price)):null;m.tactical_signal=tactical?signalView(tactical,Number(m.price)):null;
    m.tactical_response={side:tactical?.side||m.flow_action,status:tactical?.status||"watch",confidence:Number(tactical?.confidence||m.flow_confidence||0),reason:m.flow_reason,required_checks:m.flow_extreme?1:2};
    if(swing){m.recommendation=swing.side==="long"?(swing.status==="weakening"?"24H 롱 유지·근거 약화":"24H 롱 유지"):(swing.status==="weakening"?"24H 숏 유지·근거 약화":"24H 숏 유지");m.direction_confidence=Number(swing.confidence)}
    else{const c=candidates[key(symbol,"swing")];m.recommendation=c?("24H "+(c.side==="long"?"롱":"숏")+" 확인 "+c.count+"/3"):"24H 진입 대기"}
  }
  active=Object.values(byKey).map(s=>signalView(s,Number(market[s.symbol]?.price||s.entry_price)));
  const recent=await recentSignals(),actions=COINS.reduce((o,x)=>{o[x]=market[x]?.flow_action||"wait";return o},{}),openFinal=Object.values(byKey),usedMargin=openFinal.reduce((sum,x)=>sum+Number(x.margin_usd||0),0),unrealizedPnl=openFinal.reduce((sum,x)=>{const px=Number(market[x.symbol]?.price||x.entry_price),raw=(px/Number(x.entry_price)-1)*100*(x.side==="long"?1:-1);return sum+(Number(x.notional_usd||0)?Number(x.notional_usd)*raw/100-Number(x.fee_usd||0):0)},0),balance=Math.max(0,1000+realizedPnl),equity=Math.max(0,balance+unrealizedPnl),availableMargin=Math.max(0,equity-usedMargin),account={initial_balance_usd:1000,balance_usd:balance,realized_pnl_usd:realizedPnl,unrealized_pnl_usd:unrealizedPnl,equity_usd:equity,used_margin_usd:usedMargin,available_margin_usd:availableMargin,return_pct:(balance/1000-1)*100,open_positions:openFinal.length,updated_at:now.toISOString()};
  return {active,candidates,health,recent,cooldowns,account,regime:{mode:"symmetric_1m_flow",actions,checked_at:now.toISOString()}};
}

async function current(){try{const r=await fetch(PROJECT_URL+"/rest/v1/coin_snapshots?id=eq.live&select=payload",{headers:{apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY}});const rows=await r.json();return rows[0]?.payload||{}}catch{return {}}}
async function save(payload){const r=await fetch(PROJECT_URL+"/rest/v1/coin_snapshots?on_conflict=id",{method:"POST",headers:{apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY,"Content-Type":"application/json",Prefer:"resolution=merge-duplicates,return=minimal"},body:JSON.stringify([{id:"live",payload,updated_at:payload.heartbeat}])});if(!r.ok)throw Error("Supabase save "+r.status+" "+await r.text())}

function publicSignal(s){return {id:s.id,symbol:s.symbol,side:s.side,signal_type:s.signal_type||"swing",horizon_minutes:Number(s.horizon_minutes||1440),status:s.status,entry_price:Number(s.entry_price),invalidation_price:Number(s.invalidation_price),target_price:Number(s.target_price),confidence:Number(s.confidence),created_at:s.created_at,expires_at:s.expires_at,closed_at:s.closed_at,exit_price:s.exit_price==null?null:Number(s.exit_price),result_pct:s.result_pct==null?null:Number(s.result_pct),close_reason:s.close_reason,account_equity_usd:Number(s.account_equity_usd||1000),margin_usd:s.margin_usd==null?null:Number(s.margin_usd),leverage:s.leverage==null?null:Number(s.leverage),notional_usd:s.notional_usd==null?null:Number(s.notional_usd),fee_usd:s.fee_usd==null?null:Number(s.fee_usd),net_pnl_usd:s.net_pnl_usd==null?null:Number(s.net_pnl_usd),leveraged_return_pct:s.leveraged_return_pct==null?null:Number(s.leveraged_return_pct)}}
async function historyStats(symbol=""){
  let offset=0,all=[];
  while(true){
    let url=PROJECT_URL+"/rest/v1/trade_signals?select=status,result_pct,net_pnl_usd,leveraged_return_pct&status=in.(success,failure,neutral)&order=id.asc&limit=1000&offset="+offset;
    if(COINS.includes(symbol))url+="&symbol=eq."+symbol;
    const r=await fetch(url,{headers:adminHeaders()});if(!r.ok)throw Error("history stats "+r.status+" "+await r.text());
    const batch=await r.json();all.push(...batch);if(batch.length<1000)break;offset+=1000;
  }
  const success=all.filter(x=>x.status==="success").length,failure=all.filter(x=>x.status==="failure").length,neutral=all.filter(x=>x.status==="neutral").length,decided=success+failure;
  const totalReturn=all.reduce((sum,x)=>sum+(Number.isFinite(Number(x.result_pct))?Number(x.result_pct):0),0),simulated=all.filter(x=>x.net_pnl_usd!=null),netPnl=simulated.reduce((sum,x)=>sum+Number(x.net_pnl_usd||0),0);
  return {success,failure,neutral,decided,success_rate:decided?success/decided*100:0,failure_rate:decided?failure/decided*100:0,total_return_pct:totalReturn,simulated_trades:simulated.length,net_pnl_usd:netPnl,account_return_pct:netPnl/1000*100};
}
async function historyResponse(req){
  const u=new URL(req.url),page=Math.max(1,Number(u.searchParams.get("page")||1)),limit=Math.min(20,Math.max(1,Number(u.searchParams.get("limit")||20)));
  const symbol=String(u.searchParams.get("symbol")||"").toUpperCase(),offset=(page-1)*limit;
  let url=PROJECT_URL+"/rest/v1/trade_signals?select=id,symbol,side,signal_type,horizon_minutes,status,entry_price,invalidation_price,target_price,confidence,created_at,expires_at,closed_at,exit_price,result_pct,close_reason,account_equity_usd,margin_usd,leverage,notional_usd,fee_usd,net_pnl_usd,leveraged_return_pct&order=created_at.desc&limit="+limit+"&offset="+offset;
  if(COINS.includes(symbol))url+="&symbol=eq."+symbol;
  const r=await fetch(url,{headers:adminHeaders({Prefer:"count=exact"})});if(!r.ok)throw Error("history page "+r.status+" "+await r.text());
  const rows=(await r.json()).map(publicSignal),range=r.headers.get("content-range")||"",total=Number(range.split("/")[1]||rows.length),stats=await historyStats(symbol);
  return Response.json({ok:true,page,limit,total,pages:Math.max(1,Math.ceil(total/limit)),rows,stats},{headers:{"Access-Control-Allow-Origin":"*","Cache-Control":"no-store"}});
}

Deno.serve(async req=>{
  if(req.method==="OPTIONS")return new Response(null,{status:204,headers:{"Access-Control-Allow-Origin":"*","Access-Control-Allow-Headers":"authorization,apikey,content-type"}});
  if(req.method==="GET")try{return await historyResponse(req)}catch(e){return Response.json({ok:false,error:String(e)},{status:500,headers:{"Access-Control-Allow-Origin":"*"}})}
  if(req.method!=="POST")return new Response("POST required",{status:405});
  try{
    const old=await current();
    const [market,feeds]=await Promise.all([fetchMarket(),Promise.all(SOURCES.map(feed))]);
    const signalState=await manageSignals(market,old);
    const cutoff=Date.now()-86400000,merged=[...feeds.flatMap(x=>x.issues),...(old.issues||[])];const seen=new Set(),issues=[];
    for(const x of merged.sort((a,b)=>Date.parse(b.detected||b.published||0)-Date.parse(a.detected||a.published||0))){const key=x.url||x.id||x.title;if(seen.has(key))continue;seen.add(key);const ts=Date.parse(x.detected||x.published||0);if(Number.isFinite(ts)&&ts<cutoff)continue;issues.push(x);if(issues.length>=200)break}
    const today=new Date().toISOString().slice(0,10),day=issues.filter(x=>(x.detected||"").startsWith(today));
    const status=Object.fromEntries(feeds.map(x=>[x.name,x.status]));status["클라우드 수집기"]={ok:true,checked:new Date().toISOString(),items:issues.length,new:feeds.reduce((a,x)=>a+x.issues.length,0),error:""};
    const payload={...old,issues,market,status,active_signals:signalState.active,signal_candidates:signalState.candidates,signal_health:signalState.health,signal_cooldowns:signalState.cooldowns,market_regime:signalState.regime,paper_account:signalState.account,recent_signals:signalState.recent,stats:{today:day.length,urgent:day.filter(x=>["S","A"].includes(x.grade)).length,good:day.filter(x=>x.direction==="호재").length,bad:day.filter(x=>x.direction==="악재").length},hot_themes:themes(issues),hot_events:old.hot_events||[],started:old.started||new Date().toISOString(),heartbeat:new Date().toISOString(),collector:"supabase-cloud"};
    await save(payload);
    return Response.json({ok:true,heartbeat:payload.heartbeat,issues:issues.length,markets:Object.keys(market),active_signals:signalState.active.length,candidates:signalState.candidates});
  }catch(e){console.error(e);return Response.json({ok:false,error:String(e)},{status:500})}
});
