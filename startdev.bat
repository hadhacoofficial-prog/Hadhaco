@echo off
title Hadha Development

echo Starting Backend...

start "Backend" cmd /k "cd /d F:\Work\Hadha.co\Project\Backend && call hadha\Scripts\activate.bat && uvicorn app.main:app --reload"

timeout /t 2 >nul

echo Starting Frontend...

start "Frontend" cmd /k "cd /d F:\Work\Hadha.co\Project\Frontend && npm run dev"

pause