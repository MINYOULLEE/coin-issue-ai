# B플랜 연구 지도

## 현재 기준선

2026-10-12 Stage170 채택 후 새 연구는 `b_icp_continuation_stage170_v1`을 기준선으로 비교한다. 아래 Stage168~170 발굴 당시 기준선은 Stage112였으며 시간순 연구 이력이다. Stage16은 보관 연구본이다.

다음 연구 축은 [`04_B_C_CONTROLLER.md`](04_B_C_CONTROLLER.md)의 순서대로 진행한다. 먼저 B 본체 수익 확대 후보를 찾고, 그 후보의 특이 손실 구간만 B 전용 C로 방어한다.

## 연구 계보

| 구간 | 주제 | 대표 자료 | 판정 |
|---|---|---|---|
| Stage16 | 5개 core 공격형과 예약담보 | `strategy/archive/plan_b_stage16_v1.json`, `research/results/reserved_margin_stage16.json` | 보관 기준선 |
| Stage20~26 | ALGO/ETH/VET 희소 보조, 지연·충돌·인계 | `research/results/b_sparse_stage20/REPORT.md`, `DELAY_COLLISION_STAGE24.md`, `HANDOFF_STAGE25.md` | Stage26 채택 이력 |
| Stage34~45 | LINK/DOT/LTC/BNB 보조와 동시 비례배분 | `research/results/b_idle_stage35/results.json`, `research/results/b_deployed_semantics_stage40/REPORT.md`, `strategy/B_STAGE45_APPROVED_20260903.md` | 현재 신호 계보에 포함 |
| Stage46~66 | 수익보호 청산 | `strategy/B_STAGE66_APPROVED_20260907.md` | 현재 청산 계보에 포함 |
| Stage67~93 | ALGO 문턱·ADA 보조·선물 분봉 | `research/results/b_algo_ada_combo_stage91/results.json`, `research/results/b_algo_ada_futures_stage92/results.json` | Stage93 신호 현재 유지 |
| Stage94~112 | 7년 민감구간, 지연, 구간 보호, 재현 감사 | `research/results/ab_7y_extension/B_STAGE103_EXTENSION_DIAGNOSIS.json`, `B_STAGE111_CAUSALITY_REPRODUCIBILITY_AUDIT.json`, `strategy/B_STAGE112_APPROVED_20260910.md` | Stage112 채택 |

## 철회·실패 자료

- `research/results/failure/`는 반복하지 말아야 할 연구를 찾는 첫 위치다.
- Stage14/15의 5.75 손익배수, 20.7배 목표노출, 철회된 헤드라인 수익률은 운영 기준으로 복원하지 않는다.
- `research/results/failure/B-STAGE35-RESEARCH-RUNTIME-OVERLAP-MISMATCH.md`의 연구/운영 동시보조 불일치를 무시하지 않는다.

## 새 연구 저장 규칙

2026-10-12 ICP 같은 방향 유지 비교(Stage168): `research/results/b_stage168_icp_continuation/RESULTS.json` 및 `VERIFICATION.json`.
현재 Stage112를 정확히 재현한 뒤, 2시간 청산·재진입과 최대 4/8/24/168시간 고정수량 유지 8개 후보를 비교했다. 단순 유지 후보는 기본비용 수익이 악화했다. 동일 방향 재신호에 현재 노출·담보 조건을 추가한 최대 8시간 유지 후보는 5년 최종금액 +16.96%, 같은 시간봉 최대낙폭, 3분할 및 비용 2배 개선으로 후속 검증 후보다. ICP 분봉 체결·BingX·미래 독립검증은 미완료이며 운영 적용하지 않았다. 확장 파일의 실제 공통 구간은 2021-05-11~2026-08-30으로, 온전한 7년 데이터가 아니다.

- 실행 코드: `research/scripts/research_b_stageNNN_*.py` 또는 검증 목적이 드러나는 이름.

2026-10-12 Stage169 분봉 후속: `research/results/b_stage169_icp_minutes/RESULTS.json` 및 `VERIFICATION.json`. 공개 ICP USD-M 분봉 170/170 상장 후 구간(55,300분)을 확보했고, API 누락 21개는 공식 일별 ZIP과 체크섬으로 보완했다. 상장 전 5개는 검증 불가로 별도 기록했다. 동일 방향 31개 신호 연결 구간을 각각 $100 독립 ICP 계정으로 비교했으며, 지연 0/1/3/4분·비용 1/2배·추가 청산 슬리피지 0/0.1/0.3%의 24개 조합 모두 평균 개선이었다. 1분·기본비용은 개선22/악화2/동일7, 거래93→60. 이는 전체 B 동시 담보·core/supplement 충돌·현재 운영 고정 profit trigger를 포함한 5년 복리 재검증이 아니다. Stage168의 +6,025,600.63%를 분봉 검증 완료 수익률로 승격하지 않으며 운영 변경은 없다.
- 결과: `research/results/b_stageNNN_*/RESULTS.json`.

2026-10-12 Stage170 전체 B 동시 담보·그룹 충돌 검증: `research/results/b_stage170_portfolio_continuation/RESULTS.json`, `PRIMARY_LEDGERS.json`, `VERIFICATION.json`. 현재 운영 고정 수익보호 계수와 실제 보유시간(UNI 7시간 포함), 담보 예약·동시 비례배분·3.75배 신규 노출 한도·5분 TTL·청산 확인 후 진입을 같은 엔진에 적용했다. 2021-08-28~2026-08-30, $100 시작, 1분 지연·기본비용에서 기존 B $1,277,162.34(+1,277,062.34%, 787회) 대비 조건부 ICP 최대 8시간 유지 $1,976,578.03(+1,976,478.03%, 770회), 최종금액 +54.76%. 관측 시점 혼합 시세 MDD는 양쪽 -53.41%, 보수적 OHLC 낙폭 한계치는 -54.25%. ICP 149→120회, 기존 수량을 유지한 재신호 경계 28개, core/supplement 동시 보유 0건. 11개 비용·지연 조합은 전부 개선했으나 3분할은 2개만 개선(마지막 구간 +2,618.82%→+2,599.11%). 전 구간 통과 또는 실거래 검증 완료로 취급하지 않는다. ICP는 확보 분봉, ALGO/ADA는 보유 분봉, 나머지는 시간봉 프록시이며 UNI 수익보호 원본 시간봉 1개 누락은 기존 보호선 유지로 처리했다. 실제 펀딩·호가 깊이·BingX 청산 단계 및 모든 종목 동기 분봉 검증은 미완료다. 이전 Stage112/168 발표 숫자와 체결·예약·보호선 계산이 달라졌으므로 새 엔진의 기준선과 후보끼리만 비교한다. 운영 변경 없음.
- 채택 성공: `strategy/B_STAGENNN_APPROVED_YYYYMMDD.md`.
- core/보조 선택 경계, 5분 TTL, 0.35% 불리한 이동, 예약담보, 동시 비례감액, 고정수량, 청산확인, 수동/자동 분리를 운영과 동일하게 재현한다.
- 5년/7년 복리, 거래수, 승률, MDD, 비용, 지연, 거절·감액 수, 최대 예약·총노출, 미래참조와 데이터 원천을 남긴다.
- 연구 $100과 실거래 성과 기준금 $650을 섞지 않는다.

## 운영 승격 조건

연구 통과만으로 배포하거나 LIVE를 바꾸지 않는다. 새 B 버전, 사용자 승인, 원자 DB 전환, 신호/실행/청산 테스트, 사전검사, 텔레그램 계획 구분, A/B 분리 감사까지 완료해야 운영 후보가 된다.
