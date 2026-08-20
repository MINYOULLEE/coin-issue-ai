@echo off
chcp 65001 > nul
cd /d "%~dp0"
set "TARGET=%~dp0START_WINDOWS.bat"
set "WORKDIR=%~dp0"
set "LINK=%USERPROFILE%\Desktop\Coin Issue AI.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut('%LINK%'); $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%WORKDIR%'; $s.IconLocation='%SystemRoot%\System32\shell32.dll,14'; $s.Description='Coin Issue AI 실시간 모니터 실행'; $s.Save()"
if exist "%LINK%" (
  echo.
  echo 바탕화면에 'Coin Issue AI' 바로가기를 만들었습니다.
  echo 다음부터 해당 아이콘을 더블클릭하면 바로 실행됩니다.
) else (
  echo 바로가기 생성에 실패했습니다. 이 파일을 관리자 권한 없이 다시 실행해보세요.
)
pause
