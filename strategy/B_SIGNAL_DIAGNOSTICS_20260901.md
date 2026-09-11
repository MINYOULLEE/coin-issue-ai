# B 시간별 신호 진단 — 2026-09-01

사용자 승인: 며칠간 B 실거래가 없을 때 신호기가 멈춘 것인지 조건 미달인지 확인할 수 있도록 B 전용 진단을 만든다.

## 범위

- B `b_core_sparse_stage26`의 8종목만 대상이다.
- 완료된 1시간봉마다 기존 원자적 기회 기록의 `decisions.<symbol>.diagnostic`에 저장한다.
- 최신 실행 결과인 `plan_b_runtime_health(id='signals')`에도 같은 시간의 진단을 넣는다.
- A 계정·A 신호·A 주문에는 적용하지 않는다.

## 저장 내용

- 규칙 종류와 실제 신호 일치 여부
- 탈락 사유 코드
- RSI, 1시간 수익률, 거래량 비율, 변동성 압축 비율, 꼬리 비율, 스윕 기준 고저점 등 해당 규칙의 실측값
- 각 실측값과 비교할 기준값
- 보조 패턴은 롱·숏 방향별 세부 조건 통과 여부

대표 탈락 코드는 `rsi_not_extreme`, `outside_session`, `move_below_threshold`, `compression_not_met`, `volume_not_met`, `reversal_pattern_not_met`, `sweep_reclaim_not_met`이다.

## 불변 조건

- 진단 정보는 신호 선택이나 우선순위에 사용하지 않는다.
- Stage26 조건, 5분 진입 유효시간, 기본/보조 충돌 방지, 기회 쿨다운, 담보 예약, 레버리지, 계정 분리는 변경하지 않는다.
- 실거래 ON/OFF 및 테스트 모드를 변경하지 않는다.
- 과거 시간은 소급 변조하지 않고 배포 후 새로 확정되는 시간부터 기록한다.
