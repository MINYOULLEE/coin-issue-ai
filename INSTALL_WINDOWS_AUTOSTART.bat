@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "TARGET=%~dp0START_COLLECTOR_WINDOWS.bat"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%STARTUP%\Coin Issue AI Collector.lnk');$s.TargetPath='%TARGET%';$s.WorkingDirectory='%~dp0';$s.WindowStyle=7;$s.Save()"
if errorlevel 1 (
  echo ERROR: Failed to install Windows autostart shortcut.
  pause
  exit /b 1
)
echo Windows autostart shortcut installed successfully.
pause
