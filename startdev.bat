@echo off
title Hadha Development Environment

echo ======================================
echo Starting Hadha Development Environment
echo ======================================

REM ======================================
REM Backend
REM ======================================
echo Starting Backend...
start "Hadha Backend" cmd /k "cd /d F:\Work\Hadha.co\Project\Backend && call hadha\Scripts\activate.bat && uvicorn app.main:app --reload"

timeout /t 3 >nul

REM ======================================
REM Storefront
REM ======================================
echo Starting Storefront...
start "Hadha Storefront" cmd /k "cd /d F:\Work\Hadha.co\Project\Frontend_whole && npm run dev:storefront"

timeout /t 2 >nul

REM ======================================
REM Admin
REM ======================================
echo Starting Admin...
start "Hadha Admin" cmd /k "cd /d F:\Work\Hadha.co\Project\Frontend_whole && npm run dev:admin"

timeout /t 2 >nul

echo.
echo ======================================
echo All services started successfully.
echo.
echo Backend   : http://127.0.0.1:8000
echo Storefront: http://localhost:8080
echo Admin     : http://localhost:8081
echo ======================================
echo First-time compile can take up to ~30s, waiting before opening tabs...

timeout /t 20 >nul

start http://localhost:8080
start http://localhost:8081
start http://127.0.0.1:8000/docs

pause
