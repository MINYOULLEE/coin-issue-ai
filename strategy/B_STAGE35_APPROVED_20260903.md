# B플랜 Stage35 채택·배포 기준 — 2026-09-03

## 사용자 승인

- B플랜을 `b_core_idle_stage35` / `b_core_idle_stage35_v1`로 업그레이드한다.
- A플랜 `answer_mdd30`은 변경하지 않는다.
- B 자동매매 ON·LIVE는 사용자가 켠 상태를 그대로 보존한다. 마이그레이션은 `enabled`와 `test_mode`를 수정하지 않는다.

## 구성

- 기본: AVAX, ICP, BCH, DOGE, UNI — 기존 Stage26 기준 보존.
- 기존 보조: ALGO, ETH, VET — 기존 Stage26 기준 보존.
- 신규 보조: LINK 3시간 연속 5% 소진 반전, DOT 12시간 5% 투매·거래량 3배 반전, LTC 5시간 연속 5% 소진 반전.
- 신규 보조는 격리 3배, 1시간 보유, 동일 종목 선택 경계 최소 2시간이다.
- 기본 기회가 선택된 구간에는 보조를 선택하지 않으며 기본·보조는 동시 보유하지 않는다.
- 신규 희망 담보 비율: LINK 30%, DOT 15%, LTC 15%. 계좌의 실제 Equity/가용담보에서 5%를 남기고 비용을 예약하며 동시 요청은 비례 감액한다.

## 연구 및 실행 검증

- 연구 원금 $100, 최종 $2,007,973.59, 5년 모의 복리 +2,007,873.59%.
- 909회, 승률 55.67%, 종료 기준 최대낙폭 -47.13%, 시간봉 미실현 포함 최대낙폭 -55.20%.
- 신규 보조 거래 173건의 진입 창을 Binance 공개 1분봉으로 재대조했으며 OHLC 불일치 0건이다.
- 진입 지연 0/1/5/10분 모두 재계산했다. 10분 지연도 +1,951,064.60%였으나 운영 진입 TTL은 기존대로 5분 미만이다.
- 위 결과는 동일 데이터에서 발굴·검증했으므로 독립 홀드아웃, BingX 선물 체결, 미래 실거래 성과 보장이 아니다.

## 배포 안전조건

- 전환 시 활성 B 신호·포지션·실행 intent가 없어야 하며 DB 마이그레이션이 이를 강제로 검사한다.
- 새 LINK/DOT/LTC는 주문 없이 LONG/SHORT 격리 3배와 계약 최소수량/최소명목을 사전 검사한다.
- 거래소 설정 변경은 `approved_20260903_stage35_3x_no_orders` 확인 토큰과 B 스케줄러 인증, 무포지션·무주문 조건을 모두 요구한다.
- 주문 사전검사, 예약담보, 불확실 주문 보존·대사, A/B 자격증명·테이블·주문 ID 분리는 유지한다.
- 과거 `pb16-`, `pb26-` 주문은 청산 대사만 허용하며 신규 Stage35 주문은 `pb35-`를 쓴다.

## 증거

- 정본: `strategy/plan_b_standard.json`, `strategy/plan_b_combination_standard.json`
- 연구: `research/results/b_idle_stage34/REPORT.md`, `research/results/b_idle_stage35/results.json`
- 마이그레이션: `supabase/migrations/20260903051252_adopt_plan_b_idle_stage35.sql`

## 상태

- 사용자 채택: 완료
- 로컬 구현·테스트: 완료 — Node 56건, 담보금 테스트 2건, A/B 분리 감사 통과
- Supabase 함수·DB 배포: 완료 — Stage35 ID와 11종목 원자 전환
- BingX 신규 3종목 설정 검사: 완료 — LINK/DOT/LTC LONG·SHORT 격리 3배, 전체 11종목 통과, 주문 0건
- GitHub 배포: 완료 — `main` 브랜치 및 GitHub Pages 소스 반영
