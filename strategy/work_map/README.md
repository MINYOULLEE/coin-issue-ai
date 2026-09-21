# A/B 시스템 작업 지도

이 폴더는 파일을 새로 복제한 전략 저장소가 아니라 **현재 정본과 연구 자료를 찾는 단일 입구**다. 기존 파일을 이동하지 않아 코드·문서 링크와 해시 기준선이 깨지지 않게 했다.

## 먼저 고를 문서

| 작업 대상 | 읽을 문서 | 현재 상태 |
|---|---|---|
| A플랜 본체 | [`01_A_PLAN.md`](01_A_PLAN.md) | 운영 정본 Stage184 |
| B플랜 본체 | [`02_B_PLAN.md`](02_B_PLAN.md) | 운영 정본 Stage112 |
| A의 C 보조 | [`03_A_C_CONTROLLER.md`](03_A_C_CONTROLLER.md) | A 손실 방어 전용 |
| B의 C 보조 | [`04_B_C_CONTROLLER.md`](04_B_C_CONTROLLER.md) | 연구 전용, 아직 운영 미적용 |
| A 연구 | [`05_A_RESEARCH.md`](05_A_RESEARCH.md) | Stage184 이후 후보는 연구 상태부터 시작 |
| B 연구 | [`06_B_RESEARCH.md`](06_B_RESEARCH.md) | Stage112 이후 후보는 연구 상태부터 시작 |
| R-Lab | [`../RLAB_SHADOW_DECISION_LAB_20260921.md`](../RLAB_SHADOW_DECISION_LAB_20260921.md) | A/B/C 비개입 가상 판단·확률 보정 자료 수집 |

## 절대 섞지 않는 기준

- A 운영 ID는 `answer_mdd30`, 버전은 `mdd30_5x_c_controller_stage184_v1`이다.
- B 운영 ID는 `b_regime_guard_stage112`, 버전은 `b_regime_guard_stage112_v1`이다.
- A 문구의 `종목별 A+B`는 과거 표시 문구일 뿐 별도 보조 작업 분류로 사용하지 않는다.
- C는 독립 수익 전략이 아니라 A 자동수량의 급변 손실을 방어하는 컨트롤러다.
- 채택, 구현, 배포, LIVE, 실거래 검증은 서로 다른 상태다. 연구 성과만으로 배포하거나 LIVE를 바꾸지 않는다.
- A/B의 API 자격증명, 상태, 신호, 주문, 거래 장부, 알림 표식을 공유하거나 대체하지 않는다.
- 사용자가 켠 실거래 스위치는 점검·연구·문서 정리 중 변경하지 않는다.
- R-Lab은 관찰 전용이며 A/B/C 주문·담보·레버리지·스위치에 연결하지 않는다.

## 모든 작업의 시작과 종료

작업 전 `strategy/PLANS.md`, `strategy/mdd30_standard.json`, `strategy/plan_b_standard.json`을 전부 읽는다. B를 만지면 `strategy/plan_b_combination_standard.json`, `strategy/B_STAGE26_APPROVED_20260831.md`도 읽는다.

작업 종료 전 아래를 실행한다.

```text
python research/scripts/audit_plan_separation.py
python research/scripts/test_reserved_margin_stage16.py
node --test research/scripts/test_plan_b_sizing.mjs
```

전략 정본을 바꾼 경우에만 새 버전, 사용자 승인 기록, 테스트, `strategy/plan_freeze_manifest.json` 해시 갱신을 함께 수행한다.
