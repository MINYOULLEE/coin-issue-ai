@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist .env copy .env.example .env > nul
echo Coin Issue AI 시작 중...
start "" http://127.0.0.1:8765
py -3 app.py
if errorlevel 1 python app.py
pause
