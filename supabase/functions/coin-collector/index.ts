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
    let closes=[],vols=[],fast=[];
    try{const [rows,fastRows]=await Promise.all([json("https://api.binance.com/api/v3/klines?symbol="+s+"USDT&interval=1h&limit=200"),json("https://api.binance.com/api/v3/klines?symbol="+s+"USDT&interval=5m&limit=30")]);closes=rows.map(x=>Number(x[4]));vols=rows.map(x=>Number(x[5]));fast=fastRows}catch{}
    let rsi=50,vr=1,mom=change,trend=0,momentum5=0,momentum15=0,sellRatio=1,fastVolume=1,shortPressure=0;
    if(closes.length>30){
      let gain=0,loss=0;for(let i=closes.length-14;i<closes.length;i++){const d=closes[i]-closes[i-1];gain+=Math.max(d,0);loss+=Math.max(-d,0)}rsi=loss?100-100/(1+gain/loss):100;
      const v1=vols.slice(-24).reduce((a,b)=>a+b,0),v0=vols.slice(-48,-24).reduce((a,b)=>a+b,0)||1;vr=v1/v0;
      mom=(closes.at(-1)/closes.at(-25)-1)*100;trend=(ema(closes.slice(-80),12)/ema(closes.slice(-80),26)-1)*100;
    }
    if(fast.length>=20){const fc=fast.map(x=>Number(x[4])),fv=fast.map(x=>Number(x[5]));momentum5=(fc.at(-1)/fc.at(-2)-1)*100;momentum15=(fc.at(-1)/fc.at(-4)-1)*100;const recent=fast.slice(-3),buy=recent.reduce((a,x)=>a+Number(x[9]||0),0),total=recent.reduce((a,x)=>a+Number(x[5]||0),0);sellRatio=(total-buy)/(buy||1);const recentV=fv.slice(-3).reduce((a,b)=>a+b,0)/3,baseV=fv.slice(-15,-3).reduce((a,b)=>a+b,0)/12||1;fastVolume=recentV/baseV;const below=price<ema(fc.slice(-20),20);shortPressure=clamp(Math.round(Math.max(0,-momentum5)*28+Math.max(0,-momentum15)*20+Math.max(0,sellRatio-1)*22+Math.max(0,fastVolume-1)*14+(below?15:0)),0,100)}
    const direction=trend+mom*.08,confidence=clamp(Math.round(55+Math.abs(direction)*10+Math.min(vr,3)*4-Math.max(0,rsi-75)*1.2-Math.max(0,shortPressure-55)*.25),40,88);
    const rec=direction>.2?(rsi>75?"상승 추세·과열 주의":"상승 우세"):direction<-.2?(rsi<28?"하락 추세·과매도 주의":"하락 우세"):"중립·확인 대기";
    return [s,{price,change,quoteVolume:Number(t.quoteVolume),volume_ratio:vr,rsi,recommendation:rec,direction_confidence:confidence,trend_strength:clamp(Math.round(50+direction*15),0,100),scenarios24:scenarios(price,change,rsi,vr,1),scenarios7d:scenarios(price,change,rsi,vr,7),momentum_5m:momentum5,momentum_15m:momentum15,short_pressure:shortPressure,fast_volume_ratio:fastVolume,sell_buy_ratio:sellRatio,risks:[shortPressure>=65?"강한 단기 숏 압력·신규 롱 차단":rsi>75?"단기 과열·차익실현":rsi<28?"과매도 변동성":"급등락·뉴스 변수"],reasons:[`24시간 ${change>=0?"+":""}${change.toFixed(2)}%`,`거래량 ${vr.toFixed(2)}배`,`RSI ${rsi.toFixed(1)}`],updated:new Date().toISOString()}];
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
function candidateSide(m){
  const rec=String(m.live_recommendation||m.recommendation||"");
  const long=rec.startsWith("상승")&&!m.long_entry_blocked&&Number(m.short_pressure||0)<60&&Number(m.momentum_15m||0)>=-.25&&m.direction_confidence>=70&&m.volume_ratio>=.9&&m.rsi>=35&&m.rsi<=72&&m.trend_strength>=58;
  const short=rec.startsWith("하락")&&m.direction_confidence>=70&&m.volume_ratio>=.9&&m.rsi>=28&&m.rsi<=65&&m.trend_strength<=42;
  return long?"long":short?"short":null;
}
function signalView(s,price){
  const side=s.side,entry=Number(s.entry_price),pnl=(price/entry-1)*100*(side==="long"?1:-1);
  return {...s,entry_price:entry,invalidation_price:Number(s.invalidation_price),target_price:Number(s.target_price),current_price:price,current_pnl_pct:pnl,remaining_sec:Math.max(0,Math.floor((Date.parse(s.expires_at)-Date.now())/1000))};
}
async function manageSignals(market,old){
  let active=await activeSignals();const candidates={...(old.signal_candidates||{})};const health={...(old.signal_health||{})};const cooldowns={...(old.signal_cooldowns||{})};const now=new Date(),bySymbol=Object.fromEntries(active.map(x=>[x.symbol,x]));const pressureCoins=COINS.filter(x=>Number(market[x]?.short_pressure||0)>=65),marketShock=pressureCoins.length>=3||Number(market.BTC?.short_pressure||0)>=75||Number(market.ETH?.short_pressure||0)>=75;for(const [k,v] of Object.entries(cooldowns))if(Date.parse(String(v))<=Date.now())delete cooldowns[k];
  for(const symbol of COINS){
    const m=market[symbol];if(!m)continue;m.live_recommendation=m.recommendation;const cooldown=Date.parse(String(cooldowns[symbol]||0))>Date.now();m.long_entry_blocked=marketShock||cooldown||Number(m.short_pressure||0)>=60;m.long_entry_block_reason=marketShock?"시장 전체 숏 충격":cooldown?"손절 후 60분 재진입 대기":Number(m.short_pressure||0)>=60?"단기 숏 압력 강함":"";
    let s=bySymbol[symbol];
    if(s){
      const price=Number(m.price),expired=Date.now()>=Date.parse(s.expires_at);
      const invalid=s.side==="long"?price<=Number(s.invalidation_price):price>=Number(s.invalidation_price);
      const target=s.side==="long"?price>=Number(s.target_price):price<=Number(s.target_price);
      if(expired||invalid||target){
        const result=(price/Number(s.entry_price)-1)*100*(s.side==="long"?1:-1);
        const outcome=target?"success":invalid?"failure":result>=.5?"success":result<=-.5?"failure":"neutral";
        const reason=target?"목표가 도달·익절":invalid?"손상 기준 도달·손절":outcome==="success"?"24시간 만료·수익 종료":outcome==="failure"?"24시간 만료·손실 종료":"24시간 만료·보합";
        await patchSignal(s.id,{status:outcome,closed_at:now.toISOString(),exit_price:price,result_pct:result,close_reason:reason,updated_at:now.toISOString()});
        if(outcome==="failure"){cooldowns[symbol]=new Date(now.getTime()+3600000).toISOString();m.long_entry_blocked=true;m.long_entry_block_reason="손절 후 60분 재진입 대기"}
        delete bySymbol[symbol];delete candidates[symbol];delete health[symbol];s=null;
      }else{
        const liveSide=candidateSide(m),supported=liveSide===s.side,h=health[symbol]||{support_fail:0,support_ok:0};
        h.support_fail=supported?0:Number(h.support_fail||0)+1;h.support_ok=supported?Number(h.support_ok||0)+1:0;h.last_checked=now.toISOString();health[symbol]=h;
        let next=s.status;if(s.status==="active"&&h.support_fail>=3)next="weakening";if(s.status==="weakening"&&h.support_ok>=2)next="active";
        if(next!==s.status)s=await patchSignal(s.id,{status:next,updated_at:now.toISOString()});
        bySymbol[symbol]=s;delete candidates[symbol];
      }
    }
    if(!s){
      const side=candidateSide(m),prev=candidates[symbol];
      if(!side){delete candidates[symbol]}
      else{
        const count=prev?.side===side?Number(prev.count||0)+1:1;
        candidates[symbol]={side,count,first_seen:prev?.side===side?prev.first_seen:now.toISOString(),last_seen:now.toISOString()};
        if(count>=3){
          const sc=m.scenarios24,entry=Number(m.price);
          const invalidation=side==="long"?Number(sc.base.low):Number(sc.base.high);
          const target=side==="long"?Number(sc.bull.center):Number(sc.bear.center);
          const created=now.toISOString(),expires=new Date(now.getTime()+86400000).toISOString();
          try{
            s=await insertSignal({symbol,side,status:"active",entry_price:entry,invalidation_price:invalidation,target_price:target,confidence:Number(m.direction_confidence),reasons:m.reasons||[],entry_metrics:{rsi:m.rsi,volume_ratio:m.volume_ratio,trend_strength:m.trend_strength,live_recommendation:m.live_recommendation,short_pressure:m.short_pressure,momentum_5m:m.momentum_5m,momentum_15m:m.momentum_15m,sell_buy_ratio:m.sell_buy_ratio},created_at:created,expires_at:expires,updated_at:created});
            bySymbol[symbol]=s;delete candidates[symbol];
          }catch(e){if(!String(e).includes("409"))throw e}
        }
      }
    }
    s=bySymbol[symbol];
    if(s){
      m.trade_signal=signalView(s,Number(m.price));
      m.recommendation=s.side==="long"?(s.status==="weakening"?"24H 롱 유지·근거 약화":"24H 롱 유지"):(s.status==="weakening"?"24H 숏 유지·근거 약화":"24H 숏 유지");
      m.direction_confidence=Number(s.confidence);
    }else{
      const c=candidates[symbol];m.trade_signal=null;m.recommendation=m.long_entry_blocked?("롱 진입 차단·"+m.long_entry_block_reason):c?("진입 확인 중 "+c.count+"/3"):"진입 대기";
    }
  }
  active=Object.values(bySymbol).map(s=>signalView(s,Number(market[s.symbol]?.price||s.entry_price)));
  const recent=await recentSignals();
  return {active,candidates,health,recent,cooldowns,regime:{short_shock:marketShock,pressure_coins:pressureCoins,checked_at:now.toISOString()}};
}

