@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Coin Issue AI - Supabase Setup

echo.
echo ======================================================
echo   Coin Issue AI - Supabase Secret Key Setup
echo ======================================================
echo.
echo This window saves the key ONLY in this PC's .env file.
echo It does not upload the key to GitHub.
echo.
echo 1. Supabase Dashboard ^> Project Settings ^> API Keys
echo 2. Under Secret keys, reveal/copy an sb_secret_... key
echo 3. Paste it below and press Enter
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$secret=Read-Host 'Paste Supabase secret key';" ^
  "if([string]::IsNullOrWhiteSpace($secret)){throw 'No key entered.'};" ^
  "if($secret -like 'sb_publishable_*'){throw 'That is a publishable key. Copy an sb_secret_ key instead.'};" ^
  "if(-not (($secret -like 'sb_secret_*') -or ($secret -like 'eyJ*'))){throw 'Key format is not recognized.'};" ^
  "$path=Join-Path (Get-Location) '.env';" ^
  "$map=[ordered]@{};" ^
  "if(Test-Path $path){Get-Content $path -Encoding UTF8 ^| ForEach-Object {if($_ -match '^([^#=]+)=(.*)$'){$map[$matches[1].Trim()]=$matches[2]}}};" ^
  "$map['SUPABASE_URL']='https://ljazcstmwtuhideaarti.supabase.co';" ^
  "$map['SUPABASE_SERVICE_ROLE_KEY']=$secret.Trim();" ^
  "if(-not $map.Contains('CLOUD_SYNC_SECONDS')){$map['CLOUD_SYNC_SECONDS']='10'};" ^
  "if(-not $map.Contains('DASHBOARD_HOST')){$map['DASHBOARD_HOST']='127.0.0.1'};" ^
  "$lines=$map.GetEnumerator() ^| ForEach-Object { $_.Key + '=' + $_.Value };" ^
  "[IO.File]::WriteAllLines($path,$lines,(New-Object Text.UTF8Encoding($false)));" ^
  "Write-Host ''; Write-Host 'Saved securely to local .env.' -ForegroundColor Green;"

if errorlevel 1 (
  echo.
  echo Setup failed. Check the message above and try again.
  pause
  exit /b 1
)

echo.
echo Starting Coin Issue AI collector...
start "Coin Issue AI Collector" "%~dp0START_COLLECTOR_WINDOWS.bat"
echo.
echo Setup complete. The public dashboard will receive data shortly.
echo https://minyoullee.github.io/coin-issue-ai/
echo.
pause

