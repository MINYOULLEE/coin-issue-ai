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
  "$old=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue; if($old){Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue; Unregister-ScheduledTask -TaskName $name -Confirm:$false};" ^
  "$action=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/d /c ""'+$target+'""') -WorkingDirectory $root;" ^
  "$logon=New-ScheduledTaskTrigger -AtLogOn;" ^
  "$settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -WakeToRun;" ^
  "Register-ScheduledTask -TaskName $name -Action $action -Trigger $logon -Settings $settings -Description 'Runs exactly one Coin Issue AI collector and restarts it after failures.' -Force | Out-Null;" ^
  "Remove-Item -LiteralPath (Join-Path '%STARTUP%' 'Coin Issue AI Collector.lnk') -Force -ErrorAction SilentlyContinue;" ^
  "Start-ScheduledTask -TaskName $name;"
if errorlevel 1 (
  echo ERROR: Failed to install the single collector task.
  echo Try right-clicking this file and choose Run as administrator.
  pause
  exit /b 1
)
powercfg /change standby-timeout-ac 0 >nul 2>&1
echo Single Coin Issue AI collector task installed successfully.
echo Old duplicate startup entries were removed.
echo The collector will start once at Windows logon and restart only after a failure.
pause
