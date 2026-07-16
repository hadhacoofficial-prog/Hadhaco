@echo off
REM ============================================================
REM Hadha.co k6 Performance Test Runner
REM ============================================================
REM Usage:
REM   run-smoke.bat                    — Smoke tests (2 min)
REM   run-smoke.bat load               — Load tests (10 min)
REM   run-smoke.bat stress             — Stress tests (15 min)
REM   run-smoke.bat spike              — Spike tests (6 min)
REM   run-smoke.bat soak               — Soak tests (40 min)
REM   run-smoke.bat concurrency        — Inventory concurrency (5 min)
REM   run-smoke.bat all                — All scenarios sequentially
REM ============================================================

setlocal

set BASE_URL=%BASE_URL%
if "%BASE_URL%"=="" set BASE_URL=http://localhost:8000

set DEV_EMAIL=%DEV_EMAIL%
if "%DEV_EMAIL%"=="" set DEV_EMAIL=admin@hadha.co

set DEV_PASSWORD=%DEV_PASSWORD%
set CUSTOMER_EMAIL=%CUSTOMER_EMAIL%
set CUSTOMER_PASSWORD=%CUSTOMER_PASSWORD%

set SCENARIO=%1
if "%SCENARIO%"=="" set SCENARIO=smoke

set OUTPUT_DIR=k6\reports\output
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

echo ============================================================
echo  Hadha.co k6 Performance Test Suite
echo ============================================================
echo  Target:    %BASE_URL%
echo  Scenario:  %SCENARIO%
echo  Time:      %date% %time%
echo ============================================================

if "%SCENARIO%"=="smoke" goto :smoke
if "%SCENARIO%"=="load" goto :load
if "%SCENARIO%"=="stress" goto :stress
if "%SCENARIO%"=="spike" goto :spike
if "%SCENARIO%"=="soak" goto :soak
if "%SCENARIO%"=="concurrency" goto :concurrency
if "%SCENARIO%"=="all" goto :all
goto :help

:smoke
echo Running SMOKE tests...
k6 run smoke\full-suite.js --out json=%OUTPUT_DIR%\smoke-%date:~-4%%date:~4,2%%date:~7,2%.json --summary-export=%OUTPUT_DIR%\smoke-summary.json
goto :end

:load
echo Running LOAD tests...
k6 run load\full-journey.js --out json=%OUTPUT_DIR%\load-%date:~-4%%date:~4,2%%date:~7,2%.json --summary-export=%OUTPUT_DIR%\load-summary.json
goto :end

:stress
echo Running STRESS tests...
k6 run stress\full-suite.js --out json=%OUTPUT_DIR%\stress-%date:~-4%%date:~4,2%%date:~7,2%.json --summary-export=%OUTPUT_DIR%\stress-summary.json
goto :end

:spike
echo Running SPIKE tests...
k6 run spike\flash-sale.js --out json=%OUTPUT_DIR%\spike-%date:~-4%%date:~4,2%%date:~7,2%.json --summary-export=%OUTPUT_DIR%\spike-summary.json
goto :end

:soak
echo Running SOAK tests (40 minutes)...
k6 run soak\endurance.js --out json=%OUTPUT_DIR%\soak-%date:~-4%%date:~4,2%%date:~7,2%.json --summary-export=%OUTPUT_DIR%\soak-summary.json
goto :end

:concurrency
echo Running INVENTORY CONCURRENCY tests...
k6 run inventory\concurrency.js --out json=%OUTPUT_DIR%\concurrency-%date:~-4%%date:~4,2%%date:~7,2%.json --summary-export=%OUTPUT_DIR%\concurrency-summary.json
goto :end

:all
echo Running ALL scenarios sequentially...
echo.
echo [1/6] Smoke tests...
k6 run smoke\full-suite.js --out json=%OUTPUT_DIR%\smoke.json --summary-export=%OUTPUT_DIR%\smoke-summary.json
echo.
echo [2/6] Load tests...
k6 run load\full-journey.js --out json=%OUTPUT_DIR%\load.json --summary-export=%OUTPUT_DIR%\load-summary.json
echo.
echo [3/6] Stress tests...
k6 run stress\full-suite.js --out json=%OUTPUT_DIR%\stress.json --summary-export=%OUTPUT_DIR%\stress-summary.json
echo.
echo [4/6] Spike tests...
k6 run spike\flash-sale.js --out json=%OUTPUT_DIR%\spike.json --summary-export=%OUTPUT_DIR%\spike-summary.json
echo.
echo [5/6] Inventory concurrency...
k6 run inventory\concurrency.js --out json=%OUTPUT_DIR%\concurrency.json --summary-export=%OUTPUT_DIR%\concurrency-summary.json
echo.
echo [6/6] Done!
goto :end

:help
echo.
echo Usage: run-smoke.bat [scenario]
echo.
echo Scenarios:
echo   smoke         Quick validation (~2 min)
echo   load          Realistic user journey (~10 min)
echo   stress        Beyond-capacity test (~15 min)
echo   spike         Sudden traffic surge (~6 min)
echo   soak          Endurance test (~40 min)
echo   concurrency   Inventory race condition test (~5 min)
echo   all           All scenarios sequentially
echo.
echo Environment variables:
echo   BASE_URL         Backend URL (default: http://localhost:8000)
echo   DEV_EMAIL        Dev auth email
echo   DEV_PASSWORD     Dev auth password
echo   CUSTOMER_EMAIL   Customer auth email
echo   CUSTOMER_PASSWORD Customer auth password
goto :end

:end
echo.
echo ============================================================
echo  Test complete. Results in %OUTPUT_DIR%
echo ============================================================
endlocal
