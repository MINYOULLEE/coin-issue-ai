@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Coin Issue AI - 24H Local Collector
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PY_CMD="
py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD python -c "import sys" >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
  echo ERROR: Python 3 is not available in PATH.
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
findstr /B /C:"SUPABASE_SERVICE_ROLE_KEY=sb_secret_" ".env" >nul 2>&1
if errorlevel 1 (
  findstr /B /C:"SUPABASE_SERVICE_ROLE_KEY=eyJ" ".env" >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Supabase secret key is not configured.
    exit /b 2
  )
)
echo Coin Issue AI collector is starting.
echo This single supervisor will restart the collector only after a real failure.
:restart
%PY_CMD% -X utf8 -u app.py
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="10" (
  echo Another collector instance is already running. This window will close.
  timeout /t 3 /nobreak >nul
  exit /b 0
)
echo Collector stopped with code %EXIT_CODE%. Restarting in 5 seconds.
timeout /t 5 /nobreak >nul
goto restart
