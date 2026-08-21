from __future__ import annotations

import hashlib, html, json, math, os, re, sqlite3, statistics, sys, threading, time
import urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = Path(os.getenv("COIN_DB_PATH", str(ROOT / "coin_issues.db")))
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
LOCK = threading.Lock()
STATUS = {}
MARKET = {}
STARTED = datetime.now(timezone.utc).isoformat()
SNAPSHOT_FILE = ROOT / "latest_snapshot.json"

def load_env():
    p = ROOT / ".env"
    if not p.exists(): return
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw=raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            k,v=raw.split("=",1); os.environ.setdefault(k.strip(),v.strip())
load_env()

POS = {"approve":5,"approved":5,"launch":3,"adoption":3,"partnership":2,"invest":2,"inflow":2,"record high":3,"legal clarity":3,"허용":5,"승인":5,"출시":3,"채택":3,"유입":2,"상승":2}
NEG = {"ban":6,"banned":6,"hack":6,"exploit":6,"lawsuit":4,"charges":4,"indict":5,"reject":5,"outflow":2,"liquidation":3,"shutdown":5,"fraud":4,"비상":5,"금지":6,"해킹":6,"기소":4,"거부":5,"유출":3,"청산":3,"중단":5,"사기":4}
BIG = {"cftc":4,"sec ":4,"federal reserve":5,"fomc":6,"powell":5,"treasury":4,"white house":5,"congress":3,"etf":5,"bitcoin":2,"ethereum":2,"binance":3,"coinbase":3,"stablecoin":3,"interest rate":5,"inflation":4,"cpi":5,"employment":4}
CRYPTO = ("crypto","cryptocurrency","digital asset","bitcoin","btc","ethereum","ether","eth ","xrp","ripple","solana"," sol ","blockchain","token","stablecoin","usdt","usdc","defi","web3","binance","coinbase","kraken","bybit","okx","exchange-traded fund","spot etf","현물 etf","가상자산","암호화폐","비트코인","이더리움","리플","솔라나","코인","토큰","거래소")
MACRO = ("fomc","interest rate","rate cut","rate hike","cpi","inflation","nonfarm payroll","federal reserve","powell","liquidity","금리","인플레이션","유동성")
EXCHANGE_IMPACT = ("list","listing","delist","suspend","resume","deposit","withdraw","wallet maintenance","network upgrade","security","hack","exploit","proof of reserves","insolvency","bankruptcy","regulatory","license","launchpool","megadrop","상장","상폐","입금","출금","중단","재개","지갑 점검","네트워크 업그레이드","해킹","보안","준비금","파산","규제","라이선스")
EXCHANGE_NOISE = ("dual investment","api functionality","promotion","campaign","quiz","webinar","learn and earn","vip loan","copy trading","trading bot","fee promotion","general update","듀얼 투자","프로모션","이벤트","퀴즈","수수료 할인")
MEDIA_NOISE = ("here's what happened","what happened in crypto today","price prediction","top coins to buy","sponsored","press release","opinion:","explained","weekly recap","daily recap","a year after","long & short:")

def db(sql, args=(), fetch=False):
    with LOCK:
        c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
        try:
            cur=c.execute(sql,args); out=[dict(x) for x in cur.fetchall()] if fetch else None; c.commit(); return out
        finally: c.close()

