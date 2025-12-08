@echo off
title Clade Launcher
chcp 65001 >nul 2>&1
cd /d "%~dp0"

:: Run PowerShell script with UTF-8 encoding
powershell -ExecutionPolicy Bypass -NoProfile -File ".\start.ps1"

if errorlevel 1 (
    echo.
    echo [Error] Startup failed
    echo.
)
pause
