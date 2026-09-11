"""Render the completed offline screen; never reads/writes live state."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
folder=root/'research/results/adaptive_exits_stage27'
r=json.loads((folder/'RESULTS.json').read_text(encoding='utf8'))
assert len(r['rules'])==12, 'Incomplete run: expected twelve variants per plan'
lines=['# A/B 판단별 익절·손절 연구 Stage27', '',
       '오프라인 1차 선별. 운영 코드·주문·스위치·배포 변경 없음.', '',
       '기간: 2021-08-28~2026-08-29, 시작 $100. 세 구간 각각에서 후보를 고르고 다른 구간에 교차 적용. 모든 구간을 탐색했으므로 독립 검증 아님.', '',
       '## 판단 규칙', '',
       '- atr_stop / atr_pair: 직전 완료 24시간 평균 진폭(ATR)에 따라 손절 거리 설정. pair는 3 ATR 목표.',
       '- structure_stop / structure_pair: 직전 6시간 고저점에 변동성 여유를 추가. pair는 손절 거리의 2배 목표.',
       '- mean_target: 반전 신호의 목표를 직전 24시간 평균 가격으로 설정. 목표가 현재 가격의 유리한 방향이 아니거나 너무 가까우면 2 ATR 대체.',
       '- trail: 유리한 방향으로 진행하면 완료 봉 기준 2 ATR 추적 손절. 다음 봉부터 적용.',
       '- judgement: squeeze 유형 또는 강한 노출·방향 일치·가격 이동 효율 조건이면 추적, 아니면 평균 회귀 목표.',
       '- horizon_stop / pair / trail: 손절 거리 = 1.5 × ATR × √예상 보유시간. pair는 거리의 2배 목표.',
       '- judgement_wide: 위 판단 분기에 따라 보유시간 보정 추적 또는 손절만 적용.',
       '- A의 강도는 모델 노출의 대용 지표이며 검증된 승률 확률이 아님. B는 기존 신호 유형을 사용.',
       '- 고정 가격 비율은 아니지만 ATR 배수와 판단 임계값은 고정 연구 파라미터. 완전한 최적화/확률 예측 모델이 아님.', '',
       '## 계산 조건과 한계', '',
       '- 비용: 체결 방향별 수수료 0.05%, 슬리피지 0.02%, 매시간 명목금액 대비 펀딩 0.00125% 차감. 실제 역사적 펀딩 아님. 비용 2배는 이 세 항목을 모두 2배.',
       '- 1시간 OHLC에서 손절·익절이 함께 닿으면 손절 우선. 갭 손절은 불리한 시가. 시간 내 실제 체결 순서는 미확인.',
       '- B 기회 간격·원래 기회에 따른 보조 신호 차단·예약 담보·동시 비례 배분·진입 수량 고정 유지. 조기 청산으로 담보가 빨리 풀려 거래 수가 달라질 수 있음.',
       '- 청산 proxy는 격리담보 90% 손실의 단순 가정. 거래소 유지증거금·마크가격·계약 최소치·부분 체결을 재현하지 않음.',
       '- A 비교 모델은 진입 수량 고정과 위 비용·청산 proxy를 사용한 별도 연구 모델. 실제 운영 실행기의 완전한 복제 아님.',
       '- A 기존 시간별 고정비중 재생은 +257,597.52%, MDD -35.53%로 재현되지만, 아래 A 비교 모델과 계산 조건이 다르므로 같은 성과라고 혼용 금지.',
       '- 평가 MDD는 시간봉 종가에서 미실현을 포함한 자산 고점 대비 최대 하락. 청산 MDD는 거래 청산 시점 잔액 기준이며, 둘 다 실제 틱 단위 최대낙폭이 아님.', '']
for p in ('A','B'):
    lines += [f'## {p} 결과', '', '|규칙|5년 복리 수익률|$100 최종금액|거래 수|승률|평가 최대낙폭|청산 최대낙폭|청산 proxy 수|비용 2배 수익률|', '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in r['plans'][p]['results']:
        f=x['full']
        lines.append(f"|{x['rule']}|{f['return_pct']:+,.2f}%|${f['end_usd']:,.2f}|{f['trades']:,}|{f['win_rate_pct']:.2f}%|{f['hourly_mark_mdd_pct']:.2f}%|{f['closed_trade_mdd_pct']:.2f}%|{f['liquidation_proxy_count']}|{x['double_cost']['return_pct']:+,.2f}%|")
    lines += ['', '### 3분할 후보 교차 적용', '']
    for n in r['plans'][p]['nominations']:
        lines.append(f"- 구간 {n['discovery_third']} 선택: {n['rule']}; 각 구간 수익률: "+', '.join(f'{v:+,.2f}%' for v in n['cross_applied_returns']))
    passed=[x['rule'] for x in r['plans'][p]['results'] if x['research_pass']]
    lines += ['', '선별 통과: '+(', '.join(passed) if passed else '없음'), '']
lines += ['## 판정', '', '기존 대비 전기간 및 비용 스트레스 수익률 개선, 각 구간 양수, 평가 MDD 70% 이내, 전기간/스트레스 청산 proxy 없음이 선별 조건이다. 통과하더라도 배포 승인이 아니다.', '', '원시 거래 내역은 각 A_규칙.json/B_규칙.json, 구간별·비용별 요약과 원본 데이터 해시는 RESULTS.json에 보관한다. 이 연구로 운영 전략을 수정하지 않았다.']
(folder/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print(folder/'REPORT.md')
