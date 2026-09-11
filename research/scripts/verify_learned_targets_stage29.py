"""Read-only public candle downloads and offline B target fill sensitivity.
Never accesses credentials, exchange accounts, or production services.
"""
import json, urllib.request, urllib.parse, hashlib
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
import research_conditional_exits_stage28 as r

H=r.H; M=60000
OUT=r.prev.a.RESULT_DIR/'learned_targets_stage29'
CACHE=OUT/'minute_windows'

def fetch_window(p):
    s=p['symbol'];t=p['entry_ts'];end=p['exit_bar']+H
    path=CACHE/f'{s}_{t}.json'
    if path.exists():data=json.loads(path.read_text(encoding='utf8'))
    else:
        query=urllib.parse.urlencode(dict(symbol=s+'USDT',interval='1m',startTime=t,endTime=end-1,limit=1000))
        request=urllib.request.Request('https://api.binance.com/api/v3/klines?'+query,headers={'User-Agent':'coin-issue-research/1.0'})
        with urllib.request.urlopen(request,timeout=20) as response:data=json.load(response)
        if not isinstance(data,list):raise ValueError(str(data)[:200])
        path.write_text(json.dumps(data),encoding='utf8')
    rows={int(x[0]):dict(o=float(x[1]),h=float(x[2]),l=float(x[3]),c=float(x[4])) for x in data}
    assert list(sorted(rows))==list(range(t,end,M)),f'incomplete minute window {s} {t}'
    return (s,t),rows

def validate_hour(rows,t,hour):
    z=[rows[t+i*M] for i in range(60)]
    aggregated=dict(o=z[0]['o'],h=max(x['h'] for x in z),l=min(x['l'] for x in z),c=z[-1]['c'])
    return all(abs(aggregated[f]-hour[f])<=max(1e-8,abs(hour[f])*1e-8) for f in aggregated)

def execution(rows,p,target,mode):
    """Return (minute, raw fill). Hour engine releases at end of this minute's hour."""
    t=p['entry_ts'];end=p['exit_bar']+H;side=p['side']
    arm=5 if mode=='arm_5m' else 1 if mode=='arm_1m' else 0
    for stamp in range(t+arm*M,end,M):
        bar=rows[stamp]
        if not (bar['h']>=target if side>0 else bar['l']<=target):continue
        if mode in ('delay_1m','delay_5m'):
            close_at=stamp+(1 if mode=='delay_1m' else 5)*M
            if close_at>=end:return None # baseline scheduled close has priority
            return close_at,rows[close_at]['o']
        if mode=='minute_close':return stamp,bar['c']
        if mode=='overshoot_5bp':
            required=target*(1+side*.0005)
            if not (bar['h']>=required if side>0 else bar['l']<=required):continue
        if mode=='haircut_10bp':return stamp,target*(1-side*.001)
        return stamp,target
    return None

def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')

