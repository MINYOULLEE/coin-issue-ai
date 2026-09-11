"""Causal past-opportunity excursion learning for frozen B Stage26. Offline only."""
import inspect
import json
import hashlib
from datetime import datetime, timezone
import numpy as np
import research_adaptive_exits_stage27 as prev

H=prev.H
OUT=prev.a.RESULT_DIR/'conditional_exits_stage28'
RULES=[('baseline',None,None,False,False),
       ('stop_q90',.90,None,False,False),('stop_q95',.95,None,False,False),
       ('stop_q99',.99,None,False,False),('conditional_q95',.95,None,True,False),
       ('conditional_q99',.99,None,True,False),
       ('pair_q95_q80',.95,.80,False,False),('pair_q99_q95',.99,.95,False,False),
       ('learned_trail_q95',.95,.80,False,True),
       ('conditional_trail_q99',.99,.95,True,True),
       ('target_only_q50',None,.50,False,False),
       ('target_only_q80',None,.80,False,False),
       ('target_only_q95',None,.95,False,False)]

def regime(f,side):
    return (int(side*f['move']>0),int(f['eff']>.35))

def samples(series,entries,fs):
    out=[]
    for t in sorted(entries):
        for p in entries[t]:
            s=p['symbol'];side=p['side'];bars=[series[s].get(k) for k in range(t,p['exit_bar']+H,H)]
            # Never infer excursion labels across missing source candles. Keep
            # frozen entry inputs untouched; this opportunity stays unmodified.
            if any(x is None for x in bars) or t not in fs[s]:continue
            raw=bars[0]['o'];entry=raw*(1+side*.0002);end=bars[-1]['c']*(1-side*.0002)
            atr=fs[s][t]['atr']
            net=side*(end-entry)-.0005*(entry+end)-sum(x['o']*.0000125 for x in bars)
            adverse=max(0.,max(-side*(x['l' if side>0 else 'h']-raw) for x in bars))/atr
            favorable=max(0.,max(side*(x['h' if side>0 else 'l']-raw) for x in bars))/atr
            out.append(dict(symbol=s,side=side,t=t,known_at=p['exit_bar']+H,exit_bar=p['exit_bar'],
                            mae=adverse,mfe=favorable,win=net>0,regime=regime(fs[s][t],side)))
    return out

def select_history(all_samples,current,conditional):
    # Outcomes are only usable after their ORIGINAL scheduled close, even if a
    # modified strategy would exit early. This also includes unfilled opportunities.
    hist=[x for x in all_samples if x['symbol']==current['symbol'] and x['side']==current['side']
          and x['known_at']<=current['t'] and x['t']<current['t']][-120:]
    wins=[x for x in hist if x['win']]
    if len(wins)<20:return []
    if conditional:
        matched=[x for x in wins if x['regime']==current['regime']]
        if len(matched)>=12:return matched
    return wins

def learned_exits(series,entries,fs,rule):
    name,q,tp,conditional,trail=rule
    data=samples(series,entries,fs);exits={};decisions=[]
    for cur in data:
        s=cur['symbol'];t=cur['t'];side=cur['side'];hist=select_history(data,cur,conditional) if q or tp else []
        decision=dict(symbol=s,entry_ts=t,training_winners=len(hist),active=bool(hist),
                      latest_training_close=max((x['known_at'] for x in hist),default=None))
        if not hist:
            decisions.append(decision);continue
        assert decision['latest_training_close']<=t
        atr=fs[s][t]['atr'];raw=series[s][t]['o']
        distance=max(.5,float(np.quantile([x['mae'] for x in hist],q)))*atr if q else None
        stop=raw-side*distance if distance is not None else None
        trigger=float(np.quantile([x['mfe'] for x in hist],tp))*atr if tp else None
        target=raw+side*trigger if tp and not trail else None
        decision.update(stop=stop,target=target,trail_trigger_distance=trigger if trail else None)
        # The trail only arms on a COMPLETED candle, and changes the next bar's stop.
        for k in range(t,cur['exit_bar']+H,H):
            bar=series[s][k];px,reason,both=prev.hit(bar,stop,target,side)
            if px is not None:
                exits[(s,t,k)]=float(px)
                decision.update(exit_bar=k,reason=reason,ambiguous=both);break
            if trail and side*(bar['c']-raw)>=trigger:
                candidate=bar['c']-side*distance
                stop=max(stop,candidate) if side>0 else min(stop,candidate)
        decisions.append(decision)
    return exits,decisions