async function current(){try{const r=await fetch(PROJECT_URL+"/rest/v1/coin_snapshots?id=eq.live&select=payload",{headers:{apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY}});const rows=await r.json();return rows[0]?.payload||{}}catch{return {}}}
async function save(payload){const r=await fetch(PROJECT_URL+"/rest/v1/coin_snapshots?on_conflict=id",{method:"POST",headers:{apikey:SERVICE_KEY,Authorization:"Bearer "+SERVICE_KEY,"Content-Type":"application/json",Prefer:"resolution=merge-duplicates,return=minimal"},body:JSON.stringify([{id:"live",payload,updated_at:payload.heartbeat}])});if(!r.ok)throw Error("Supabase save "+r.status+" "+await r.text())}

function publicSignal(s){return {id:s.id,symbol:s.symbol,side:s.side,status:s.status,entry_price:Number(s.entry_price),invalidation_price:Number(s.invalidation_price),target_price:Number(s.target_price),confidence:Number(s.confidence),created_at:s.created_at,expires_at:s.expires_at,closed_at:s.closed_at,exit_price:s.exit_price==null?null:Number(s.exit_price),result_pct:s.result_pct==null?null:Number(s.result_pct),close_reason:s.close_reason}}
async function historyResponse(req){
  const u=new URL(req.url),page=Math.max(1,Number(u.searchParams.get("page")||1)),limit=Math.min(20,Math.max(1,Number(u.searchParams.get("limit")||20)));
  const symbol=String(u.searchParams.get("symbol")||"").toUpperCase(),offset=(page-1)*limit;
  let url=PROJECT_URL+"/rest/v1/trade_signals?select=id,symbol,side,status,entry_price,invalidation_price,target_price,confidence,created_at,expires_at,closed_at,exit_price,result_pct,close_reason&order=created_at.desc&limit="+limit+"&offset="+offset;
  if(COINS.includes(symbol))url+="&symbol=eq."+symbol;
  const r=await fetch(url,{headers:adminHeaders({Prefer:"count=exact"})});if(!r.ok)throw Error("history page "+r.status+" "+await r.text());
  const rows=(await r.json()).map(publicSignal),range=r.headers.get("content-range")||"",total=Number(range.split("/")[1]||rows.length);
  return Response.json({ok:true,page,limit,total,pages:Math.max(1,Math.ceil(total/limit)),rows},{headers:{"Access-Control-Allow-Origin":"*","Cache-Control":"no-store"}});
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
    const payload={...old,issues,market,status,active_signals:signalState.active,signal_candidates:signalState.candidates,signal_health:signalState.health,signal_cooldowns:signalState.cooldowns,market_regime:signalState.regime,recent_signals:signalState.recent,stats:{today:day.length,urgent:day.filter(x=>["S","A"].includes(x.grade)).length,good:day.filter(x=>x.direction==="호재").length,bad:day.filter(x=>x.direction==="악재").length},hot_themes:themes(issues),hot_events:old.hot_events||[],started:old.started||new Date().toISOString(),heartbeat:new Date().toISOString(),collector:"supabase-cloud"};
    await save(payload);
    return Response.json({ok:true,heartbeat:payload.heartbeat,issues:issues.length,markets:Object.keys(market),active_signals:signalState.active.length,candidates:signalState.candidates});
  }catch(e){console.error(e);return Response.json({ok:false,error:String(e)},{status:500})}
});