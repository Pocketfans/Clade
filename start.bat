@echo off
setlocal enabledelayedexpansion
title Clade Launcher
color 0A

echo.
echo  ============================================================
echo                    Clade Launcher
echo  ============================================================
echo.

:: Check Python
echo [1/6] Checking Python...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo     [ERROR] Python not found! Please install Python 3.11+
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo     [OK] Python %PYTHON_VERSION%

:: Check Node.js
echo [2/6] Checking Node.js...
node --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo     [ERROR] Node.js not found! Please install Node.js 18+
    pause
    exit /b 1
)
for /f %%i in ('node --version') do set NODE_VERSION=%%i
echo     [OK] Node.js %NODE_VERSION%

:: Setup backend virtual environment
echo [3/6] Setting up backend...
cd backend
if not exist "venv" (
    echo     Creating virtual environment...
    python -m venv venv
)

:: Activate venv and install dependencies
call venv\Scripts\activate.bat
pip show fastapi >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo     Installing backend dependencies...
    pip install -e ".[dev]" -q
) else (
    echo     [OK] Backend dependencies ready
)

:: Install frontend dependencies
echo [4/6] Setting up frontend...
cd ..\frontend
if not exist "node_modules" (
    echo     Installing frontend dependencies...
    call npm install --silent
) else (
    echo     [OK] Frontend dependencies ready
)

:: Return to project root
cd ..

echo [5/6] Starting services...
echo.
echo     Starting backend (port 8000)...
start "Clade-Backend" cmd /k "cd backend && call venv\Scripts\activate.bat && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

:: Wait for backend
timeout /t 3 /nobreak >nul

echo     Starting frontend (port 5173)...
start "Clade-Frontend" cmd /k "cd frontend && npm run dev"

:: Wait for frontend
echo.
echo [6/6] Waiting for services to start...
timeout /t 5 /nobreak >nul

:: Open browser
echo.
echo  ============================================================
echo                      Launch Complete!
echo.
echo    Frontend: http://localhost:5173
echo    Backend:  http://localhost:8000
echo    API Docs: http://localhost:8000/docs
echo.
echo    Opening browser...
echo  ============================================================
echo.

start "" "http://localhost:5173"

echo Press any key to close this window (services will keep running)...
pause >nul
