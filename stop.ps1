# Clade 鍋滄鏈嶅姟 - PowerShell 鐗堟湰
$Host.UI.RawUI.WindowTitle = "Clade - 鍋滄鏈嶅姟"

try {
    $OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Red
Write-Host "                  鍋滄 Clade 鏈嶅姟" -ForegroundColor Red
Write-Host "  ============================================================" -ForegroundColor Red
Write-Host ""

Write-Host "姝ｅ湪鍋滄鏈嶅姟..." -ForegroundColor Yellow

# 鍋滄 Node.js 杩涚▼锛堝墠绔級
Write-Host "  姝ｅ湪鍋滄鍓嶇..." -ForegroundColor Yellow
Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# 鍋滄 Python/uvicorn 杩涚▼锛堝悗绔級
Write-Host "  姝ｅ湪鍋滄鍚庣..." -ForegroundColor Yellow

# 閫氳繃绔彛鏌ユ壘骞剁粓姝㈣繘绋?$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
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
Write-Host "                  鎵€鏈夋湇鍔″凡鍋滄" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

Start-Sleep -Seconds 3
