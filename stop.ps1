# Clade 停止服务 - PowerShell 版本
$Host.UI.RawUI.WindowTitle = "Clade - 停止服务"

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Red
Write-Host "                  停止 Clade 服务" -ForegroundColor Red
Write-Host "  ============================================================" -ForegroundColor Red
Write-Host ""

Write-Host "正在停止服务..." -ForegroundColor Yellow

# 停止 Node.js 进程 (前端)
Write-Host "  正在停止前端..." -ForegroundColor Yellow
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 停止 Python/uvicorn 进程 (后端)
Write-Host "  正在停止后端..." -ForegroundColor Yellow

# 通过端口查找并终止进程
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($port8000) {
    foreach ($pid in $port8000) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
}

$port5173 = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($port5173) {
    foreach ($pid in $port5173) {
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "                  所有服务已停止" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

Start-Sleep -Seconds 3