def init_db():
    db("""CREATE TABLE IF NOT EXISTS issues(id TEXT PRIMARY KEY, source TEXT, source_type TEXT, title TEXT, summary TEXT, url TEXT, published TEXT, detected TEXT, delay_sec INTEGER, grade TEXT, score INTEGER, direction TEXT, confidence INTEGER, assets TEXT, category TEXT, reaction TEXT, investor_note TEXT, horizon TEXT, ai INTEGER DEFAULT 0)""")
    db("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
    db("""CREATE TABLE IF NOT EXISTS hot_events(id TEXT PRIMARY KEY, title TEXT, event_time TEXT, source TEXT, url TEXT, grade TEXT, direction TEXT, reason TEXT, watch TEXT, detected TEXT)""")
    cutoff=datetime.fromtimestamp(time.time()-int(CFG.get("max_item_age_hours",48))*3600,timezone.utc).isoformat()
    db("DELETE FROM issues WHERE detected < ? OR (published LIKE '____-__-__T%' AND published < ?)",(cutoff,cutoff))
    db("DELETE FROM hot_events WHERE event_time < ?",(datetime.now(timezone.utc).isoformat(),))
    seed_fomc()

def clean(s): return re.sub(r"\s+"," ",re.sub(r"<[^>]*>"," ",html.unescape(s or ""))).strip()
def duplicate_title(title):
    stop={"the","a","an","to","of","in","on","for","and","as","at","with","after","from","says","new"}
    words={w for w in re.findall(r"[a-z0-9]+",title.lower()) if len(w)>2 and w not in stop}
    if len(words)<4: return False
    for row in db("SELECT title FROM issues ORDER BY detected DESC LIMIT 100",fetch=True):
        other={w for w in re.findall(r"[a-z0-9]+",row["title"].lower()) if len(w)>2 and w not in stop}
        if other and len(words&other)/len(words|other)>=0.55: return True
    return False
def txt(node, names):
    for n in list(node):
        if n.tag.split("}")[-1].lower() in names and (n.text or "").strip(): return n.text.strip()
    return ""

def fetch_feed(src):
    req=urllib.request.Request(src["url"],headers={"User-Agent":"CoinIssueAI/1.0 contact=local-user","Accept":"application/rss+xml, application/atom+xml, text/xml"})
    with urllib.request.urlopen(req,timeout=12) as r: data=r.read(3_000_000)
    if src.get("format")=="binance_json":
        j=json.loads(data); out=[]
        for catalog in j.get("data",{}).get("catalogs",[]):
            for a in catalog.get("articles",[])[:20]:
                code=a.get("code",""); url="https://www.binance.com/en/support/announcement/"+code
                stamp=a.get("releaseDate"); date=datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat() if stamp else ""
                out.append((clean(a.get("title","")),url,clean(catalog.get("catalogName","")),date))
        return out
    root=ET.fromstring(data); out=[]
    nodes=[x for x in root.iter() if x.tag.split("}")[-1].lower() in ("item","entry")]
    for n in nodes[:40]:
        title=clean(txt(n,{"title"})); link=txt(n,{"link"})
        if not link:
            for x in n:
                if x.tag.split("}")[-1].lower()=="link" and x.attrib.get("href"): link=x.attrib["href"]; break
        desc=clean(txt(n,{"description","summary","content","encoded"}))
        date=txt(n,{"pubdate","published","updated","date"})
        out.append((title,link,desc,date))
    return out

def parse_date(s):
    if not s: return None
    try: return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        try: return datetime.fromisoformat(s.replace("Z","+00:00")).astimezone(timezone.utc)
        except Exception: return None

MONTHS={"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
def event_date(text):
    now=datetime.now(timezone.utc)
    m=re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b",text)
    if m: return datetime(int(m[1]),int(m[2]),int(m[3]),18,tzinfo=timezone.utc)
    m=re.search(r"\b("+"|".join(MONTHS)+r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d{2}))?",text.lower())
    if m:
        year=int(m[3] or now.year); d=datetime(year,MONTHS[m[1]],int(m[2]),18,tzinfo=timezone.utc)
        if not m[3] and d<now-timedelta(days=2): d=d.replace(year=year+1)
        return d
    return None

def hot_profile(title):
    t=title.lower()
    if "fomc" in t: return "S","양방향 변동성","금리·유동성 기대를 바꿔 전체 코인시장을 크게 움직일 수 있습니다.","성명·점도표·의장 기자회견, DXY와 국채금리 동시 확인"
    if "clarity" in t: return "S","호재 가능","미국 암호화폐 시장구조의 법적 불확실성을 줄일 가능성이 있어 기관 자금 기대와 연결됩니다.","표결·수정안·양당 지지 여부와 실제 통과 단계 확인"
    if "cftc" in t or "sec" in t: return "A","호재/악재 확인","미국 규제기관의 공식 발언은 ETF·거래소·파생상품 규칙 기대를 즉시 바꿀 수 있습니다.","준비 연설문과 라이브 핵심 문장, 기존 정책 대비 새 표현 확인"
    if any(k in t for k in ("hearing","congress","senate","house")): return "A","정책 방향 확인","의회 일정은 법안 통과 가능성과 규제 기대를 선반영시킬 수 있습니다.","위원 명단·표결 일정·수정안과 공식 발언 확인"
    return "B","변동성 가능","예정된 공식 일정 전후로 관련 자산의 기대가 먼저 반영될 수 있습니다.","일정 변경 여부와 가격·거래량 선행 반응 확인"

def detect_hot(title, body, source, url):
    text=title+" "+body
    low=text.lower()
    if not any(k in low for k in ("will ","to meet","meeting","to speak","speech","hearing","fomc","clarity","roundtable","conference","위원장","연설","회의","청문회","법안")): return
    when=event_date(text)
    now=datetime.now(timezone.utc)
    if not when or when<now-timedelta(hours=6) or when>now+timedelta(days=120): return
    grade,direction,reason,watch=hot_profile(title+" "+source)
    iid=hashlib.sha256((source+when.date().isoformat()).encode()).hexdigest()[:24]
    db("INSERT OR REPLACE INTO hot_events VALUES(?,?,?,?,?,?,?,?,?,?)",(iid,title,when.isoformat(),source,url,grade,direction,reason,watch,now.isoformat()))

def seed_fomc():
    official="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    for iso,title in (("2026-09-16T18:00:00+00:00","FOMC 9월 금리 결정·경제전망·기자회견"),("2026-10-28T18:00:00+00:00","FOMC 10월 금리 결정·기자회견"),("2026-12-09T19:00:00+00:00","FOMC 12월 금리 결정·경제전망·기자회견"),("2027-01-27T19:00:00+00:00","FOMC 1월 금리 결정·기자회견")):
        when=datetime.fromisoformat(iso)
        if when>datetime.now(timezone.utc):
            grade,direction,reason,watch=hot_profile(title); iid=hashlib.sha256(title.encode()).hexdigest()[:24]
            db("INSERT OR IGNORE INTO hot_events VALUES(?,?,?,?,?,?,?,?,?,?)",(iid,title,iso,"Federal Reserve",official,grade,direction,reason,watch,datetime.now(timezone.utc).isoformat()))

def hot_themes():
    rows=db("SELECT title,summary,grade,direction,assets,url,source FROM issues WHERE detected >= ?",(datetime.fromtimestamp(time.time()-86400,timezone.utc).isoformat(),),True)
    specs=[
        ("미국 CLARITY 법안·시장구조",("clarity","market structure"),"미국 암호화폐 규제의 법적 명확성과 기관 진입 기대를 바꿀 수 있는 핵심 테마입니다.","표결 단계·수정안·양당 지지와 CFTC/SEC 권한 배분 확인"),
        ("미국 CFTC·SEC 암호화폐 정책",("cftc","sec ","crypto regulation","digital asset regulation"),"미국 규제기관의 발언과 규칙 변화가 시장 전체의 위험 프리미엄을 바꿀 수 있습니다.","공식 원문에서 확정·제안·개인 의견을 구분하고 시행일 확인"),
        ("현물 ETF·기관 자금 흐름",("etf","institutional inflow","institutional outflow"),"ETF 자금 흐름은 BTC·ETH 현물 수요와 기관 심리를 직접 보여주는 선행 지표입니다.","일일 순유입 지속성과 가격·거래량 동행 여부 확인"),
        ("대형 해킹·네트워크 위험",("hack","exploit","breach","network halt"),"보안 사고와 체인 중단은 관련 자산의 즉각적인 유동성·신뢰 위험으로 이어질 수 있습니다.","실제 피해액·추가 유출·입출금 중단·공식 복구 공지 확인")]
    out=[]
    for name,keys,reason,watch in specs:
        hits=[x for x in rows if any(k in (x["title"]+" "+x["summary"]).lower() for k in keys)]
        if not hits: continue
        pos=sum(x["direction"]=="호재" for x in hits); neg=sum(x["direction"]=="악재" for x in hits)
        direction="호재 우세" if pos>neg else "악재 우세" if neg>pos else "방향 확인 중"
        grade="S" if len(hits)>=3 or any(x["grade"]=="S" for x in hits) else "A" if len(hits)>=2 or any(x["grade"]=="A" for x in hits) else "B"
        assets=sorted({a for x in hits for a in x["assets"].split(",")})
        out.append({"title":name,"grade":grade,"direction":direction,"reason":reason,"watch":watch,"evidence_count":len(hits),"assets":",".join(assets),"url":hits[0]["url"],"source":"복수 출처 종합"})
    return out

def relevant(title, body, source_type):
    t=(title+" "+body[:1200]).lower()
    if source_type=="media" and any(k in t for k in MEDIA_NOISE): return False
    if source_type=="exchange":
        if any(k in t for k in EXCHANGE_NOISE): return False
        return any(k in t for k in EXCHANGE_IMPACT)
    return any(k in t for k in CRYPTO) or (any(k in t for k in MACRO) and any(k in t for k in ("market","risk asset","bitcoin","crypto","liquidity")))

def investor_view(title, direction, assets, category, reaction):
    t=title.lower(); coin=assets.split(",")[0]
    if "상폐" in t or "delist" in t:
        return f"{coin} 유동성과 접근성이 급감할 수 있습니다. 보유·선물 포지션과 다른 거래소의 동반 상폐 여부를 즉시 확인하세요.", "즉시~24시간"
    if any(k in t for k in ("hack","exploit","해킹","security breach")):
        return f"추가 자금 유출과 입출금 중단 가능성이 있습니다. {coin} 입출금 상태·공격 지갑·프로젝트 공식 대응을 확인하기 전 추격 진입을 피하세요.", "즉시~72시간"
    if any(k in t for k in ("suspend","중단","wallet maintenance","지갑 점검")):
        return "거래소 간 이동 제한으로 가격 괴리와 변동성이 커질 수 있습니다. 해당 거래소의 입출금 재개 시각과 타 거래소 가격을 비교하세요.", "즉시~24시간"
    if "상장" in t or "listing" in t:
        return f"신규 유동성 유입 가능성이 있지만 발표 직후 급등분은 되돌림 위험이 큽니다. {coin} 현물 거래 개시 시각·입금 개방·선물 선행 상장 여부를 확인하세요.", "발표~거래개시 24시간"
    if category=="규제·ETF":
        return "확정 결정인지 단순 발언·검토인지 구분해야 합니다. 공식 문서의 시행일과 대상 자산, 시장 선반영 여부를 확인하세요.", "즉시~수일"
    if category=="거시경제":
        return "달러·국채금리와 위험자산 유동성에 영향을 줄 수 있습니다. BTC 방향뿐 아니라 DXY와 미 국채금리의 동시 반응을 확인하세요.", "발표 직후~24시간"
    if direction=="악재": return f"예상 악재지만 현재 반응은 ‘{reaction}’입니다. 가격·거래량이 확인되기 전 제목만으로 추격 매도하지 마세요.", "즉시~24시간"
    if direction=="호재": return f"예상 호재이며 현재 반응은 ‘{reaction}’입니다. 이미 급등했다면 선반영 가능성과 거래량 지속 여부를 먼저 확인하세요.", "즉시~24시간"
    return "방향성이 확정되지 않은 정보입니다. 공식 원문과 가격·거래량 반응이 확인될 때까지 관찰 대상으로 두세요.", "관찰"

def candles(symbol, interval="1h", limit=500):
    q=urllib.parse.urlencode({"symbol":symbol+"USDT","interval":interval,"limit":limit})
    req=urllib.request.Request("https://api.binance.com/api/v3/klines?"+q,headers={"User-Agent":"CoinIssueAI/4.0"})
    with urllib.request.urlopen(req,timeout=12) as r: rows=json.loads(r.read())
    return [float(x[4]) for x in rows],[float(x[5]) for x in rows]

def ema(values, period):
    a=2/(period+1); out=values[0]
    for v in values[1:]: out=a*v+(1-a)*out
    return out

def prediction(symbol, price):
    closes,volumes=candles(symbol)
    if len(closes)<170: return {}
    short_closes,short_volumes=candles(symbol,"5m",288)
    rets=[math.log(closes[i]/closes[i-1]) for i in range(1,len(closes)) if closes[i-1]>0]
    vol_h=statistics.pstdev(rets[-168:]); daily_vol=vol_h*math.sqrt(24)*100
    mom24=(closes[-1]/closes[-25]-1)*100; mom72=(closes[-1]/closes[-73]-1)*100; mom7=(closes[-1]/closes[-169]-1)*100
    trend=(ema(closes[-100:],12)/ema(closes[-100:],26)-1)*100
    gains=[]; losses=[]
    for i in range(-14,0):
        d=closes[i]-closes[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/14; al=sum(losses)/14; rsi=100 if al==0 else 100-(100/(1+ag/al))
    v1=sum(volumes[-24:]); v0=sum(volumes[-48:-24]) or 1; volume_ratio=v1/v0
    news=0.0; news_count=0
    for x in db("SELECT grade,direction,confidence,assets FROM issues WHERE detected >= ?",(datetime.fromtimestamp(time.time()-86400,timezone.utc).isoformat(),),True):
        if symbol in x["assets"] or "시장전체" in x["assets"]:
            w={"S":4,"A":3,"B":2,"C":1,"D":.5}.get(x["grade"],1)*(x["confidence"]/100)
            news += w*(1 if x["direction"]=="호재" else -1 if x["direction"]=="악재" else 0); news_count+=1
    short15=(short_closes[-1]/short_closes[-4]-1)*100
    short60=(short_closes[-1]/short_closes[-13]-1)*100
    short4h=(short_closes[-1]/short_closes[-49]-1)*100
    ema9=ema(short_closes[-80:],9); ema21=ema(short_closes[-80:],21); ema50=ema(short_closes[-100:],50)
    short_trend=(ema9/ema21-1)*100
    below_fast=price<ema9 and price<ema21; below_structure=price<ema50
    short_volume=sum(short_volumes[-12:])/(sum(short_volumes[-24:-12]) or 1)
    heat=-max(0,(rsi-72)/8)+max(0,(28-rsi)/8)
    exhaustion=max(0,mom24-6)*.35-min(0,mom24+6)*.25
    intraday=.30*short15+.32*short60+.18*short4h+.65*short_trend
    if below_fast: intraday-=.45
    if below_structure: intraday-=.35
    p24=max(-14,min(14,.25*mom24+.08*(mom72/3)+.16*trend+.34*news+.30*heat-exhaustion+intraday))
    p7=max(-35,min(35,.38*mom7+.20*mom72+.75*trend+1.2*news+.5*heat-.35*exhaustion))
    if rsi>=78 and p24>0: p24*=.62
    elif rsi>=72 and p24>0: p24*=.82
    if rsi>=78 and p7>0: p7*=.78
    elif rsi>=72 and p7>0: p7*=.84
    if rsi<=22 and p24<0: p24*=.62
    if rsi<=22 and p7<0: p7*=.78
    center24=price*(1+p24/100); center7=price*(1+p7/100)
    band24=max(daily_vol*.85,1.2); band7=max(daily_vol*math.sqrt(7)*.8,3)
    agreement=sum((x>0)==(p24>0) for x in (mom24,mom72,mom7,trend,news) if x!=0); signals=sum(x!=0 for x in (mom24,mom72,mom7,trend,news))
    trend_points=round((agreement/max(1,signals))*25)
    if 1.1<=volume_ratio<=2.5: volume_points=20
    elif 2.5<volume_ratio<=4: volume_points=16
    elif .8<=volume_ratio<1.1: volume_points=12
    elif volume_ratio>4: volume_points=10
    else: volume_points=6
    if news_count==0: news_points=5
    else:
        same=(news>0 and p24>0) or (news<0 and p24<0)
        news_points=min(20,10+round(abs(news)*2)) if same else 6
    risk_points=20
    if rsi>=78 or rsi<=22: risk_points-=14
    elif rsi>=72 or rsi<=28: risk_points-=8
    risk_points-=min(6,round(max(0,daily_vol-4)))
    risk_points=max(0,risk_points)
    data_points=15 if len(closes)>=500 else 12
    total_score=trend_points+volume_points+news_points+risk_points+data_points
    strength=(p24/max(1,daily_vol))+(p7/max(3,daily_vol*math.sqrt(7)))
    if below_fast and short60<-.35: rec="단기 조정 우세·지지 회복 확인"
    elif total_score<60: rec="종합 추천 보류·추가 확인"
    elif rsi>=72 and mom24>5: rec="신규 추격매수 보류·조정 관찰"
    elif rsi<=28 and mom24<-5: rec="성급한 손절 보류·반등 확인"
    elif strength>=1.2 and volume_ratio>=1 and total_score>=80: rec="강한 상승 우세·분할 진입 관찰"
    elif strength>=.45: rec="상승 우세·분할 진입 관찰"
    elif strength<=-1.2 and volume_ratio>=1 and total_score>=80: rec="강한 하락 위험·노출 축소 검토"
    elif strength<=-.45: rec="하락 위험·신규 진입 주의"
    else: rec="중립·확인 대기"
    directional=max(-1,min(1,intraday/max(.6,daily_vol/3)))
    bull_prob=round(max(12,min(48,27+directional*15+(4 if news>1 else 0)-(7 if rsi>75 else 0))))
    bear_prob=round(max(12,min(48,27-directional*15+(7 if below_fast else 0)+(5 if below_structure else 0))))
    base_prob=100-bull_prob-bear_prob
    if base_prob<24:
        trim=24-base_prob; bull_prob-=trim//2; bear_prob-=trim-trim//2; base_prob=24
    def sc(change,prob,trigger):
        band=max(.65,daily_vol*.42); center=price*(1+change/100)
        return {"center":center,"low":center*(1-band/100),"high":center*(1+band/100),"change":change,"prob":prob,"trigger":trigger}
    base_change=max(-5,min(5,p24*.45)); bull_change=max(1,abs(p24)*.7+daily_vol*.55); bear_change=-max(1,abs(p24)*.55+daily_vol*.55)
    scenarios24={"base":sc(base_change,base_prob,"5분 추세가 중립권에서 유지"),"bull":sc(bull_change,bull_prob,f"EMA9 {ema9:.4g}·EMA21 {ema21:.4g} 위로 회복"),"bear":sc(bear_change,bear_prob,f"EMA50 {ema50:.4g} 아래 안착 또는 최근 저점 재이탈")}
    wband=max(2,daily_vol*math.sqrt(7)*.55)
    def sc7(change,prob,trigger):
        center=price*(1+change/100); return {"center":center,"low":center*(1-wband/100),"high":center*(1+wband/100),"change":change,"prob":prob,"trigger":trigger}
    scenarios7={"base":sc7(max(-12,min(12,p7*.45)),base_prob,"거시·ETF·뉴스 흐름 유지"),"bull":sc7(max(3,abs(p7)*.75+wband*.5),bull_prob,"주요 저항 돌파와 현물 거래량 확인"),"bear":sc7(-max(3,abs(p7)*.65+wband*.5),bear_prob,"단기 지지 붕괴와 거래량 동반 매도")}
    direction_confidence=round(max(35,min(82,45+abs(directional)*22+min(10,abs(news)*2))))
    trend_strength=round(max(0,min(100,50+directional*38)))
    direction="상승" if directional>.18 else "하락" if directional<-.18 else "중립"
    risks=[]
    if mom24>7: risks.append("급등 후 차익실현")
    if below_fast: risks.append("5분 단기 추세선 하회")
    if short_volume>1.5: risks.append("최근 거래량 급증")
    if not risks: risks.append("예상 밖 뉴스·거시 변수")
    reasons=[f"15분 {short15:+.2f}%",f"1시간 {short60:+.2f}%",f"4시간 {short4h:+.2f}%",f"24h {mom24:+.2f}%",f"거래량 {volume_ratio:.2f}배",f"RSI {rsi:.1f}",f"뉴스 {news:+.1f}"]
    return {"forecast24":{"center":center24,"low":center24*(1-band24/100),"high":center24*(1+band24/100),"change":p24},"forecast7d":{"center":center7,"low":center7*(1-band7/100),"high":center7*(1+band7/100),"change":p7},"scenarios24":scenarios24,"scenarios7d":scenarios7,"volume_ratio":volume_ratio,"daily_volatility":daily_vol,"rsi":rsi,"news_score":news,"news_count":news_count,"recommendation":rec,"trend_direction":direction,"trend_strength":trend_strength,"direction_confidence":direction_confidence,"risks":risks,"pullback_range":{"low":min(ema21,ema50),"high":max(ema21,ema50)},"analysis_coverage":["5분 구조","1시간 추세","24시간 모멘텀","거래량","변동성","뉴스"],"total_score":total_score,"score_breakdown":{"추세 일치":trend_points,"거래량 확인":volume_points,"뉴스 뒷받침":news_points,"위험 건전성":risk_points,"데이터 품질":data_points},"reasons":reasons,"analysis_updated":datetime.now(timezone.utc).isoformat()}

def analyze(title, body, weight, source_type):
    t=(title+" "+body[:700]).lower(); pos=sum(v for k,v in POS.items() if k in t); neg=sum(v for k,v in NEG.items() if k in t)
    impact=sum(v for k,v in BIG.items() if k in t); score=min(100, 12+weight*5+impact*4+max(pos,neg)*4)
    if score>=85: grade="S"
    elif score>=65: grade="A"
    elif score>=45: grade="B"
    elif score>=25: grade="C"
    else: grade="D"
    direction="호재" if pos>neg+1 else "악재" if neg>pos+1 else "중립"
    assets=[]
    for key,sym in (("bitcoin","BTC"),("btc","BTC"),("ethereum","ETH"),("ether","ETH"),("solana","SOL"),("xrp","XRP"),("ripple","XRP"),("bnb","BNB"),("stablecoin","STABLE"),("usdt","STABLE"),("usdc","STABLE"),("crypto","시장전체")):
        if key in t and sym not in assets: assets.append(sym)
    if any(k in t for k in MACRO) and "시장전체" not in assets: assets.append("시장전체")
    category="거래소 공지" if source_type=="exchange" else "규제·ETF" if any(k in t for k in ("sec ","cftc","regulation","etf","법안","규제")) else "해킹·보안" if any(k in t for k in ("hack","exploit","breach","해킹","취약점")) else "거시경제" if any(k in t for k in MACRO) else "코인 이슈"
    focus=next((a for a in assets if a in MARKET),"BTC")
    move=float(MARKET.get(focus,{}).get("change",0)); reaction="반응 확인 전"
    if direction=="악재" and move>1: reaction=f"시장 무시 중 ({focus} 24h +{move:.2f}%)"; score=max(10,score-12)
    elif direction=="호재" and move<-1: reaction=f"시장 미반영/약세 ({focus} 24h {move:.2f}%)"; score=max(10,score-8)
    elif direction=="악재" and move<-1: reaction=f"하락 반응 확인 ({focus} 24h {move:.2f}%)"; score=min(100,score+8)
    elif direction=="호재" and move>1: reaction=f"상승 반응 확인 ({focus} 24h +{move:.2f}%)"; score=min(100,score+8)
    if score>=85: grade="S"
    elif score>=65: grade="A"
    elif score>=45: grade="B"
    elif score>=25: grade="C"
    else: grade="D"
    return grade,score,direction,min(96,55+weight*6+abs(pos-neg)*3),",".join(assets or ["시장전체"]),category,reaction

def market_loop():
    symbols=["BTCUSDT","ETHUSDT","XRPUSDT","SOLUSDT","BNBUSDT"]
    url="https://api.binance.com/api/v3/ticker/24hr?"+urllib.parse.urlencode({"symbols":json.dumps(symbols,separators=(",",":"))})
    last_prediction=0
    while True:
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"CoinIssueAI/2.0"})
            with urllib.request.urlopen(req,timeout=10) as r: rows=json.loads(r.read())
            with LOCK:
                for x in rows:
                    sym=x["symbol"].replace("USDT",""); MARKET.setdefault(sym,{}).update({"price":float(x["lastPrice"]),"change":float(x["priceChangePercent"]),"quoteVolume":float(x["quoteVolume"]),"updated":datetime.now(timezone.utc).isoformat()})
            if time.time()-last_prediction>=60:
                for sym in ["BTC","ETH","XRP","SOL","BNB"]:
                    try:
                        extra=prediction(sym,float(MARKET.get(sym,{}).get("price",0)))
                        with LOCK: MARKET.setdefault(sym,{}).update(extra)
                    except Exception as e: STATUS["예측 "+sym]={"ok":False,"checked":datetime.now(timezone.utc).isoformat(),"items":0,"new":0,"error":str(e)[:160]}
                last_prediction=time.time()
        except Exception as e: STATUS["실시간 시세"]={"ok":False,"checked":datetime.now(timezone.utc).isoformat(),"items":0,"new":0,"error":str(e)[:160]}
        time.sleep(max(5,int(CFG.get("market_refresh_seconds",10))))

