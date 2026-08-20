@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] Python 확인
py -3 --version || goto :fail
echo [2/3] 프로그램 문법 확인
py -3 -m py_compile app.py || goto :fail
echo [3/3] 환경설정 확인
if not exist .env (
  echo .env 파일이 없습니다. START_COLLECTOR_WINDOWS.bat 첫 실행 시 자동 생성됩니다.
) else (
  findstr /B "SUPABASE_URL=" .env
)
echo.
echo 기본 점검 완료.
pause
exit /b 0
:fail
echo.
echo 점검 실패. 위 오류를 확인하세요.
pause
exit /b 1