def runner(exits):
    src=inspect.getsource(prev.b.replay)
    patches=[('target*(1+x','target*x.get("weight_scale",1.)*(1+x'),
             ('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)'),
             ("if proxy or t >= p['exit_bar']:","adaptive = exits.get((s,p['entry_ts'],t))\n            if adaptive is not None and p['qty']*p['side']*(adaptive-p['entry'])-p['entry_fee']-p['funding'] > -.9*p['margin']: proxy=False\n            if proxy or adaptive is not None or t >= p['exit_bar']:"),
             ("close = bar['c']*(1-p['side']*slip)","close = (adaptive if adaptive is not None else bar['c'])*(1-p['side']*slip)")]
    for old,new in patches:
        assert src.count(old)==1,old
        src=src.replace(old,new)
    env={**prev.b.__dict__,'exits':exits};exec(src,env)
    return env['replay']

def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')

def main():
    OUT.mkdir(exist_ok=True)
    series,entries,times,std=prev.b_setup();fs={s:prev.features(list(v.values())) for s,v in series.items()}
    cuts=[times[0]+int((times[-1]+H-times[0])*k/3) for k in range(4)]
    items=[]
    for rule in RULES:
        exits,decisions=learned_exits(series,entries,fs,rule);fn=runner(exits)
        run=lambda **kw:fn(series,entries,times,1.15,**kw)
        full=run();stress=run(cost_mult=2)
        segments=[prev.compact(run(start=cuts[i],end=cuts[i+1])) for i in range(3)]
        if rule[0]=='baseline':assert abs(full['end_usd']-std['reference']['end_usd'])<1e-6
        item=dict(rule=rule[0],full=prev.compact(full),double_cost=prev.compact(stress),segments=segments,
                  active_opportunities=sum(d['active'] for d in decisions),total_opportunities=len(decisions),
                  incomplete_opportunities=sum(len(v) for v in entries.values())-len(decisions),
                  changed_opportunities=len(exits),ambiguous_opportunities=sum(d.get('ambiguous',False) for d in decisions))
        items.append(item);save(rule[0]+'.json',dict(summary=item,ledger=full['ledger'],decisions=decisions))
        print(rule[0],json.dumps(item['full']),flush=True)
    base=items[0]
    for x in items:
        x['screen_pass']=x['rule']!='baseline' and x['full']['return_pct']>base['full']['return_pct'] and x['double_cost']['return_pct']>base['double_cost']['return_pct'] and x['full']['hourly_mark_mdd_pct']>=-70 and x['full']['liquidation_proxy_count']==0 and x['double_cost']['liquidation_proxy_count']==0 and all(z['return_pct']>0 for z in x['segments'])
    nominations=[dict(discovery_third=i+1,rule=(w:=max(items,key=lambda x:x['segments'][i]['return_pct']))['rule'],cross_returns=[s['return_pct'] for s in w['segments']]) for i in range(3)]
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),plan='B',runtime_id=std['strategy_id'],
                rules=RULES,cuts=cuts,results=items,nominations=nominations,independent_validation=False,live_changes=False,
                data_sha256={s:hashlib.sha256((prev.a.DATA_DIR/f'{s}USDT_1h.csv').read_bytes()).hexdigest() for s in series},
                notes=['Same symbol and direction, latest 120 completed original opportunities; at least 20 net winners, regime subset at least 12',
                       'All opportunities observed including unfilled, only after original horizon completes',
                       'Winner labels use baseline research costs even under double-cost stress',
                       'Chronological thirds retain training history available before each decision, not independent datasets',
                       'Rule selection across thirds uses previously researched data; not an untouched holdout',
                       'Binance spot OHLC, not actual BingX mark/funding/liquidation/execution',
                       'Hourly stop-first, worse gap stop, next-bar trailing; same reserved margin and cooldowns',
                       'A not rerun: fixed-quantity comparator and production reconciliation unresolved'])
    save('RESULTS.json',result)
    lines=['# B Stage28 — 과거 성공 신호의 역행·상승 폭으로 청산 판단', '',
           '연구 전용. A/B 운영 설정 변경 없음. A는 Stage27 재생 차이 해소 전까지 이번 연구에서 제외.', '',
           '2021-08-28~2026-08-29, $100 시작. 이전에 종료된 같은 종목·방향 기회 중 최근 120개만 관찰. 비용 차감 후 성공 사례 20개 이상일 때만 학습형 청산 적용. 부족하면 기존 시간 청산 유지.', '',
           'stop_q95: 성공 거래의 최대 역행폭을 진입 당시 ATR로 나눈 값의 95분위수 × 현재 ATR. 0.5 ATR 최소 거리. q90/q99도 비교. conditional은 가격 방향 일치·이동 효율로 나누되 성공 표본 12개 미만이면 전체 성공 표본 사용.', '',
           'pair는 성공 거래의 최대 유리한 움직임 80/95분위수를 목표로 사용. target_only는 손절 없이 50/80/95분위수 목표만 적용. learned_trail은 그 수준을 종가로 넘은 뒤에만 다음 봉 추적 손절을 조정한다. 신호 방향·선택 간격·원래 보유기한·담보 배분은 변경하지 않음.', '',
           '학습에 쓰는 성공 여부는 주문 체결 여부와 무관한 가상 기회 결과이며, 해당 기회의 원래 종료 시각이 지난 후에만 알 수 있게 했다. 가격·변동성·관측 사례가 바뀌면 선도 달라지지만 분위수·표본 조건은 고정 연구 파라미터다.', '',
           '|방식|5년 복리 수익률|$100 최종금액|거래 수|승률|평가 최대낙폭|청산 최대낙폭|비용 2배 수익률|학습 적용 기회|',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in items:
        f=x['full'];lines.append(f"|{x['rule']}|{f['return_pct']:+,.2f}%|${f['end_usd']:,.2f}|{f['trades']}|{f['win_rate_pct']:.2f}%|{f['hourly_mark_mdd_pct']:.2f}%|{f['closed_trade_mdd_pct']:.2f}%|{x['double_cost']['return_pct']:+,.2f}%|{x['active_opportunities']}/{x['total_opportunities']}|")
    lines+=['', f"원시 기회 중 봉 누락으로 학습에서 제외한 기회: {items[0]['incomplete_opportunities']}개. 해당 기회의 원래 진입/청산 입력을 삭제하거나 바꾸지 않았다.", '', '## 3분할 교차 비교', '']
    for n in nominations:lines.append(f"- 구간 {n['discovery_third']} 선택 {n['rule']}: "+', '.join(f'{v:+,.2f}%' for v in n['cross_returns']))
    lines+=['', '## 한계', '', '수수료 편도 0.05%, 슬리피지 편도 0.02%, 펀딩 시간당 명목금액 0.00125%. 비용 2배는 세 비용 모두 2배. 실제 펀딩 이력 아님. 평가 최대낙폭은 시간봉 종가 미실현 포함, 청산 최대낙폭은 거래 종료마다 잔액 평가. 틱 단위 손실 최저점은 미검증.', '',
            '원래 기회 선택과 이번 규칙 선택 모두 이미 연구했던 자료에 기반한다. 각 의사결정의 학습 입력은 과거에 한정했지만 독립 검증은 아니다. 같은 봉 양쪽 도달은 손절 우선. 실거래 적용 또는 주문 권한을 생성하지 않음.', '',
            '선별 통과: '+(', '.join(x['rule'] for x in items if x['screen_pass']) or '없음')]
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')

if __name__=='__main__':main()
