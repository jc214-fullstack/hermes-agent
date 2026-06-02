@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "DEFAULT_ROOT=%%~fI"
if "%HERMES_PROJECT_ROOT%"=="" (set "HERMES_PROJECT_ROOT=%DEFAULT_ROOT%")
if "%HERMES_HEALTH_URL%"=="" set "HERMES_HEALTH_URL=http://127.0.0.1:8787/health"
if "%HERMES_INIT_URL%"=="" set "HERMES_INIT_URL=http://127.0.0.1:8787/system/initialize"
if "%HERMES_TIMEOUT_SECONDS%"=="" set "HERMES_TIMEOUT_SECONDS=60"
if "%HERMES_PORT%"=="" set "HERMES_PORT=8787"
if "%HERMES_START_CMD%"=="" set "HERMES_START_CMD=hermes gateway start"

set "LOG_DIR=%HERMES_PROJECT_ROOT%\.hermes\logs"
set "RUN_DIR=%HERMES_PROJECT_ROOT%\.hermes\run"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"
set "LOG_FILE=%LOG_DIR%\gateway-up.log"
set "PID_FILE=%RUN_DIR%\gateway.pid"

set "STARTED=no"
set "INITIALIZED=skipped"
set "ERROR_MSG="

call :check_health
if "%HEALTHY%"=="yes" goto :maybe_init

echo [%DATE% %TIME%] gateway unhealthy, attempting start>>"%LOG_FILE%"
if not "%HERMES_GATEWAY_SERVICE%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Service -Name $env:HERMES_GATEWAY_SERVICE -ErrorAction Stop" >>"%LOG_FILE%" 2>&1
  if errorlevel 1 (
    set "ERROR_MSG=failed to start service %HERMES_GATEWAY_SERVICE%"
    goto :wait_for_health
  )
  set "STARTED=yes"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','cd /d ""'+$env:HERMES_PROJECT_ROOT+'"" && '+$env:HERMES_START_CMD+' >> ""'+$env:LOG_FILE+'"" 2>&1' -WindowStyle Hidden -PassThru; if($p){ Set-Content -Path $env:PID_FILE -Value $p.Id -Encoding ascii }" >>"%LOG_FILE%" 2>&1
  if errorlevel 1 (
    set "ERROR_MSG=failed to launch start command"
    goto :wait_for_health
  )
  set "STARTED=yes"
)

:wait_for_health
set /a elapsed=0
:wait_loop
call :check_health
if "%HEALTHY%"=="yes" goto :maybe_init
if %elapsed% GEQ %HERMES_TIMEOUT_SECONDS% goto :timeout
powershell -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1
set /a elapsed+=2
goto :wait_loop

:maybe_init
if "%HERMES_SKIP_INIT%"=="1" (
  set "INITIALIZED=skipped"
  goto :success
)
if "%HERMES_INIT_URL%"=="" (
  set "INITIALIZED=skipped"
  goto :success
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$resp = Invoke-WebRequest -Uri $env:HERMES_INIT_URL -Method Post -TimeoutSec 30 -UseBasicParsing -ErrorAction Stop; if(($resp.StatusCode -ge 200) -and ($resp.StatusCode -lt 300)){ exit 0 } else { exit 1 }" >>"%LOG_FILE%" 2>&1
if errorlevel 1 (
  set "INITIALIZED=failed"
  set "ERROR_MSG=initialize endpoint failed"
) else (
  set "INITIALIZED=yes"
)

:success
call :check_health
if "%HEALTHY%"=="yes" (
  echo command run: scripts\hermes-gateway-up.cmd
  echo gateway healthy: yes
  echo started: %STARTED%
  echo restarted: unknown
  echo initialized: %INITIALIZED%
  if not "%ERROR_MSG%"=="" echo errors: %ERROR_MSG%
  echo next action: none
  exit /b 0
)

goto :timeout

:timeout
echo command run: scripts\hermes-gateway-up.cmd
echo gateway healthy: no
echo started: %STARTED%
echo restarted: unknown
echo initialized: %INITIALIZED%
if "%ERROR_MSG%"=="" set "ERROR_MSG=health check timeout"
echo errors: %ERROR_MSG%
echo next action: inspect %LOG_FILE%
exit /b 2

:check_health
set "HEALTHY=no"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; try { $r=Invoke-WebRequest -Uri $env:HERMES_HEALTH_URL -Method Get -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop; if(($r.StatusCode -ge 200) -and ($r.StatusCode -lt 300)){ $ok=$true } } catch {}; if($ok){ exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 set "HEALTHY=yes"
exit /b 0
