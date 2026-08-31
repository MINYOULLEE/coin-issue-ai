# 보조 감시 및 뉴스 부분 실패 수정

2026-08-31 사용자 요청: 점검만 하지 말고 수정. 실거래 ON/OFF·잠금·스케줄 변경 금지.

## 유지한 운영 상태

- A/B enabled=true, test_mode=false. cron 1~6 모두 active=true, 매분 실행 유지.
- B runtime.live_ready=true는 사용자 재활성화 후 운영 서버에서 읽어 보존했다. 이번 작업에서 새로 활성화한 것이 아니다.
- 로컬에 남았던 옛 runtime=false와 감사 기준을 현재 사용자 승인 상태로 동기화했다. 연구 정본의 과거 활성화 플래그는 그대로 유지한다.
- 매매 신호·종목·수량 계산·담보 비율·레버리지 변경 없음. 검증용 실주문 없음.

## 완료

- B v12에서 빠졌던 복구 오류 확인, 실행/청산 상태 저장 복원. 개별 주문·청산 결과의 error/ok=false도 최상위 실패로 보고.
- B signals/execute/close 상태가 3분 이상 갱신되지 않거나 실패하면 Telegram 보조 경고. A 복구 실패와 뉴스별 수집 실패도 포함.
- 같은 보조 상태 반복 알림 억제, 변화 및 복구 알림. Telegram 상태 조회/저장 오류도 확인. Telegram 자체 전체 중단은 같은 봇으로 알림 보장이 불가능함.
- HTTP 수집기가 400 이상 외에 status 없는 timeout/error_msg, HTTP200+ok=false 및 개별 results 오류도 포착. JSON 아닌 응답은 안전하게 처리.
- 뉴스 RSS 대신 HTML 차단 화면을 받은 경우 정상 처리하지 않음. CFTC 공식 목록 fallback 추가. 원문 URL·공식 발행일 유지.
- Coinbase Status 공식 RSS를 별도 출처로 추가. 블로그와 다른 내용이며 블로그 복구로 표시하지 않음.
- 뉴스 일부 실패 시 전체 수집 상태를 부분 실패로 표시하되 거래 처리는 계속한다.

## 배포 및 검증

- plan-b-executor v13 / plan-b-account-read v13 / coin-collector v76 / telegram-trade-notify v23
- DB migration: operational_monitoring_news_alerts; SQL: supabase/repairs/operational_monitoring_20260831.sql
- 4개 함수·상대 의존성 원격 재조회 일치 확인.
- Node 52개 테스트 통과. Stage16 Python 2개 통과. 37개 파일 기준선 및 A/B 분리 감사 통과.
- SQL 실제 함수 테스트: status 없는 timeout, HTTP200 실패, results 오류 각각 포착; 비JSON HTTP200 오탐 없음. 테스트 트랜잭션 전부 rollback; 가짜 오류/주문 영구 기록 없음.
- 05:08 UTC B signals/execute/close 모두 ok=true, 갱신 재개 확인. Coinbase Status 25개 항목 파싱·당일 관련 1건 수집.

## 아직 해결되지 않은 외부 제한

- CFTC Press / CFTC Speeches: 운영 서버에서 원래 RSS 및 공식 대체 목록 모두 HTTP403. 로컬에서는 공식 목록/RSS HTTP200이지만 운영 경로 복구는 아님.
- Coinbase 블로그: RSS 및 공식 블로그 목록 HTTP403. 공식 장애 피드는 정상이나 블로그 전체를 대체하지 않음.
- 결과: 11개 출처 중 8개 수집 가능, 원래 3개 출처 차단은 남아 있다. 감시 수정과 출처 접속 복구를 혼동하지 않는다.
- 차단 우회나 무단 외부 프록시는 도입하지 않았다. 출처의 허용된 API/배포 피드 또는 승인된 별도 수집 환경이 필요하다.

공식 출처: https://www.cftc.gov/RSS/index.htm / https://www.cftc.gov/PressRoom/PressReleases / https://status.coinbase.com/history