def ai_summary(title, body):
    key=os.getenv("OPENAI_API_KEY","")
    if not key: return None
    prompt=f"제목: {title}\n본문: {body[:2200]}\n한국어 2문장으로 사실만 요약. 첫 문장은 무슨 발표인지, 둘째 문장은 암호화폐 시장 영향 가능성. 과장 금지."
    payload=json.dumps({"model":os.getenv("OPENAI_MODEL","gpt-5-mini"),"input":prompt}).encode()
    req=urllib.request.Request("https://api.openai.com/v1/responses",data=payload,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=25) as r: j=json.loads(r.read())
        return clean(j.get("output_text", "")) or None
    except Exception: return None

def telegram(issue):
    token=os.getenv("TELEGRAM_BOT_TOKEN",""); chat=os.getenv("TELEGRAM_CHAT_ID","")
    if not token or not chat: return
    icon="🚨" if issue["grade"]=="S" else "⚡"
    msg=f'{icon} {issue["grade"]}급 | {issue["direction"]}\n\n{issue["title"]}\n\n{issue["summary"][:600]}\n\n관련: {issue["assets"]} | 감지지연: {issue["delay_sec"]}초\n출처: {issue["source"]}\n{issue["url"]}'
    data=urllib.parse.urlencode({"chat_id":chat,"text":msg,"disable_web_page_preview":"true"}).encode()
    try: urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",data=data),timeout=10).read()
    except Exception: pass

