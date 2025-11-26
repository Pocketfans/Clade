@echo off
title Clade - Stop Services
color 0C

echo.
echo  ============================================================
echo               Stop Clade Services
echo  ============================================================
echo.

echo Stopping services...

:: Stop Node.js processes (frontend)
echo   Stopping frontend...
taskkill /F /IM node.exe >nul 2>&1

:: Stop Python/uvicorn processes (backend)
echo   Stopping backend...
taskkill /F /FI "WINDOWTITLE eq Clade-Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Clade-Frontend*" >nul 2>&1

:: Find and kill processes by port
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo  ============================================================
echo               All services stopped
echo  ============================================================
echo.

timeout /t 3 >nul
