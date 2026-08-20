# Coin Issue AI 무료 상시 페이지 설정

## 동작 구조

- Windows PC: 뉴스·거래소 공지·시세 수집과 분석
- Supabase 무료 DB: 최신 결과 1개 저장
- GitHub Pages: 최신 결과를 5초마다 읽어 항상 표시

PC가 꺼져도 페이지와 마지막 데이터는 유지됩니다. PC가 켜지고 수집기가 실행 중일 때 데이터가 새로 갱신됩니다.

## 1. Supabase 프로젝트 만들기

1. https://supabase.com 에서 무료 프로젝트를 만듭니다.
2. SQL Editor에서 `supabase_setup.sql` 내용을 실행합니다.
3. Project Settings → API에서 Project URL, anon public key, service_role key를 확인합니다.

`service_role` 키는 절대로 GitHub에 올리거나 다른 사람에게 보내지 마세요.

## 2. 로컬 수집기 설정

`.env.example`을 복사해 `.env`로 만들고 다음을 입력합니다.

```env
SUPABASE_URL=https://프로젝트.supabase.co
SUPABASE_SERVICE_ROLE_KEY=로컬에만_보관할_service_role_키
```

`START_COLLECTOR_WINDOWS.bat`을 실행합니다. Windows 로그인 때 자동 실행하려면 `INSTALL_WINDOWS_AUTOSTART.bat`을 한 번 실행합니다.

## 3. GitHub Pages 설정

`docs/config.js`에 Project URL과 anon public key를 입력합니다.

```javascript
supabaseUrl: "https://프로젝트.supabase.co",
supabaseAnonKey: "anon_public_key",
```

GitHub Settings → Pages에서 `Deploy from a branch`, `main`, `/docs`를 선택합니다. `service_role` 키는 절대 `config.js`에 넣지 마세요.

## 4. 확인

- 로컬: http://127.0.0.1:8765
- 공개: GitHub가 발급한 `github.io` 주소
- 초록색 `실시간 연결`: 최근 45초 안에 동기화
- 빨간색 `수집기 중단`: 페이지는 열리지만 PC 수집기가 멈춘 상태

## 문제 해결

- Python 없음: Python 3.10 이상 설치, 설치할 때 `Add Python to PATH` 선택
- `config.js 설정 필요`: `docs/config.js` 두 값 확인
- `HTTP 401/403`: anon 키 또는 SQL 정책 확인
- 동기화 오류: 로컬 화면의 `클라우드 동기화` 상태와 `.env` 확인