def process_source(src, baseline):
    now=datetime.now(timezone.utc)
    try:
        items=fetch_feed(src); new=0
        for title,url,body,date_s in reversed(items):
            if not title: continue
            detect_hot(title,body,src["name"],url)
            if not relevant(title,body,src.get("type","media")): continue
            iid=hashlib.sha256((url or title).encode()).hexdigest()[:24]
            if db("SELECT id FROM issues WHERE id=?",(iid,),True): continue
            if duplicate_title(title): continue
            published=parse_date(date_s); delay=max(0,int((now-published).total_seconds())) if published else 0
            max_age=int(CFG.get("max_item_age_hours",48))*3600
            if published and ((now-published).total_seconds()>max_age or (published-now).total_seconds()>21600): continue
            grade,score,direction,confidence,assets,category,reaction=analyze(title,body,src.get("weight",2),src.get("type","media"))
            if score<int(CFG.get("minimum_issue_score",45)): continue
            investor_note,horizon=investor_view(title,direction,assets,category,reaction)
            summary=(body[:500] or title); ai=0
            if not baseline:
                a=ai_summary(title,body)
                if a: summary=a; ai=1
            issue={"id":iid,"source":src["name"],"source_type":src.get("type","media"),"title":title,"summary":summary,"url":url,"published":published.isoformat() if published else date_s,"detected":now.isoformat(),"delay_sec":delay,"grade":grade,"score":score,"direction":direction,"confidence":confidence,"assets":assets,"category":category,"reaction":reaction,"investor_note":investor_note,"horizon":horizon,"ai":ai}
            db("INSERT OR IGNORE INTO issues VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",tuple(issue.values()))
            new+=1
            if not baseline and "SABCD".index(grade)<= "SABCD".index(CFG.get("minimum_telegram_grade","A")): telegram(issue)
        STATUS[src["name"]]={"ok":True,"checked":now.isoformat(),"items":len(items),"new":new,"error":""}
    except Exception as e: STATUS[src["name"]]={"ok":False,"checked":now.isoformat(),"items":0,"new":0,"error":str(e)[:160]}

