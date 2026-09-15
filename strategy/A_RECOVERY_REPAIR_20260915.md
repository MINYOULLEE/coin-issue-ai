# A 일일 진입 및 C 청산 복구 보수

상태: 로컬 구현·테스트 및 운영 함수 배포 완료. 실제 포지션별 복구 발생 여부는 자연 실행에서 계속 확인한다.
사용자 요청: 2026-09-15 A Stage185 점검에서 확인한 복구 결함 수정.

## 수정 범위

- 26시간 경과 기준을 다음 UTC 01:00 판단 경계로 교체. 미래·비정상 시각 거절.
- 최초 신호에도 판단봉 마감시각 저장. 구형 신호는 생성시각, 저장된 retry_pending 판단, 종목·방향·기본 노출·가능한 경우 신호 ID를 대조.
- 실행기는 요청 본문 대신 DB의 최신 A 신호를 읽는다. 이미 종료·무효 처리된 신호는 재진입하지 않는다.
- 미체결 복구 중 동일 신호의 거래 이력이 있으면 새 진입으로 재사용하지 않는다.
- 일일 답안을 청산/수량조정 실패 및 체결 대기 분기에서도 보존한다. 답안이 실제로 없으면 현재 임시 시간봉으로 대체하지 않는다.
- C 청산 대상을 trade_signals.entry_metrics.c_close_intent에 먼저 저장한 뒤 청산 요청. 실패 시 다음 수집 주기에서 시장 조건과 무관하게 이어서 처리.
- C 신규진입 동결도 청산 요청 전에 저장. 스냅샷 heartbeat는 이전 값 유지.
- C 청산 완료는 기존 실행기의 잔량 확인 또는 종료된 실거래 장부 확인 후 처리. 해당 신호에 매칭되는 장부가 아예 없으면 완료로 단정하지 않는다.
- C 평가 자료의 5종목 시간 경계 일치와 유효성을 확인. 누락 자료는 평가 완료시각을 전진시키지 않는다.
- C 대기 청산은 일일 증액/리사이즈 및 급등방어 부분청산과 겹치지 않게 처리.
- sync 정리에서 request_payload가 있는 미확정 주문 예약은 경과시간만으로 삭제하지 않는다.

## 검증

- `node --test research/scripts/test_a_recovery_policy.mjs research/scripts/test_a_execution_safety.cjs research/scripts/test_a_entry_cycle.mjs research/scripts/test_plan_b_sizing.mjs`
- `node research/scripts/audit_a_recovery_stage185.cjs`: 원본 감사 RESULTS.json을 보존하고 VERIFICATION.json에 수정 후 5개 시나리오 결과 저장.
- 필수 A/B 분리 및 예약담보 감사.

가격·수익률 전략 파라미터는 Stage184 그대로다. 이번은 실행 복구 수정으로 별도 복리 수익률을 계산하지 않았다.

## 운영 적용 및 한계

배포 대상: coin-collector, bingx-order-execute, 두 함수가 공유하는 a_recovery_policy.mjs.
2026-09-15 사용자 명시 승인 후 Supabase 프로젝트 `ljazcstmwtuhideaarti`에 직접 배포했다. 확인 버전은 coin-collector v87, bingx-order-execute v69이며 두 함수 모두 ACTIVE다. 배포 시 A/B 실거래 스위치와 B 전략·자격증명·장부는 변경하지 않았다.
실제 장애 시각의 DB 신호·주문·예약 이력을 읽어 신규 정규 판단, 오래된 orphan, 이미 체결된 주문을 구분해야 한다. 답안 누락 건을 추측해서 재진입하지 않는다.
