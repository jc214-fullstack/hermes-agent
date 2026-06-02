@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "DEFAULT_ROOT=%%~fI"
if "%HERMES_PROJECT_ROOT%"=="" (set "HERMES_PROJECT_ROOT=%DEFAULT_ROOT%")
if "%HERMES_PORT%"=="" set "HERMES_PORT=8787"
if "%HERMES_ALLOW_PORT_KILL%"=="" set "HERMES_ALLOW_PORT_KILL=0"

set "RUN_DIR=%HERMES_PROJECT_ROOT%\.hermes\run"
set "PID_FILE=%RUN_DIR%\gateway.pid"

set "RESTARTED=no"
set "STOP_ERROR="

if not "%HERMES_GATEWAY_SERVICE%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Restart-Service -Name $env:HERMES_GATEWAY_SERVICE -Force -ErrorAction Stop" >nul 2>&1
  if errorlevel 1 (
    set "STOP_ERROR=failed to restart service %HERMES_GATEWAY_SERVICE%"
  ) else (
    set "RESTARTED=yes"
  )
) else if not "%HERMES_STOP_CMD%"=="" (
  cmd /c "cd /d "%HERMES_PROJECT_ROOT%" && %HERMES_STOP_CMD%" >nul 2>&1
  if errorlevel 1 (
    set "STOP_ERROR=stop command failed"
  ) else (
    set "RESTARTED=yes"
  )
) else if exist "%PID_FILE%" (
  set /p GATEWAY_PID=<"%PID_FILE%"
  if not "%GATEWAY_PID%"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id $env:GATEWAY_PID -Force -ErrorAction Stop; $kids=Get-CimInstance Win32_Process -Filter ('ParentProcessId=' + $env:GATEWAY_PID) -ErrorAction SilentlyContinue; if($kids){ $kids | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }" >nul 2>&1
    if errorlevel 1 (
      set "STOP_ERROR=failed to kill pid %GATEWAY_PID%"
    ) else (
      set "RESTARTED=yes"
    )
  )
) else if "%HERMES_ALLOW_PORT_KILL%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-NetTCPConnection -LocalPort ([int]$env:HERMES_PORT) -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if($p){ Stop-Process -Id $p -Force -ErrorAction Stop }" >nul 2>&1
  if errorlevel 1 (
    set "STOP_ERROR=failed to kill process on port %HERMES_PORT%"
  ) else (
    set "RESTARTED=yes"
  )
)

call "%SCRIPT_DIR%hermes-gateway-up.cmd"
set "UP_EXIT=%ERRORLEVEL%"

echo restarted: %RESTARTED%
if not "%STOP_ERROR%"=="" echo restart errors: %STOP_ERROR%

exit /b %UP_EXIT%
