@echo off
title Clade - 停止服务
chcp 65001 >nul 2>&1
cd /d "%~dp0"

:: 运行 PowerShell 停止脚本
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0stop.ps1"

pause
