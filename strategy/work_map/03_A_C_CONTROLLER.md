# A + C 보조 컨트롤러

## 역할

C는 독립 플랜이나 수익 확대 신호가 아니다. **A 5배 단일의 급변시장 손실만 방어**하며 A 자동수량에만 작동한다. 현재 A Stage184 안에 포함된 운영 규칙이다.

## 발동 구조

공통 완료 시간봉을 한 번씩 평가하고 다음 수집 주기에서 실행한다.

1. 5종목 시간수익률 중앙값의 최근 6시간 변동성이 최근 168시간의 1.8배 이상.
2. BTC/ETH/XRP/TRX/SOL 최근 24시간 수익률 평균 쌍상관이 0.75 이상.
3. 현재 A 보유방향에 대해 다음 중 하나 이상.
   - 3시간 5% 역행 포지션 2개 이상.
   - 3시간 3% 역행 포지션 3개 이상.
   - 6시간 3% 역행 포지션 3개 이상.

해당 자동수량의 합집합을 한 번 청산한다. 3시간 3% 조건은 신규 재진입 48시간, 6시간 3% 조건은 24시간 동결하며 겹치면 양수 중 짧은 24시간을 사용한다. 수동수량과 기존 비대상 포지션은 건드리지 않는다.

## 정본·근거

- 정본: `strategy/mdd30_standard.json`의 `c_controller`
- 승인 기록: `strategy/A_STAGE184_APPROVED_20260914.md`
- 최종 경로 조합: `research/results/a_stage177_c_overlap_priority/RESULTS.json`, `research/results/a_stage178_c_combined_paths/RESULTS.json`
- 실행 스트레스: `research/results/a_stage179_c_execution_stress/RESULTS.json`
- 분봉 자료·포트폴리오: `research/results/a_stage182_c_futures_minutes/RESULTS.json`, `research/results/a_stage183_c_minute_portfolio/RESULTS.json`

## C 연구 계보

Stage143부터 장중 컨트롤러를 분리했고, Stage145~176에서 손실 경계·조건 조합·변형시장·보존률을 탐색했다. Stage177~183에서 겹침 우선순위, 경로 결합, 실행 지연, Binance USD-M 1분 이벤트 114/114를 검증한 뒤 Stage184로 채택했다.

## 변경 판단

C 조건을 넓혀 평상시 수익 거래까지 자르는 변경은 목적 위반이다. 조건·동결·청산 대상을 바꾸면 A 본체 변경이므로 새 A 버전, 전체 5년/7년 재생, 변형시장, 비용, 지연, 분봉 검증과 사용자 승인이 필요하다.
