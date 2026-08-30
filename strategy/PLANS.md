# A/B 매매 기준 — 작업 전 반드시 읽기

## A플랜: 기존 운영 기준 보존

- 정본: `strategy/mdd30_standard.json`
- ID: `answer_mdd30`, 버전 `mdd30_final_2026_08_29`
- BTC/ETH/XRP/TRX/SOL, 5개 독립 트리, UTC 00시 시작 시간봉(00:59:59.999 마감)을 사용하고, 마감 후 UTC 01:00(태국 08:00)에 리밸런싱. 기존 실행 시각은 변경하지 않고 표시만 교정.
- 거래소 레버리지 10배, 총 명목노출 최대 1.6배, 고정 손절/익절 없음.
- `BINGX_API_KEY` / `BINGX_SECRET_KEY`; `trade_signals`, `real_trading_state`, `real_trades`, `bingx_trade_history` 사용.
- A 문구의 '종목별 A+B'는 A 모델 내부 구성이다. 플랫폼 B플랜과 혼동 금지.
- 기존 보관 소스 재생은 +257,597.52%, MDD -35.53%. 예전 +799,385.16%/-29.22%는 미재현 기록이며 현재 검증치로 사용 금지.

## B플랜: 사용자 채택 Stage16 공격형

- 정본: `strategy/plan_b_standard.json`, 배포용 사본 `_shared/plan_b_standard.json` (자동 검사로 일치 강제).
- ID: `b_reserved_margin_stage16`, 버전 `b_reserved_margin_stage16_v1`.
- AVAX RSI72/30(3배), ICP RSI24/20(5배), BCH UTC20~22시 2% 반전(3배), DOGE 수축0.35/거래량1.5 확장(5배), UNI UTC7~9시 2% 반전(2배).
- RSI는 Wilder가 아닌 단순평균이며 신호봉의 현재 수익을 제외한 이전 완료봉 기준.
- 실제 보유시간: AVAX 13h / ICP 2h / BCH 4h / DOGE 13h / UNI 7h. 구 연구 표기 12/1/3/12/6은 인덱스였으며 실제 시간으로 재해석 금지.
- 1.15는 신호당 희망 담보 비율이다. 115% 주문 확정이나 손익 배수가 아니다.
- 열린 포지션 담보를 차감하고 equity 5%를 남긴다. 비용까지 예약, 동시 주문은 비례 감액, 부족하면 거절. 진입 수량 고정.
- 미실현 손익과 담보 부족으로 진입 후 예약담보/equity 비율이 상승할 수 있다. 신규 주문 한도와 현재 위험 지표를 혼동하지 않는다.
- `PLAN_B_BINGX_API_KEY` / `PLAN_B_BINGX_SECRET_KEY`; `plan_b_trading_state`, `plan_b_signals`, `plan_b_real_trades`만 사용. A 계정으로 대체 금지.
- Stage16 재생: $100 → $516,614.04, +516,514.04%, 종료 후 MDD -49.00%, 시간봉 평가 MDD -54.64%, 656회, 승률 56.71%.
- B 실거래 시작 기준은 $150. 2026-08-30 B 계좌 잔고/Equity/가용 담보 $150 확인. 연구 $100과 혼동 금지. `$150+실현손익`은 입출금/미실현을 제외한 성과 기준금이지 실제 잔고가 아니다.
- 이전 100만% 기준 미달이지만 사용자가 이 수정본을 명시적으로 채택했다. 연구 판정을 몰래 통과로 고치지 않는다.
- 폐기 대상: ETC/LINK 미래 거래량 후보, Stage14/15 무담보 합성, 5.75 손익배수, 20.7배 목표노출, +18,320,364.82% 주장.

## 구현/배포 상태를 구분할 것

**최신 상태: `EXECUTION_REPAIR_20260831.md`를 먼저 확인.** 아래 2026-08-30 기록은 과거 상태이다. 현재 실행 안전성 수정과 별도 런타임 게이트가 적용됐으며 B 신규 진입은 점검/승인 대기로 잠겨 있다. 연구 정본의 활성화 플래그를 현재 서버 상태로 해석하지 않는다.

채택 기준 고정과 운영 적용은 별개다. 2026-08-30 공개 기록 승인 후 계좌 조회 v6, 텔레그램 v13, 읽기 전용 실행 점검 v2 배포. 공개 기록 200, 무인증 제어 401 확인. 실주문 예약/선점 DB와 BingX 어댑터 준비본을 추가했으나 완전한 자동 진입→청산 동기화 통합은 아직 미완성이다. B 계좌의 실제 롱/숏 레버리지는 전 종목 20배로 채택 기준과 불일치하므로 사용자 수정 필요. B live_ready=false, enabled=false, test_mode=true 유지. 상세 상태는 `B_PRELIVE_STATUS.md` 참조.

## 보조 기능 분리

- A 파랑 / B 보라. 실거래 제어는 인증, 기록은 각 플랜 읽기 전용.
- 공용 텔레그램은 명령·알림 접두어로 A/B 명시. B 데이터가 없다고 A 데이터 표시 금지.
- 계정 연결 성공을 주문 실행 완료로 표현하지 않는다.
- B 주문 예약/잠금과 실거래 장부는 반드시 B 전용. 연구 거래를 실거래 기록에 쓰지 않는다.

## 검증 명령

`python research/scripts/audit_plan_separation.py`

`python research/scripts/test_reserved_margin_stage16.py`

`node --test research/scripts/test_plan_b_sizing.mjs`

파일 해시 기준선: `strategy/plan_freeze_manifest.json`. 새 전략 수정은 별도 버전과 사용자 승인 기록으로만 진행한다.
