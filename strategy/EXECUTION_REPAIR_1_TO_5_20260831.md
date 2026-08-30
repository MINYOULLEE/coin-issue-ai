# 사용자 승인 1~5번 실행·표시 수정 (2026-08-31 태국시간)

범위: 체결 확인, 비동기 복구, 정산 알림, 오류 노출, 실제 시각/상태 표시. 전략 신호·담보 배분·레버리지·수익률 기준 변경 없음.

## 적용 내역

1. A: 요청 수량/신호 가격을 실제 체결로 대체 기록하지 않는다. 거래소 실제 executedQty/avgPrice만 장부에 기록한다. 0/불명확 응답은 대기, 부분 체결은 실제 수량만 기록한다.
2. A: 주문 전 요청 내용을 예약에 영속 저장한다. 응답 단절/장부 저장 실패 뒤 예약을 시간만으로 삭제하지 않는다. 기존 clientOrderId 조회로만 복구하며 재주문·강제 청산하지 않는다. queued/pending은 일일 진입 완료가 아니다. 수집기 매 주기에 복구하며, 복구 호출 자체 실패도 표시한다.
3. B: close_price와 net_pnl_usd가 확인된 건만 청산 알림 발송. net=null을 0으로 표시하지 않는다. 거래별 발송 확인 필드로 뒤늦게 정산된 과거 거래도 조회한다. B 실거래 청산 기록은 적용 당시 0건으로 과거 발송 건 재전송 없음.
4. B: 복구 오류를 응답·시스템 오류·별도 상태 테이블에 남긴다. 복구 오류가 있을 때 그 실행 회차의 신규 주문은 진행하지 않지만 기존 청산 관리는 계속한다. 설정 스위치를 변경하는 기능이 아니다.
5. A: UTC00 시작 시간봉 마감(00:59:59.999) 이후 UTC01 / 태국08시 실행으로 설명 교정. 기존 decision_hour_utc=0은 봉 시작 시각이며 유지; 별도 실행 시각 메타데이터 추가. UI는 신호 없음/갱신 지연/오류/체결 대기와 주문 허용 상태를 구분한다.

## 배포

- DB migration: execution_reconciliation_reporting_repair
- SQL 보관: supabase/repairs/execution_1_to_5_20260831.sql
- bingx-order-submit v10 / bingx-account-read v44 / coin-collector v75
- plan-b-account-read v11 / plan-b-executor v11 / plan-b-strategy v6
- telegram-trade-notify v22
- 7개 함수와 모든 상대 의존 파일을 원격에서 다시 읽어 로컬 배포본 일치 확인.

## 검증

- Node 43개 테스트 통과: 실제 체결, 0체결, 부분 체결, 타임아웃, DB 실패, 중복 예약, OFF, A/B 격리, 지연 정산 알림, 기존 B 사이징/실행, UI 세션, TS/JS 파싱.
- test_reserved_margin_stage16.py: 2개 통과.
- audit_plan_separation.py: 32개 해시 기준선 및 A/B 정본 일치 통과.
- 상태 테이블 RLS 및 anon/authenticated 권한 없음, 예약 RPC anon 실행 금지, 제출된 예약 TTL 보존 확인.
- 보안 advisor ERROR/WARN 없음. RLS/no-policy INFO는 서버 전용 테이블의 의도된 접근 차단이다. 설명: https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy
- 배포 후 2026-08-30 21:32 UTC: A 복구 ok=true/errors=[]; B signals/close ok=true; 최근 5분 system_errors 0건.

## 설정 보존 / 검증 한계

- 전후 동일: A enabled=true/test_mode=false; B enabled=false/test_mode=false; B runtime.live_ready=false.
- cron 1/2/3/4/6 active=true, 5(B 신규 실행) active=false. 이번 수정에서 잠금/활성화/스케줄 변경 없음.
- 사용자 계좌에 검증용 주문은 넣지 않았다. 장애 주입 테스트 통과는 실제 신규 거래의 종단 간 검증 완료를 뜻하지 않는다.
- 거래소에서 주문 존재 자체를 확인하지 못하면 예약을 유지하고 수동 확인이 필요하다. 불명확 주문을 임의로 다시 보내지 않는다.
- Telegram 발송 성공 후 DB 발송확인 저장 실패 시 다음 회차에 중복 알림 가능(외부 발송과 DB 기록은 단일 트랜잭션이 아님). 지연 정산 누락은 수정했으나 exactly-once 보장은 아니다.
- 화면은 JS 실행/분리 테스트로 검증했으며 인증된 운영 화면의 시각 검수는 별도로 수행하지 않았다.