def monitor():
    baseline=not bool(db("SELECT value FROM meta WHERE key='initialized'",fetch=True)) and not CFG.get("first_run_alerts",False)
    while True:
        threads=[]
        for src in CFG["sources"]:
            if src.get("enabled",True):
                t=threading.Thread(target=process_source,args=(src,baseline),daemon=True); t.start(); threads.append(t)
        for t in threads: t.join(30)
        if baseline: db("INSERT OR REPLACE INTO meta VALUES('initialized','1')"); baseline=False
        time.sleep(max(5,int(CFG.get("poll_seconds",15))))

PAGE=r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Coin Issue AI</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#080b12;color:#edf2ff;font:14px system-ui}header{padding:22px 4%;border-bottom:1px solid #20283a;background:#0c111c;position:sticky;top:0;z-index:2}.top{display:flex;align-items:center;justify-content:space-between;gap:12px}h1{margin:0;font-size:22px}.live{color:#65f5ad}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#2ee98b;box-shadow:0 0 10px #2ee98b;margin-right:7px}.wrap{padding:20px 4%;max-width:1450px;margin:auto}.stats,.market{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:18px}.stat,.ticker,.card,.sources{background:#101725;border:1px solid #263149;border-radius:13px;padding:14px}.num{font-size:25px;font-weight:800;margin-top:7px}.ticker b{font-size:17px}.tabs{display:flex;gap:7px;margin:15px 0;flex-wrap:wrap}button{background:#172033;color:#dbe7ff;border:1px solid #31405e;padding:9px 14px;border-radius:9px;cursor:pointer}button.on{background:#295ee8;border-color:#5280ff}.grid{display:grid;grid-template-columns:1fr 310px;gap:14px}.card{margin-bottom:10px}.head{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.grade{font-weight:900;font-size:16px;border-radius:7px;padding:5px 9px}.S{background:#d92b50}.A{background:#e26c28}.B{background:#b08b21}.C,.D{background:#3c4d69}.good{color:#55eba2}.bad{color:#ff6c7d}.neutral{color:#aebbd0}.reaction{margin-top:9px;padding:8px;border-radius:7px;background:#172033;color:#d6e1f5}.recgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:15px}.rec{background:#101725;border:1px solid #315780;border-radius:13px;padding:16px}.forecast{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.forecast div{background:#172033;padding:10px;border-radius:8px;line-height:1.5}.invest{margin-top:9px;padding:11px;border-radius:8px;background:#11251e;border:1px solid #245c47;color:#d9f7ea;line-height:1.55}.title{font-size:17px;font-weight:750;margin:12px 0 8px}.summary{color:#bdc8dc;line-height:1.6}.meta{color:#7f90ac;font-size:12px;margin-top:11px}.meta a{color:#77a5ff}.source-row{padding:9px 0;border-bottom:1px solid #202b40}.err{color:#ff7180}.ok{color:#57e5a0}@media(max-width:800px){.stats,.market{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr}.sources{order:-1}}</style></head><body>
<header><div class="top"><h1>⚡ Coin Issue AI v7</h1><div class="live"><span class="dot"></span>실시간 감시 중 · <span id="clock"></span></div></div></header><div class="wrap"><div class="market" id="market"></div><div class="stats"><div class="stat">오늘 감지<div class="num" id="today">0</div></div><div class="stat">긴급 S/A<div class="num" id="urgent">0</div></div><div class="stat">호재<div class="num good" id="good">0</div></div><div class="stat">악재<div class="num bad" id="bad">0</div></div><div class="stat">시장 상태<div class="num" id="regime">-</div></div></div><div class="tabs"><button class="on" data-f="ALL">전체</button><button data-f="RECOMMEND">⭐ 종합추천</button><button data-f="HOT">🔥 핫이슈</button><button data-f="S,A">🚨 S/A급</button><button data-f="BTC">BTC</button><button data-f="ETH">ETH</button><button data-f="XRP">XRP</button><button data-f="SOL">SOL</button><button data-f="BNB">BNB</button><button data-f="시장전체">시장 전체</button><button data-f="exchange">거래소 공지</button><button data-f="규제·ETF">규제·ETF</button><button data-f="해킹·보안">해킹·보안</button><button data-f="호재">호재</button><button data-f="악재">악재</button></div><div id="recommendations"></div><div class="grid"><main id="issues"></main><aside class="sources"><b>출처 상태</b><div id="sources"></div></aside></div></div><script>
let filter='ALL';document.querySelectorAll('button').forEach(b=>b.onclick=()=>{document.querySelectorAll('button').forEach(x=>x.classList.remove('on'));b.classList.add('on');filter=b.dataset.f;load()});
const esc=s=>(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const money=(n,p)=>'$'+Number(n||0).toLocaleString(undefined,{maximumFractionDigits:(p||0)<10?4:2});
function renderRecommendations(d){
  const on=['RECOMMEND','HOT'].includes(filter);document.querySelector('.grid').style.display=on?'none':'grid';recommendations.style.display=on?'grid':'none';recommendations.className='recgrid';
  if(!on)return;
  if(filter==='HOT'){
    let vals=Object.values(d.market),avg=vals.length?vals.reduce((a,v)=>a+v.change,0)/vals.length:0,vr=vals.filter(v=>v.volume_ratio).reduce((a,v)=>a+v.volume_ratio,0)/Math.max(1,vals.filter(v=>v.volume_ratio).length);
    let themes=(d.hot_themes||[]).map(e=>`<div class="rec"><div class="head"><span class="grade ${e.grade}">${e.grade}급</span><h2 style="margin:0">🔥 현재 핵심 테마: ${esc(e.title)}</h2></div><p>${esc(e.direction)} · 관련 ${esc(e.assets)} · 근거 기사 ${e.evidence_count}건</p><div class="invest"><b>왜 시장이 주목하는가</b><br>${esc(e.reason)}</div><div class="reaction"><b>다음 확인 지점</b><br>${esc(e.watch)}<br><br><b>현재 선행 반응</b><br>주요 코인 평균 24h ${avg>=0?'+':''}${avg.toFixed(2)}% · 평균 거래량 ${vr?vr.toFixed(2):'-'}배<br>${avg>2&&vr>1.5?'가격과 거래량이 동시에 강해 이 테마의 선행 반영 가능성이 있습니다. 단독 원인으로 확정하지는 않습니다.':'아직 가격·거래량의 뚜렷한 선행 반응은 확인되지 않았습니다.'}</div><div class="meta"><a target="_blank" href="${esc(e.url)}">대표 근거 확인</a></div></div>`).join('');
    let events=d.hot_events.map(e=>{let left=(new Date(e.event_time)-Date.now())/3600000;let countdown=left<24?`${Math.max(0,left).toFixed(1)}시간 후`:`${(left/24).toFixed(1)}일 후`;return `<div class="rec"><div class="head"><span class="grade ${e.grade}">${e.grade}급</span><h2 style="margin:0">📅 예정 일정: ${esc(e.title)}</h2></div><p><b>${countdown}</b> · ${new Date(e.event_time).toLocaleString()} · ${esc(e.source)}</p><p class="${e.direction.includes('호재')?'good':'neutral'}">예상 성격: ${esc(e.direction)}</p><div class="invest"><b>왜 중요한가</b><br>${esc(e.reason)}</div><div class="reaction"><b>미리 확인할 것</b><br>${esc(e.watch)}<br><br><b>현재 선행 반응</b><br>주요 코인 평균 24h ${avg>=0?'+':''}${avg.toFixed(2)}% · 평균 거래량 ${vr?vr.toFixed(2):'-'}배<br>${avg>2&&vr>1.5?'가격과 거래량이 일정 전부터 강해 선행 반영 가능성이 있습니다.':'아직 뚜렷한 선행 반응은 확인되지 않았습니다.'}</div><div class="meta"><a target="_blank" href="${esc(e.url)}">공식 일정·원문 확인</a></div></div>`}).join('');
    recommendations.innerHTML=themes+events||'<div class="rec">감지된 핵심 테마와 예정 일정이 없습니다.</div>';return;
  }
  recommendations.innerHTML=Object.entries(d.market).map(([s,v])=>{
    if(!v.forecast24)return `<div class="rec"><h2>${s}</h2>예측 데이터 계산 중… 약 1분 후 자동 표시됩니다.</div>`;
    let c=v.recommendation.includes('상승')?'good':v.recommendation.includes('하락')?'bad':'neutral';
    return `<div class="rec"><div class="head"><h2 style="margin:0">${s}</h2><b class="${c}">${esc(v.recommendation)}</b><span>종합점수 ${v.total_score}/100</span></div><p>현재가 <b>${money(v.price,v.price)}</b> · 24h <span class="${v.change>=0?'good':'bad'}">${v.change>=0?'+':''}${v.change.toFixed(2)}%</span></p><p>24h 거래대금 $${(v.quoteVolume/1000000000).toFixed(2)}B · 최근 거래량 ${v.volume_ratio.toFixed(2)}배 · 변동성 ${v.daily_volatility.toFixed(2)}%</p><div class="forecast"><div><b>24시간 예상</b><br>중심 ${money(v.forecast24.center,v.price)} (${v.forecast24.change>=0?'+':''}${v.forecast24.change.toFixed(2)}%)<br><small>범위 ${money(v.forecast24.low,v.price)} ~ ${money(v.forecast24.high,v.price)}</small></div><div><b>1주 예상</b><br>중심 ${money(v.forecast7d.center,v.price)} (${v.forecast7d.change>=0?'+':''}${v.forecast7d.change.toFixed(2)}%)<br><small>범위 ${money(v.forecast7d.low,v.price)} ~ ${money(v.forecast7d.high,v.price)}</small></div></div><div class="reaction">100점 평가: ${Object.entries(v.score_breakdown).map(([k,n])=>k+' '+n).join(' · ')}<br>근거: ${v.reasons.map(esc).join(' · ')}</div><div class="meta">1시간봉 500개·거래량·변동성·최근 뉴스 종합. 확률적 추정이며 보장값이 아닙니다.</div></div>`
  }).join('');
}
async function load(){let d=await fetch('/api/issues?limit=200').then(r=>r.json());renderRecommendations(d);let x=d.issues;if(filter==='S,A')x=x.filter(i=>['S','A'].includes(i.grade));else if(filter==='exchange')x=x.filter(i=>i.source_type==='exchange');else if(['호재','악재'].includes(filter))x=x.filter(i=>i.direction===filter);else if(filter!=='ALL')x=x.filter(i=>i.assets.split(',').includes(filter)||i.category===filter);issues.innerHTML=x.map(i=>`<article class="card"><div class="head"><span class="grade ${i.grade}">${i.grade}급</span><b class="${i.direction==='호재'?'good':i.direction==='악재'?'bad':'neutral'}">${i.direction}</b><span>${esc(i.assets)}</span><span>${esc(i.category)}</span><span>정보검증 ${i.confidence}/100</span></div><div class="title">${esc(i.title)}</div><div class="summary">${esc(i.summary)}</div><div class="reaction">📊 ${esc(i.reaction)}</div><div class="invest"><b>투자자 체크 · ${esc(i.horizon)}</b><br>${esc(i.investor_note)}</div><div class="meta">${esc(i.source)} · 게시 ${i.published?new Date(i.published).toLocaleString():'시각 미제공'} · 감지지연 ${i.delay_sec}초 · <a target="_blank" href="${esc(i.url)}">원문</a>${i.ai?' · AI 요약':''}</div></article>`).join('')||'<div class="card">최근 24시간 내 조건에 맞는 중요 이슈가 없습니다.</div>';today.textContent=d.stats.today;urgent.textContent=d.stats.urgent;good.textContent=d.stats.good;bad.textContent=d.stats.bad;let vals=Object.values(d.market);let avg=vals.length?vals.reduce((a,v)=>a+v.change,0)/vals.length:0;regime.textContent=avg>2?'강한 상승':avg>.3?'상승':avg<-2?'강한 하락':avg<-.3?'하락':'중립';regime.className='num '+(avg>0?'good':avg<0?'bad':'neutral');market.innerHTML=Object.entries(d.market).map(([s,v])=>`<div class="ticker"><b>${s}</b><br>$${v.price.toLocaleString(undefined,{maximumFractionDigits:v.price<10?4:2})}<br><span class="${v.change>=0?'good':'bad'}">${v.change>=0?'+':''}${v.change.toFixed(2)}%</span></div>`).join('');sources.innerHTML=Object.entries(d.status).map(([n,s])=>`<div class="source-row"><span class="${s.ok?'ok':'err'}">${s.ok?'● 정상':'● 오류'}</span><br>${esc(n)}<br><small>${s.ok?'항목 '+s.items+(s.new?' · 신규 '+s.new:''):esc(s.error)}</small></div>`).join('')}
setInterval(()=>{clock.textContent=new Date().toLocaleTimeString();load()},5000);load();</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send(self,code,body,ctype="application/json; charset=utf-8"):
        b=body.encode(); self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(b))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/api/issues"):
            q=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); limit=min(500,int(q.get("limit",[200])[0]))
            self.send(200,json.dumps(build_snapshot(limit),ensure_ascii=False)); return
        self.send(200,PAGE,"text/html; charset=utf-8")

