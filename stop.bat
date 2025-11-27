@echo off
chcp 65001 >nul
title Clade - 停止服务
color 0C

echo.
echo  ============================================================
echo               停止 Clade 服务
echo  ============================================================
echo.

echo 正在停止服务...

:: 停止 Node.js 进程（前端）
echo   正在停止前端...
taskkill /F /IM node.exe >nul 2>&1

:: 停止 Python/uvicorn 进程（后端）
echo   正在停止后端...
taskkill /F /FI "WINDOWTITLE eq Clade-Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Clade-Frontend*" >nul 2>&1

:: 通过端口查找并终止进程
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo  ============================================================
echo               所有服务已停止
echo  ============================================================
echo.

timeout /t 3 >nul
