@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY_CMD="
py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD python -c "import sys" >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD goto :python_fail
echo [1/3] Python
%PY_CMD% --version
echo [2/3] Application syntax
%PY_CMD% -m py_compile app.py || goto :fail
echo [3/3] Supabase configuration
if not exist ".env" goto :env_fail
findstr /B "SUPABASE_URL=" ".env"
findstr /B "SUPABASE_SERVICE_ROLE_KEY=" ".env" >nul || goto :env_fail
echo Setup check passed.
pause
exit /b 0
:python_fail
echo ERROR: Python 3 is not installed or not available in PATH.
pause
exit /b 1
:env_fail
echo ERROR: Supabase is not configured. Run SETUP_SUPABASE_WINDOWS.bat.
pause
exit /b 1
:fail
echo ERROR: Setup check failed. Review the message above.
pause
exit /b 1
