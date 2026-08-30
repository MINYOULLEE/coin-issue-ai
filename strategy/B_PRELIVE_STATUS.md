# B Stage16 비활성 배포 상태 (2026-08-30)

## 완료 / 근거

- 운영 DB 전략 `b_reserved_margin_stage16`, enabled=false, test_mode=true. A 설정/주문 함수는 변경하지 않음.
- `plan-b-strategy` v1: 인증된 preview만 허용. 주문/신호 장부 쓰기 없음. 운영 호출 HTTP200, 5종목 데이터 검증 성공. 호출 시점은 정각 후 5분 초과라 전부 만료 처리. 강제 신호나 추격 주문 없음.
- `telegram-bot-webhook` v12: B Stage16 표시 및 전체 거래 집계 RPC 사용. B의 가짜 `$100+손익` 잔고 제거. 실제 담보는 B 계좌 조회로 확인.
- `plan_b_paper_reservations`: B 모의 전용. DB 트랜잭션 잠금·담보 부족 거절·원자적 단일 선점. 실거래 테이블과 분리. 서비스 권한만 허용, RLS 활성화.
- DB 테스트는 트랜잭션 롤백: 중복 선점 거절, $70 예약 뒤 $30 추가 예약 거절($5 여유), 테스트 장부 0건. anon RPC 권한 없음.
- 신호/담보/주문 생명주기 Node 테스트 13개, 재생 Python 테스트 2개. 주문 생명주기는 **모의 어댑터 테스트**이며 실제 BingX 체결 시험이 아님.

## 차단 / 미완료 (누락시키지 말 것)

1. `plan-b-account-read` 수정본 배포가 보안 검토에서 거절됨. 비인증 상세 실거래 공개 위험에 대한 명시적 승인 또는 공개 범위 변경 필요. 우회 배포 금지. 원격 v5 유지.
2. 실제 BingX 주문 어댑터/계약 최소 수량/유지증거금/체결·청산 동기화는 아직 미완성. 모의 예약을 실거래에 재사용하지 말 것.
3. 실주문용 원자적 예약과 신선한 계좌 스냅샷의 통합, 실제 실행기 연결이 필요함. paper RPC 통과를 live 구현 완료라고 표현하지 말 것.
4. 신호 미리보기는 수동 점검용. 자동 주문 스케줄/실거래 활성화 없음.
5. 역사적 Stage16 연구 수익률은 수정하지 않음. 전송 지연/거래소 제약 반영한 실거래 수익률로 단정하지 않음.

## 배포 내용

Supabase migration name: `plan_b_stage16_disabled_preparation`.
로컬 SQL: `supabase/migrations/20260830122300_adopt_plan_b_aggressive.sql`.
이 SQL은 기존 B 테이블을 전제로 한다. 새 DB에서는 `20260830170000_plan_b_isolated_system.sql`이 먼저 필요하므로 단순 파일명 순 신규 구축은 금지. 운영 migration history와 맞추기 전 일괄 db push 금지.

실거래 활성화/주문 제출은 수행하지 않았다. 다음 작업은 새 연구가 아니라 위 미완성 실행 통합이다.
