@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Coin Issue AI - 24H Local Collector
set "PY_CMD="
py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD python -c "import sys" >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
  echo ERROR: Python 3 is not installed or not available in PATH.
  echo Install Python 3 and enable "Add python.exe to PATH".
  start "" "https://www.python.org/downloads/windows/"
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
findstr /B /C:"SUPABASE_SERVICE_ROLE_KEY=sb_secret_" ".env" >nul 2>&1
if errorlevel 1 (
  findstr /B /C:"SUPABASE_SERVICE_ROLE_KEY=eyJ" ".env" >nul 2>&1
  if errorlevel 1 (
    echo Supabase secret key is not configured.
    echo Run SETUP_SUPABASE_WINDOWS.bat first.
    pause
    exit /b 1
  )
)
echo Coin Issue AI collector is starting.
echo If the app stops, it will restart after 5 seconds.
:restart
%PY_CMD% app.py
echo The app stopped. Restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto restart
