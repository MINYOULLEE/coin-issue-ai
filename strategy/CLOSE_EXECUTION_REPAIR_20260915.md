# 청산 실행 오류 보수 — 2026-09-15

사용자 승인: 현재 코드에서 재현한 청산 결함 3건에 대해 “오류 고치자”.
상태: 로컬 수정 및 회귀 검사 완료. DB 마이그레이션과 운영 배포는 미실행.

- B Stage112: 시간 만기가 되면 수익보호 캔들 조회를 생략하고 원래 시간 청산을 수행한다.
- B: 청산 주문이 종료됐고 자동 잔량이 0이면 수동 잔량을 보존하며 거래/신호/예약을 종료한다. 미확정 주문은 완료 처리하지 않는다.
- 연동 계정: 청산 시도 ID·수량·수동 잔량을 DB에 원자 저장한 뒤 주문한다. 주문 접수/0체결은 완료가 아니다. 다음 주기는 기존 주문 조회로 복구하며 미확정/NOT_FOUND는 재주문하지 않는다. 종료된 부분체결은 확인된 자동 잔량만 재시도한다.
- 연동 계정의 리사이즈 손절 실패 안전청산도 동일 확인 경로를 사용한다.
- 손익은 추정 가격/수수료로 만들지 않는다. 고유한 종목·방향·진입시각·수량의 거래소 순손익 기록으로 정산한다. 수동 혼합 또는 매칭 실패는 미정산 상태로 남는다.
- 주문 전 프로세스 중단 등으로 저장된 시도는 있지만 거래소 주문이 없는 경우 자동 재주문하지 않으며 별도 조회/운영 확인이 필요하다. 기존 잘못 종료된 과거 장부는 변경하지 않았다.

전략 정본 A Stage184/B Stage112, 수량 정책, 신호, LIVE 스위치, 일정, 자격증명은 변경하지 않았다.

## 검증

`node --experimental-vm-modules --test --test-timeout=15000 research/scripts/test_managed_close.mjs research/scripts/test_managed_accounts.cjs research/scripts/test_execution_reporting.cjs research/scripts/test_a_execution_safety.cjs research/scripts/test_a_recovery_policy.mjs research/scripts/test_plan_b_live_cycle.mjs research/scripts/test_plan_b_sizing.mjs research/scripts/test_plan_b_exchange.mjs research/scripts/test_plan_b_profit_lock.mjs`

80개 통과. 신규 장애 검사는 실제 운영 청산 함수/공유 모듈을 사용한다. Stage16 담보 2개 통과. 실주문 시험 없음.

## 운영 반영 순서

1. `20260915120000_managed_close_confirmation.sql`: 연동 거래 장부에 nullable JSONB `close_context` 추가. 기존 데이터/권한 변경 없음.
2. `plan-b-executor`, `managed-account-executor`를 공유 모듈과 함께 배포.
3. 원격 소스 일치, A/B 및 연동 계정 스위치 유지, 다음 자동 실행의 청산/예약/오류 상태 확인.

배포 완료나 자연 체결 검증으로 간주하지 않는다.
