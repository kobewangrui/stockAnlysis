@echo off
setlocal

set "APP_DIR=%LOCALAPPDATA%\StockAnalysisDashboard"

taskkill /IM StockAnalysis.exe /F >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$paths=@(" ^
  "  (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Stock Analysis Dashboard.lnk')," ^
  "  (Join-Path ([Environment]::GetFolderPath('Programs')) 'Stock Analysis Dashboard.lnk')," ^
  "  (Join-Path ([Environment]::GetFolderPath('Programs')) 'Uninstall Stock Analysis Dashboard.lnk')" ^
  ");" ^
  "foreach($path in $paths){if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path -Force}}"

start "" /min cmd /c "timeout /t 1 /nobreak >nul & rmdir /s /q ""%APP_DIR%"""
endlocal
