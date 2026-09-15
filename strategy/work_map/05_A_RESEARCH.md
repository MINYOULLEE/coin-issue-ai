# A플랜 연구 지도

## 현재 기준선

최신 실행 복구 점검: `research/results/a_stage185_recovery_audit/REPORT.md`. 후속 로컬 보수: `strategy/A_RECOVERY_REPAIR_20260915.md`. Stage184 전략 파라미터는 유지하며 운영 배포 완료 여부는 보수 기록에서 별도로 확인한다.

새 A 연구는 항상 Stage184를 기준선으로 비교한다. 후보가 Stage184보다 좋아 보여도 연구 결과일 뿐이며 사용자 채택 전 운영 정본에 반영하지 않는다.

## 연구 계보

| 구간 | 주제 | 대표 자료 | 판정 |
|---|---|---|---|
| Stage48~59 | 기존 A 개선, 동적 목표/청산 탐색 | `research/results/a_dynamic_targets_stage59/RESULTS.json` | 연구 이력 |
| Stage67~80 | 노출 확대와 낙폭 방어, 변형시장 | `research/results/a_drawdown_guard_stage75/RESULTS.json`, `research/results/a_stage80_extended_synthetic/RESULTS.json` | Stage75 채택 이력, 현재는 과거 |
| Stage81~126 | 변동성·비용·선택적 리사이즈·실행복원 | `research/results/ab_7y_extension/A_STAGE125_DELAY_RESILIENT_RESIZE.json` | Stage126까지 채택 이력 |
| Stage127~135 | 장중 급등 숏 방어 | `research/results/ab_7y_extension/A_STAGE132_RALLY_GUARD_MDD_REFINEMENT.json`, `research/results/a_rally_guard_minutes_stage133/RESULTS.json` | Stage135 구성 현재 유지 |
| Stage136~142 | 5배 단일과 방어 후보 | `research/results/a_stage136_leverage_defense/VALIDATION.json`, `research/results/a_stage139_single_guard_validation/RESULTS.json` | C 연구로 이어짐 |
| Stage143~176 | C 손실방어 조건 탐색 | `research/results/a_stage143_c_intraday_controller/RESULTS.json`, `research/results/a_stage175_c_fresh_paths/RESULTS.json` | 후보 선별 |
| Stage177~184 | C 겹침·경로·지연·분봉 최종검증 | `research/results/a_stage177_c_overlap_priority/RESULTS.json`, `research/results/a_stage183_c_minute_portfolio/RESULTS.json` | Stage184 채택 |

## 새 연구 저장 규칙

- 실행 코드: `research/scripts/research_a_stageNNN_*.py` 또는 `validate_a_stageNNN_*.py`
- 결과: `research/results/a_stageNNN_*/RESULTS.json`
- 채택 성공: `strategy/A_STAGENNN_APPROVED_YYYYMMDD.md`
- 실패/보류도 원인, 비용, 거래수, 승률, 5년/7년 복리, MDD, 지연 결과를 결과 JSON에 남긴다.
- 미래참조 여부, 데이터 원천, 시작금, 수수료·슬리피지·펀딩, MDD 정의를 반드시 기록한다.
- 기존 결과를 덮어쓰지 말고 새 Stage 번호를 사용한다.

## 비교 최소 항목

Stage184 기준과 후보를 같은 표본·같은 비용으로 비교하고 5년 복리, 7년 복리, 거래수, 승률, 완료봉 MDD, 봉 내부 불리경로 MDD, 비용 2·3배, 0·1·3·5분 지연, 순서보존 변형시장, 분봉 커버리지를 함께 보고한다.
