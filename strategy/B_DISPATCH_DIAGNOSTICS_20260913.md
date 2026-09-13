# B 신호 실행 누락 진단 보수 — 2026-09-13

사용자 요청으로 B Stage112의 전략 조건과 실거래 ON 상태를 변경하지 않고, 유효 신호가 주문 예약 전 단계에서 제외되는 사유를 영속 기록하도록 보수했다.

- `plan_b_signals.dispatch_block_reason`과 `dispatch_checked_at`을 추가했다.
- 동일 종목·방향의 수동 수량이 자동 장부 수량보다 많으면 `manual_same_side_overlap`을 기록하고 주문하지 않는다.
- 진입 직전 가격이 신호가보다 불리하게 0.35%를 초과하면 `adverse_move_over_0_35pct`, 가격이 유효하지 않으면 `invalid_mark_price`를 기록한다.
- 정상 주문 후보가 되면 이전 차단 사유를 지운다. 실행 주기 결과에도 `skipped` 배열로 사유를 남긴다.
- 2026-09-13 DOGE 신호는 데이터 장애 후 생성됐지만 주문 예약 없이 5분 기한이 종료됐다. 과거 건은 `expired_before_dispatch_diagnostics`로 정리했다. 원인을 소급 추정하지 않는다.
- 이 변경은 안전 사전검사를 우회하거나 진입 유효시간을 연장하지 않는다. A플랜과 A/B 실거래 스위치는 변경하지 않았다.
