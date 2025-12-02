# Clade Stop Services
$Host.UI.RawUI.WindowTitle = "Clade - Stop"

# ==================== 读取端口配置 ====================
# 默认端口
$BACKEND_PORT = 8022
$FRONTEND_PORT = 5188

# 从 .env 文件读取端口配置
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Encoding UTF8
    foreach ($line in $envContent) {
        if ($line -match '^\s*BACKEND_PORT\s*=\s*(\d+)') {
            $BACKEND_PORT = [int]$Matches[1]
        }
        if ($line -match '^\s*FRONTEND_PORT\s*=\s*(\d+)') {
            $FRONTEND_PORT = [int]$Matches[1]
        }
    }
}

# Load Chinese language
$langFile = Join-Path $PSScriptRoot "lang_zh.json"
if (Test-Path $langFile) {
    $lang = Get-Content $langFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $stopTitle = "停止 Clade 服务"
    $stoppingBackend = "停止后端服务 (端口 $BACKEND_PORT)..."
    $stoppingFrontend = "停止前端服务 (端口 $FRONTEND_PORT)..."
    $cleanup = "关闭相关窗口..."
    $stopped = "已停止"
    $notRunning = "未在运行"
    $allStopped = "所有服务已停止"
    $stoppingProcess = "停止进程"
    $closingWindow = "关闭窗口"
} else {
    $stopTitle = "Stopping Clade Services"
    $stoppingBackend = "Stopping backend (port $BACKEND_PORT)..."
    $stoppingFrontend = "Stopping frontend (port $FRONTEND_PORT)..."
    $cleanup = "Closing windows..."
    $stopped = "Stopped"
    $notRunning = "Not running"
    $allStopped = "All Services Stopped"
    $stoppingProcess = "Stopping"
    $closingWindow = "Closing"
}

Clear-Host
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Red
Write-Host "                    $stopTitle                               " -ForegroundColor Red
Write-Host "  ============================================================" -ForegroundColor Red
Write-Host ""

Write-Host "  [1/2] $stoppingBackend" -ForegroundColor Yellow
$portBackend = Get-NetTCPConnection -LocalPort $BACKEND_PORT -ErrorAction SilentlyContinue
if ($portBackend) {
    $portBackend | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        $proc = Get-Process -Id $_ -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "        ${stoppingProcess}: $($proc.ProcessName) (PID: $_)" -ForegroundColor Gray
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "        [OK] $stopped" -ForegroundColor Green
} else {
    Write-Host "        [INFO] $notRunning" -ForegroundColor Gray
}

Write-Host ""
Write-Host "  [2/2] $stoppingFrontend" -ForegroundColor Yellow
$portFrontend = Get-NetTCPConnection -LocalPort $FRONTEND_PORT -ErrorAction SilentlyContinue
if ($portFrontend) {
    $portFrontend | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        $proc = Get-Process -Id $_ -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "        ${stoppingProcess}: $($proc.ProcessName) (PID: $_)" -ForegroundColor Gray
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "        [OK] $stopped" -ForegroundColor Green
} else {
    Write-Host "        [INFO] $notRunning" -ForegroundColor Gray
}

Write-Host ""
Write-Host "  [3/3] $cleanup" -ForegroundColor Yellow
Get-Process powershell -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -like "*Clade*" -and $_.Id -ne $PID
} | ForEach-Object {
    Write-Host "        ${closingWindow}: $($_.MainWindowTitle)" -ForegroundColor Gray
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "                    $allStopped                              " -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

Start-Sleep -Seconds 2
