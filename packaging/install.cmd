@echo off
setlocal

set "APP_NAME=Stock Analysis Dashboard"
set "APP_DIR=%LOCALAPPDATA%\StockAnalysisDashboard"
set "APP_EXE=%APP_DIR%\StockAnalysis.exe"
set "DESKTOP_LINK=%USERPROFILE%\Desktop\Stock Analysis Dashboard.lnk"
set "START_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Stock Analysis Dashboard.lnk"
set "UNINSTALL_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Uninstall Stock Analysis Dashboard.lnk"

if not exist "%APP_DIR%" mkdir "%APP_DIR%"
copy /Y "%~dp0StockAnalysis.exe" "%APP_EXE%" >nul
copy /Y "%~dp0uninstall.cmd" "%APP_DIR%\uninstall.cmd" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$shell=New-Object -ComObject WScript.Shell;" ^
  "$appDir=Join-Path $env:LOCALAPPDATA 'StockAnalysisDashboard';" ^
  "$exe=Join-Path $appDir 'StockAnalysis.exe';" ^
  "$desktop=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Stock Analysis Dashboard.lnk';" ^
  "$start=Join-Path ([Environment]::GetFolderPath('Programs')) 'Stock Analysis Dashboard.lnk';" ^
  "$uninstall=Join-Path ([Environment]::GetFolderPath('Programs')) 'Uninstall Stock Analysis Dashboard.lnk';" ^
  "function New-Link($path,$target,$workdir){$shortcut=$shell.CreateShortcut($path);$shortcut.TargetPath=$target;$shortcut.WorkingDirectory=$workdir;$shortcut.Save()};" ^
  "New-Link $desktop $exe $appDir;" ^
  "New-Link $start $exe $appDir;" ^
  "New-Link $uninstall (Join-Path $appDir 'uninstall.cmd') $appDir;"

if /I not "%STOCK_ANALYSIS_SKIP_LAUNCH%"=="1" start "" "%APP_EXE%"
endlocal