def build_snapshot(limit=200):
    day=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats={"today":db("SELECT count(*) n FROM issues WHERE detected LIKE ?",(day+"%",),True)[0]["n"],"urgent":db("SELECT count(*) n FROM issues WHERE grade IN ('S','A') AND detected LIKE ?",(day+"%",),True)[0]["n"],"good":db("SELECT count(*) n FROM issues WHERE direction='호재' AND detected LIKE ?",(day+"%",),True)[0]["n"],"bad":db("SELECT count(*) n FROM issues WHERE direction='악재' AND detected LIKE ?",(day+"%",),True)[0]["n"]}
    with LOCK:
        status=json.loads(json.dumps(STATUS,ensure_ascii=False)); market=json.loads(json.dumps(MARKET,ensure_ascii=False))
    return {"issues":db("SELECT * FROM issues ORDER BY detected DESC LIMIT ?",(limit,),True),"stats":stats,"status":status,"market":market,"hot_events":db("SELECT * FROM hot_events ORDER BY event_time ASC",fetch=True),"hot_themes":hot_themes(),"started":STARTED,"heartbeat":datetime.now(timezone.utc).isoformat(),"collector":"local-windows"}

def cloud_sync_loop():
    url=os.getenv("SUPABASE_URL","").rstrip("/"); key=os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
    interval=max(5,int(os.getenv("CLOUD_SYNC_SECONDS","10")))
    while True:
        try:
            snap=build_snapshot(200)
            required_markets={"BTC","ETH","XRP","SOL","BNB"}
            ready_markets={symbol for symbol,value in snap.get("market",{}).items() if value.get("price")}
            if not required_markets.issubset(ready_markets):
                STATUS["클라우드 동기화"]={"ok":False,"checked":snap["heartbeat"],"items":0,"new":0,"error":"시세 초기화 중 · 기존 정상 스냅샷 유지"}
                time.sleep(interval)
                continue
            raw=json.dumps(snap,ensure_ascii=False)
            tmp=SNAPSHOT_FILE.with_suffix(".tmp"); tmp.write_text(raw,encoding="utf-8"); tmp.replace(SNAPSHOT_FILE)
            if url and key:
                body=json.dumps([{"id":"live","payload":snap,"updated_at":snap["heartbeat"]}],ensure_ascii=False).encode("utf-8")
                req=urllib.request.Request(url+"/rest/v1/coin_snapshots?on_conflict=id",data=body,method="POST",headers={"apikey":key,"Authorization":"Bearer "+key,"Content-Type":"application/json","Prefer":"resolution=merge-duplicates,return=minimal","User-Agent":"CoinIssueAI/7.0"})
                with urllib.request.urlopen(req,timeout=20) as r: r.read()
                STATUS["클라우드 동기화"]={"ok":True,"checked":snap["heartbeat"],"items":len(snap["issues"]),"new":0,"error":""}
            else:
                STATUS["클라우드 동기화"]={"ok":False,"checked":snap["heartbeat"],"items":0,"new":0,"error":"SUPABASE 설정 전 · 로컬 모드"}
        except Exception as e:
            STATUS["클라우드 동기화"]={"ok":False,"checked":datetime.now(timezone.utc).isoformat(),"items":0,"new":0,"error":str(e)[:180]}
        time.sleep(interval)

def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):
            stream.reconfigure(encoding="utf-8",errors="replace")
    port=int(CFG.get("dashboard_port",8765)); host=os.getenv("DASHBOARD_HOST","127.0.0.1")
    try:
        server=ThreadingHTTPServer((host,port),Handler)
    except OSError as e:
        if getattr(e,"winerror",None)==10048 or getattr(e,"errno",None) in (48,98):
            print("Coin Issue AI collector is already running.",flush=True)
            return 10
        raise
    init_db(); threading.Thread(target=market_loop,daemon=True).start(); threading.Thread(target=monitor,daemon=True).start(); threading.Thread(target=cloud_sync_loop,daemon=True).start()
    print(f"\nCoin Issue AI collector running: http://{host}:{port}\nCloud sync: {'configured' if os.getenv('SUPABASE_URL') else 'not configured'}\nStop: Ctrl+C\n",flush=True)
    server.serve_forever()
    return 0
if __name__=="__main__": raise SystemExit(main())
