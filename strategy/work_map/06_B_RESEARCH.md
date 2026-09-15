# B플랜 연구 지도

## 현재 기준선

새 B 연구는 Stage112를 기준선으로 비교한다. Stage16은 출발점이었던 보관 연구본이며 현재 B 런타임 ID가 아니다.

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

- 실행 코드: `research/scripts/research_b_stageNNN_*.py` 또는 검증 목적이 드러나는 이름.
- 결과: `research/results/b_stageNNN_*/RESULTS.json`.
- 채택 성공: `strategy/B_STAGENNN_APPROVED_YYYYMMDD.md`.
- core/보조 선택 경계, 5분 TTL, 0.35% 불리한 이동, 예약담보, 동시 비례감액, 고정수량, 청산확인, 수동/자동 분리를 운영과 동일하게 재현한다.
- 5년/7년 복리, 거래수, 승률, MDD, 비용, 지연, 거절·감액 수, 최대 예약·총노출, 미래참조와 데이터 원천을 남긴다.
- 연구 $100과 실거래 성과 기준금 $650을 섞지 않는다.

## 운영 승격 조건

연구 통과만으로 배포하거나 LIVE를 바꾸지 않는다. 새 B 버전, 사용자 승인, 원자 DB 전환, 신호/실행/청산 테스트, 사전검사, 텔레그램 계획 구분, A/B 분리 감사까지 완료해야 운영 후보가 된다.
