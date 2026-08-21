@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Coin Issue AI - 24H Local Collector
set "LOG_FILE=%~dp0collector_runtime.log"
set "PY_CMD="
py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD python -c "import sys" >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
  echo [%date% %time%] ERROR: Python 3 is not available in PATH.>>"%LOG_FILE%"
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
findstr /B /C:"SUPABASE_SERVICE_ROLE_KEY=sb_secret_" ".env" >nul 2>&1
if errorlevel 1 (
  findstr /B /C:"SUPABASE_SERVICE_ROLE_KEY=eyJ" ".env" >nul 2>&1
  if errorlevel 1 (
    echo [%date% %time%] ERROR: Supabase secret key is not configured.>>"%LOG_FILE%"
    exit /b 2
  )
)
echo Coin Issue AI collector is starting.
echo If the app stops, it will restart after 5 seconds.
:restart
echo [%date% %time%] Collector process starting.>>"%LOG_FILE%"
%PY_CMD% -u app.py >>"%LOG_FILE%" 2>&1
echo [%date% %time%] Collector stopped with code %ERRORLEVEL%. Restarting in 5 seconds.>>"%LOG_FILE%"
timeout /t 5 /nobreak >nul
goto restart
