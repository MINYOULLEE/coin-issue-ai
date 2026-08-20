@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "TARGET=%~dp0START_COLLECTOR_WINDOWS.bat"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%STARTUP%\Coin Issue AI Collector.lnk');$s.TargetPath='%TARGET%';$s.WorkingDirectory='%~dp0';$s.WindowStyle=7;$s.Save()"
echo Windows 시작프로그램 등록 완료.
pause
