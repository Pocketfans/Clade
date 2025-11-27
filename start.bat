@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Clade 启动器
color 0A

echo.
echo  ============================================================
echo                    Clade 启动器
echo  ============================================================
echo.

:: 检查 Python
echo [1/6] 检查 Python...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo     [错误] 未找到 Python！请安装 Python 3.11+
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo     [完成] Python %PYTHON_VERSION%

:: 检查 Node.js
echo [2/6] 检查 Node.js...
node --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo     [错误] 未找到 Node.js！请安装 Node.js 18+
    pause
    exit /b 1
)
for /f %%i in ('node --version') do set NODE_VERSION=%%i
echo     [完成] Node.js %NODE_VERSION%

:: 配置后端虚拟环境
echo [3/6] 配置后端环境...
cd backend
if not exist "venv" (
    echo     正在创建虚拟环境...
    python -m venv venv
)

:: 激活虚拟环境并安装依赖
call venv\Scripts\activate.bat
pip show fastapi >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo     正在安装后端依赖...
    pip install -e ".[dev]" -q
) else (
    echo     [完成] 后端依赖已就绪
)

:: 安装前端依赖
echo [4/6] 配置前端环境...
cd ..\frontend
if not exist "node_modules" (
    echo     正在安装前端依赖...
    call npm install --silent
) else (
    echo     [完成] 前端依赖已就绪
)

:: 返回项目根目录
cd ..

echo [5/6] 启动服务...
echo.
echo     正在启动后端 (端口 8000)...
start "Clade-Backend" cmd /k "cd backend && call venv\Scripts\activate.bat && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

:: 等待后端启动
timeout /t 3 /nobreak >nul

echo     正在启动前端 (端口 5173)...
start "Clade-Frontend" cmd /k "cd frontend && npm run dev"

:: 等待前端启动
echo.
echo [6/6] 等待服务启动...
timeout /t 5 /nobreak >nul

:: 打开浏览器
echo.
echo  ============================================================
echo                      启动完成！
echo.
echo    前端地址: http://localhost:5173
echo    后端地址: http://localhost:8000
echo    API文档:  http://localhost:8000/docs
echo.
echo    正在打开浏览器...
echo  ============================================================
echo.

start "" "http://localhost:5173"

echo 按任意键关闭此窗口（服务将继续运行）...
pause >nul
