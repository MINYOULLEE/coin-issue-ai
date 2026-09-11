# 실패 연구 기록

| 연구군 | 주요 실패 이유 | 기존 상세 자료 |
|---|---|---|
| A Stage84 신호 집중 감속 | 기본 5년은 현재 A를 근소하게 상회하나 비용 2배 +813,042.59%로 기준 미달, 검증구간 개선 없음 | [Stage84 신호 집중](A-STAGE84-SIGNAL-CONCENTRATION-FAIL.md) |
| A Stage82 종목별 변동성 감속 | 5년 +1,151,666.82%로 현재 A보다 낮고 미사용 검증 기본 7/20 수익 | [Stage82 종목별 감속](A-STAGE82-SYMBOL-VOLATILITY-FAIL.md) |
| A Stage81 변동성 감속 | MDD는 -40.35%로 개선됐지만 5년 복리 +634,882.62%로 100만% 미달, 미사용 검증구간도 약함 | [Stage81 변동성 감속](A-STAGE81-VOLATILITY-OVERLAY-FAIL.md) |
| A Stage79 확장 합성검증 | 80경로 중 기본 43개·극단비용 27개만 수익, 최악 불리 MDD -79.51% | [Stage80 확장 검증](A-STAGE80-EXTENDED-SYNTHETIC-FAIL.md) |
| A Stage76 균형형 | 방어 배율 의미 교정 후 실효 1.12배, 불리 경로 필요담보/Equity 103.54%로 실행 상한 초과 | [Stage76 균형형 철회](../success/A-STAGE76-BALANCED-CANDIDATE.md) |
| A Stage76 고수익형 | 가상시장 불리 경로 MDD -81.99%, -70% 기준 위반 | [Stage76 고수익형](A-STAGE76-HIGH-MDD-FAIL.md) |
| 결정트리·확신도 조절 | 5년 복리 기준 미달, 독립구간 성과 소멸 | [답안지 대체 방식](../answer_sheet_method_search_2026-08-29.md) |
| 공격형 알트 조합 | 독립검증 대손실·MDD 과다 | [공격형 독립검증](../aggressive_independent_validation_deep_dive_2026-08-29.md) |
| 1시간봉 단일 반전 | 대다수 코인 독립구간 손실 | 재실행: `search_intraday_patterns.py` |
| 3분할 교차검증 미통과 | BTC·TRX·SOL·다수 알트가 구간 간 전이 실패 | 재실행: `search_three_way_patterns.py` |
| ETH+LINK 반전 조합 v1 | 세 구간 플러스이나 5년 복리 기준 미달·MDD -50% 초과 | [ETH-LINK 조합](ETH-LINK-1H-VSR-COMBO-v1.md) |
| ETH 단독 반전 v1 | 세 구간 플러스이나 5년 복리 +75%로 기준 미달 | [ETH 단독](ETH-1H-VSR-05X-24H-v1.md) |
| ETC+LINK 조합 2차 검증 | 다음 봉·현실 비용 적용 시 100만% 및 MDD 기준 실패 | [2차 검증](ETC-LINK-1H-VSR-COMBO-stage2.md) |
| ETC+LINK 적응형 위험관리 3차 | 변동성 목표·낙폭 감속 적용 후 위험 기준은 개선됐으나 100만% 미달 | [3차 검증](ETC-LINK-1H-VSR-COMBO-stage3.md) |

실패한 규칙을 다시 연구하려면 진입 조건·시간봉·비용 또는 검증 구조가 실질적으로
달라져야 한다. 단순 파라미터 재실행은 중복 연구로 처리한다.
