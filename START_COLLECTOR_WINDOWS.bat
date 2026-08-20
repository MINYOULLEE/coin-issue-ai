@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
title Coin Issue AI - 24H Local Collector
echo Coin Issue AI 로컬 수집기를 시작합니다.
echo 오류 발생 시 5초 후 자동 재시작합니다.
:restart
py -3 app.py
echo 프로그램이 종료되었습니다. 5초 후 자동 재시작합니다.
timeout /t 5 /nobreak >nul
goto restart
