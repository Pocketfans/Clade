# Clade Stop Services - PowerShell
$Host.UI.RawUI.WindowTitle = "Clade - Stop Services"

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Red
Write-Host "                  Stop Clade Services" -ForegroundColor Red
Write-Host "  ============================================================" -ForegroundColor Red
Write-Host ""

Write-Host "Stopping services..." -ForegroundColor Yellow

# Stop Node.js processes (frontend)
Write-Host "  Stopping frontend..." -ForegroundColor Yellow
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Stop Python/uvicorn processes (backend)
Write-Host "  Stopping backend..." -ForegroundColor Yellow

# Find and kill processes by port
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
Write-Host "                  All services stopped" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

Start-Sleep -Seconds 3