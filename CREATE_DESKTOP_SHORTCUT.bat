@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "TARGET=%~dp0START_WINDOWS.bat"
set "WORKDIR=%~dp0"
set "LINK=%USERPROFILE%\Desktop\Coin Issue AI.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%LINK%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%WORKDIR%'; $s.IconLocation='%SystemRoot%\System32\shell32.dll,14'; $s.Description='Coin Issue AI'; $s.Save()"
if exist "%LINK%" (
  echo Desktop shortcut created successfully.
) else (
  echo ERROR: Failed to create desktop shortcut.
)
pause
