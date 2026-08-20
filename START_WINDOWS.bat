@echo off
setlocal EnableExtensions
cd /d "%~dp0"
start "" "http://127.0.0.1:8765"
call "%~dp0START_COLLECTOR_WINDOWS.bat"
