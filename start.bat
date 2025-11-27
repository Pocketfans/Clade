@echo off
title Clade 启动器
chcp 65001 >nul 2>&1
cd /d "%~dp0"

:: 检查 PowerShell 是否可用
where powershell >nul 2>&1
if errorlevel 1 (
    echo.
    echo [错误] 未找到 PowerShell，无法启动!
    echo.
    pause
    exit /b 1
)

:: 运行 PowerShell 启动脚本
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0start.ps1"

:: 如果 PowerShell 执行失败，显示错误
if errorlevel 1 (
    echo.
    echo [错误] 启动失败，请检查错误信息
    echo.
    pause
)
