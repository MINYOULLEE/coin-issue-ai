# Coin Issue AI

실시간 암호화폐 이슈, 공식기관 발표, 거래소 공지와 시장 데이터를 한 화면에서 확인하는 로컬 대시보드입니다.

## 주요 기능

- CFTC, SEC, Federal Reserve 공식 발표 감시
- 주요 암호화폐 뉴스와 거래소 공지 수집
- BTC, ETH, XRP, SOL, BNB 실시간 가격·거래량 분석
- 호재·악재·중요도 자동 분류
- 24시간 및 1주 확률적 가격 범위
- 100점 기준 종합추천
- 예정된 규제기관 일정과 FOMC 핫이슈 표시
- 텔레그램 긴급 알림과 선택적 AI 한국어 요약

## Windows 실행

1. Python 3.10 이상을 설치합니다.
2. 저장소를 다운로드하거나 복제합니다.
3. `START_WINDOWS.bat`을 실행합니다.
4. 브라우저에서 `http://127.0.0.1:8765`를 엽니다.

바탕화면 바로가기는 `CREATE_DESKTOP_SHORTCUT.bat`을 한 번 실행해 생성할 수 있습니다.

## 선택 설정

`.env.example`을 `.env`로 복사한 뒤 필요한 항목만 입력합니다.

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

키가 없어도 기본 수집, 시장 분석과 대시보드는 동작합니다.

## 보안

- `.env`와 `coin_issues.db`는 Git에서 제외됩니다.
- API 키나 텔레그램 토큰을 커밋하지 마세요.
- 저장소에는 개인 데이터베이스가 포함되지 않습니다.

## 주의사항

이 프로그램의 분석과 예측은 공개 데이터 기반의 확률적 추정이며 투자 자문이나 수익 보장이 아닙니다. 실제 투자 판단 전 공식 원문과 최신 시장 상황을 직접 확인하세요.

자세한 한국어 설명은 [README_KO.md](README_KO.md)를 참고하세요.
