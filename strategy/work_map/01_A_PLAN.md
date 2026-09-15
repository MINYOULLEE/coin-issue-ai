# 현재 A플랜

## 한 줄 정의

`answer_mdd30` / `mdd30_5x_c_controller_stage184_v1`: BTC·ETH·XRP·TRX·SOL 5개 독립 트리의 일일 답안 리밸런싱에 5배 격리 레버리지, 낙폭 노출 축소, 장중 급등 방어, C 급변 방어를 적용한 A 운영본이다.

## 정본과 승인 기록

- 기계 판독 정본: `strategy/mdd30_standard.json`
- 전체 설명: `strategy/PLANS.md`
- 현재 승인·배포 기록: `strategy/A_STAGE184_APPROVED_20260914.md`
- 직전 핵심 단계: `strategy/A_STAGE135_APPROVED_20260911.md`, `strategy/A_STAGE126_APPROVED_20260910.md`, `strategy/A_STAGE75_APPROVED_20260908.md`
- 답안 트리: `supabase/functions/coin-collector/answer_trees.ts`
- 현재 트리 SHA-256: `9A483FD33C540F6601B01901143313B81C89E8C3A9CCD257141F86694F34E31B`

## 현재 핵심 규칙

- 결정: UTC 00:00 시작 일봉 완료 후 UTC 01:00, 태국 08:00 실행.
- 거래소 레버리지: 격리 5배.
- 정상 노출배율: 2.333333, 총 명목노출 상한 3.733333.
- 실제 BingX Equity 고점 대비 낙폭 22.5%부터 배율 0.77, 10.125% 이내 회복 시 정상 복귀.
- 고정 익절 없음. 일일 답안 리밸런싱과 진입가 기준 15% 비상손절 사용.
- SOL 숏 구간 필터와 선택적 리사이즈 규칙 유지.
- 수동수량은 자동수량과 분리하며 자동 로직이 수동수량을 청산·리사이즈하지 않는다.

## 운영 영역

- 자격증명: `BINGX_API_KEY`, `BINGX_SECRET_KEY`
- 주요 상태/신호/장부: `real_trading_state`, `trade_signals`, `real_trades`, `bingx_trade_history`
- 타인 연동 A 계정도 원하는 버전과 적용 버전을 기록하며, 현재 LIVE A 계정은 Stage184를 사용한다.
- 타인 계정 실행 상세: `strategy/MANAGED_BINGX_ACCOUNTS_20260909.md`
- 수동/자동 수량 분리: `strategy/MANUAL_AUTO_QUANTITY_ISOLATION_20260912.md`

## 성과 표기의 의미

현재 보관 연구 기준은 5년 +32,207,210.98%, 7년 +61,015,176.64%, 완료시간봉 불리경로 MDD -45.37%, 비용 3배 +2,147,998.66%다. 이는 과거 Binance 기반 재생·변형 검증이며 미래 BingX 수익이나 독립 실거래 성과가 아니다.

## 변경 금지선

A 변경을 B에 복사하지 않는다. A의 트리, 시간, 레버리지, 노출, 청산, C 조건 중 하나라도 바꾸면 새 A 버전과 사용자 승인이 필요하다. 점검 때문에 LIVE를 자동 OFF하지 않는다.
