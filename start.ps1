# Clade 启动器 - PowerShell 版本
$Host.UI.RawUI.WindowTitle = "Clade 启动器"

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "                     Clade 启动器" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

# 获取脚本所在目录
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
Write-Host "  工作目录: $scriptDir" -ForegroundColor Gray
Write-Host ""

# 检查 Python
Write-Host "[1/6] 检查 Python..." -ForegroundColor Cyan
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "      [错误] 未找到 Python! 请安装 Python 3.11+" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}
$pythonVersion = & python --version 2>&1
Write-Host "      [完成] $pythonVersion" -ForegroundColor Green

# 检查 Node.js
Write-Host "[2/6] 检查 Node.js..." -ForegroundColor Cyan
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Host "      [错误] 未找到 Node.js! 请安装 Node.js 18+" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}
$nodeVersion = & node --version 2>&1
Write-Host "      [完成] Node.js $nodeVersion" -ForegroundColor Green

# 切换到项目目录
Set-Location $scriptDir

# 配置后端虚拟环境
Write-Host "[3/6] 配置后端环境..." -ForegroundColor Cyan
Set-Location backend
if (-not (Test-Path "venv")) {
    Write-Host "      正在创建虚拟环境..." -ForegroundColor Yellow
    & python -m venv venv
}

# 激活虚拟环境并安装依赖
& .\venv\Scripts\Activate.ps1
$fastapiCheck = & pip show fastapi 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "      正在安装后端依赖..." -ForegroundColor Yellow
    & pip install -e ".[dev]" -q
} else {
    Write-Host "      [完成] 后端依赖已就绪" -ForegroundColor Green
}

# 安装前端依赖
Write-Host "[4/6] 配置前端环境..." -ForegroundColor Cyan
Set-Location ..\frontend
if (-not (Test-Path "node_modules")) {
    Write-Host "      正在安装前端依赖..." -ForegroundColor Yellow
    & npm install --silent
} else {
    Write-Host "      [完成] 前端依赖已就绪" -ForegroundColor Green
}

# 返回项目根目录
Set-Location $scriptDir

Write-Host "[5/6] 启动服务..." -ForegroundColor Cyan
Write-Host ""
Write-Host "      正在启动后端 (端口 8000)..." -ForegroundColor Yellow

# 启动后端 (PowerShell 窗口)
$backendCmd = "chcp 65001 > `$null; Set-Location '$scriptDir\backend'; .\venv\Scripts\Activate.ps1; Write-Host 'Clade Backend' -ForegroundColor Green; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# 等待后端启动
Start-Sleep -Seconds 3

Write-Host "      正在启动前端 (端口 5173)..." -ForegroundColor Yellow

# 启动前端 (PowerShell 窗口)
$frontendCmd = "chcp 65001 > `$null; Set-Location '$scriptDir\frontend'; Write-Host 'Clade Frontend' -ForegroundColor Green; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

# 等待前端启动
Write-Host ""
Write-Host "[6/6] 等待服务启动..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

# 打开浏览器
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "                       启动完成!" -ForegroundColor Green
Write-Host ""
Write-Host "     Frontend: " -NoNewline; Write-Host "http://localhost:5173" -ForegroundColor Cyan
Write-Host "     Backend:  " -NoNewline; Write-Host "http://localhost:8000" -ForegroundColor Cyan
Write-Host "     API Docs: " -NoNewline; Write-Host "http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "     正在打开浏览器..." -ForegroundColor Yellow
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

Start-Process "http://localhost:5173"

Write-Host "按任意键关闭此窗口 (服务将继续运行)..." -ForegroundColor Gray
[void][System.Console]::ReadKey($true)
