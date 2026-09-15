# 현재 B플랜

## 한 줄 정의

`b_regime_guard_stage112` / `b_regime_guard_stage112_v1`: Stage93의 13종목 신호, Stage66 수익보호 청산, 총노출·계좌낙폭·BTC 약세구간 보호를 결합한 독립 B 운영본이다.

## 정본과 승인 기록

- 기계 판독 정본: `strategy/plan_b_standard.json`
- 배포 공유 정본: `strategy/plan_b_combination_standard.json`
- 실행 기준: `strategy/plan_b_execution_standard.json`
- 현재 승인·운영 기록: `strategy/B_STAGE112_APPROVED_20260910.md`
- 초기 조합 승인 기록: `strategy/B_STAGE26_APPROVED_20260831.md`
- 과거 기준선: `strategy/archive/plan_b_stage16_v1.json` — 현재 운영본으로 사용 금지.

## 현재 핵심 규칙

- 1시간 완료봉 신호, 다음 봉 시가 진입, 5분 미만 TTL, 불리한 이동 0.35% 이내.
- core: AVAX, ICP, BCH, DOGE, UNI.
- supplement: ALGO, ETH, VET, LINK, DOT, LTC, BNB, ADA.
- 보조 1시간 보유와 선택 경계 최소 2시간을 구분한다.
- 기본/보조 그룹은 같은 B 계정에서 상호 배제하며 청산·잔량 0·미체결 없음 확인 후 다음 그룹을 허용한다.
- 실제 가용 담보, 5% 현금 버퍼, 비용 예약, 동시 요청 비례 감액, 진입 수량 고정을 사용한다.
- 신규진입 후 총 명목노출은 실제 Equity의 3.75배 이하.
- 고점 대비 25% 낙폭 시 168시간 신규진입만 중지. 기존 포지션 청산은 계속.
- BTC 완료 72시간 수익률 -6% 이하 또는 필요한 BTC 자료 누락 시 BCH/ICP/LINK/UNI 신규진입만 차단.

## 운영 영역

- 자격증명: `PLAN_B_BINGX_API_KEY`, `PLAN_B_BINGX_SECRET_KEY`
- 상태/신호/장부: `plan_b_trading_state`, `plan_b_signals`, `plan_b_real_trades`
- 주문 접두어: `pb112`
- B 실거래 성과 기준금: 사용자 확인 $650. 연구 시작금 $100과 구분.
- 연구의 채택은 실제 자연 신호·체결·청산의 독립 실거래 검증 완료를 뜻하지 않는다.

## 현재 연구 표기

5년 $100 → $5,151,963.11, +5,151,863.11%, 820회, 시간봉 MDD -46.81%. 7년 $100 → $16,049,336.14, +16,049,236.14%, 888회, 시간봉 MDD -50.37%. 과거 Binance 자료 기반 모의검증이다.

## 변경 금지선

A 자격증명·테이블·상태를 B의 대체 경로로 쓰지 않는다. Stage16, Stage14/15의 5.75 배수·20.7배 노출·철회 수익률을 복원하지 않는다. 사전검사와 예약/선점 절차를 우회하지 않으며 점검 때문에 사용자가 켠 B LIVE를 끄지 않는다.
