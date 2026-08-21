@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "TARGET=%~dp0START_COLLECTOR_WINDOWS.bat"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$name='Coin Issue AI Collector';" ^
  "$target='%TARGET%';" ^
  "$root='%~dp0';" ^
  "$action=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/d /c ""'+$target+'""') -WorkingDirectory $root;" ^
  "$logon=New-ScheduledTaskTrigger -AtLogOn;" ^
  "$watchdog=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5);" ^
  "$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -WakeToRun;" ^
  "Register-ScheduledTask -TaskName $name -Action $action -Trigger @($logon,$watchdog) -Settings $settings -Description 'Keeps the Coin Issue AI local collector running and restarts it automatically.' -Force | Out-Null;" ^
  "Remove-Item -LiteralPath (Join-Path '%STARTUP%' 'Coin Issue AI Collector.lnk') -Force -ErrorAction SilentlyContinue;" ^
  "Start-ScheduledTask -TaskName $name;"
if errorlevel 1 (
  echo ERROR: Failed to install the collector watchdog.
  echo Try right-clicking this file and choose Run as administrator.
  pause
  exit /b 1
)
powercfg /change standby-timeout-ac 0 >nul 2>&1
echo Windows 24H collector watchdog installed successfully.
echo - Starts at Windows logon
echo - Checks every 5 minutes
echo - Restarts automatically after a crash
echo - Prevents sleep while the PC is plugged in
pause
