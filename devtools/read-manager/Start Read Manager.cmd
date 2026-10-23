@echo off
setlocal
where pwsh.exe >nul 2>&1
if not errorlevel 1 (
  pwsh.exe -NoProfile -File "%~dp0Start-ReadManager.ps1"
) else (
  "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -File "%~dp0Start-ReadManager.ps1"
)
if errorlevel 1 pause