def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    prior=json.loads((r.OUT/'target_only_q80.json').read_text(encoding='utf8'))
    series,entries,times,std=r.prev.b_setup()
    # Verify the candidate is frozen, not a new fit chosen after seeing minutes.
    fs={s:r.prev.features(list(v.values())) for s,v in series.items()}
    hourly,decisions=r.learned_exits(series,entries,fs,('target_only_q80',None,.8,False,False))
    assert decisions==prior['decisions']
    proposals={(p['symbol'],t):p for t,ps in entries.items() for p in ps}
    selected=[d for d in decisions if 'exit_bar' in d]
    assert len(selected)==55
    minutes={};errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(fetch_window,proposals[(d['symbol'],d['entry_ts'])]):d for d in selected}
        for future in as_completed(jobs):
            d=jobs[future]
            try:key,rows=future.result();minutes[key]=rows
            except Exception as e:errors.append(dict(symbol=d['symbol'],entry_ts=d['entry_ts'],error=str(e)))
    save('coverage.json',dict(requested=len(selected),downloaded=len(minutes),errors=errors))
    if errors:
        print(json.dumps(dict(status='minute_data_incomplete',downloaded=len(minutes),errors=errors[:3])),flush=True)
        return
    hours=0
    for key,rows in minutes.items():
        p=proposals[key]
        for stamp in range(p['entry_ts'],p['exit_bar']+H,H):
            assert validate_hour(rows,stamp,series[key[0]][stamp]),f'OHLC mismatch {key} {stamp}'
            hours+=1
    modes=['baseline','hourly_q80','minute_touch','arm_1m','arm_5m','overshoot_5bp','minute_close','delay_1m','delay_5m','haircut_10bp']
    results=[]
    cuts=[times[0]+int((times[-1]+H-times[0])*i/3) for i in range(4)]
    for mode in modes:
        exits={};fills=[]
        if mode=='hourly_q80':exits=hourly
        elif mode!='baseline':
            for d in selected:
                key=(d['symbol'],d['entry_ts']);p=proposals[key]
                fill=execution(minutes[key],p,d['target'],mode)
                if fill:
                    stamp,price=fill;exits[(*key,stamp//H*H)]=price
                    fills.append(dict(symbol=key[0],entry_ts=key[1],fill_minute=stamp,raw_price=price,target=d['target']))
        fn=r.runner(exits)
        full=fn(series,entries,times,1.15);stress=fn(series,entries,times,1.15,cost_mult=2)
        if mode=='baseline':assert abs(full['end_usd']-std['reference']['end_usd'])<1e-6
        if mode in ('hourly_q80','minute_touch'):assert abs(full['end_usd']-prior['summary']['full']['end_usd'])<1e-6
        item=dict(mode=mode,full=r.prev.compact(full),double_cost=r.prev.compact(stress),
                  segments=[r.prev.compact(fn(series,entries,times,1.15,start=cuts[i],end=cuts[i+1])) for i in range(3)],
                  target_candidate_fills=len(exits))
        results.append(item);save(mode+'.json',dict(summary=item,ledger=full['ledger'],minute_fills=fills))
        print(mode,json.dumps(item['full']),flush=True)
    output=dict(generated_at=datetime.now(timezone.utc).isoformat(),results=results,minute_windows=len(minutes),matched_hours=hours,
                minute_count=sum(len(v) for v in minutes.values()),ohlc_mismatches=0,live_changes=False,independent_validation=False,
                candidate_sha256=hashlib.sha256((r.OUT/'target_only_q80.json').read_bytes()).hexdigest(),
                minute_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(CACHE.glob('*.json'))},
                limitations=['Public Binance SPOT candles, not BingX futures or order-book fills',
                             'Only 55 original target-touch candidate windows checked, not all account candles',
                             'Portfolio equity, funding and margin release still hourly; not minute-resolution MDD',
                             'Minute touch is not proof of limit queue fill; overshoot and delayed market exits are sensitivity assumptions',
                             'Minute delay is from opening time of touch minute, whose exact intraminute touch time is unknown',
                             'Original scheduled close wins over delayed target beyond deadline',
                             'No A rerun, no production changes'])
    save('RESULTS.json',output)
    lines=['# B Stage29 — 학습형 익절 q80 세부 봉 체결 검증', '',
           f"55개 목표 도달 기회 전체: {hours}개 시간봉과 {output['minute_count']}개 1분봉 대조, OHLC 불일치 0개. 기존 q80 판단값 고정 후 검사.", '',
           '|조건|5년 복리 수익률|$100 최종금액|거래 수|승률|평가 최대낙폭|청산 최대낙폭|비용 2배 수익률|',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for x in results:
        f=x['full'];lines.append(f"|{x['mode']}|{f['return_pct']:+,.2f}%|${f['end_usd']:,.2f}|{f['trades']}|{f['win_rate_pct']:.2f}%|{f['hourly_mark_mdd_pct']:.2f}%|{f['closed_trade_mdd_pct']:.2f}%|{x['double_cost']['return_pct']:+,.2f}%|")
    lines+=['', '## 해석과 한계', '',
            'minute_touch는 목표 도달 가격 체결 가정 유지. arm_1m/5m는 진입 후 해당 분부터만 목표 주문 유효. overshoot_5bp는 목표를 추가 0.05% 통과해야 목표 가격 체결 인정. minute_close는 최초 도달 분 종가, delay_1m/5m는 최초 도달 분 시작 기준 1/5분 후 시가에 청산. haircut_10bp는 목표 체결가에 추가 불리한 0.10% 적용. 모든 경우 기존 비용을 별도로 차감.', '',
            '비용: 수수료 편도 0.05%, 슬리피지 편도 0.02%, 펀딩 시간당 명목금액 0.00125%. 비용 2배는 세 항목 모두 2배. 기간은 기존 2021-08-28~2026-08-29, $100 연구 기준.', '',
            '55개는 실제 체결 거래 수가 아닌 목표 도달 기회 수. 기타 기회는 기존 시간봉 계산 유지. 청산 담보 반환·평가·펀딩은 시간 단위 유지하여 전체 1분봉 계좌 재생으로 부르면 안 된다. 최대낙폭은 시간봉 종가 평가/거래 종료 잔액 기준이지 분봉·틱 기준이 아니다.', '',
            '분봉의 목표 도달은 호가 잔량·주문 대기열·실제 체결 보장이 아니다. Binance 현물 자료이며 BingX 선물 펀딩/마크가격/거래 체결 미검증. 이미 선택된 과거 후보이므로 독립 검증 아님. A/B 운영에는 변경 없음.']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')

if __name__=='__main__':main()
