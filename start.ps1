# Clade 鍚姩鍣?- PowerShell 鐗堟湰
$Host.UI.RawUI.WindowTitle = "Clade 鍚姩鍣?

try {
    $OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "                     Clade 鍚姩鍣? -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

# 鑾峰彇鑴氭湰鎵€鍦ㄧ洰褰?$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $scriptDir) { $scriptDir = Get-Location }
Write-Host "  宸ヤ綔鐩綍: $scriptDir" -ForegroundColor Gray
Write-Host ""

# 妫€鏌?Python
Write-Host "[1/6] 妫€鏌?Python..." -ForegroundColor Cyan
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "      [閿欒] 鏈壘鍒?Python锛佽瀹夎 Python 3.11+" -ForegroundColor Red
    Read-Host "鎸夊洖杞﹂敭閫€鍑?
    exit 1
}
$pythonVersion = & python --version 2>&1
Write-Host "      [瀹屾垚] $pythonVersion" -ForegroundColor Green

# 妫€鏌?Node.js
Write-Host "[2/6] 妫€鏌?Node.js..." -ForegroundColor Cyan
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Host "      [閿欒] 鏈壘鍒?Node.js锛佽瀹夎 Node.js 18+" -ForegroundColor Red
    Read-Host "鎸夊洖杞﹂敭閫€鍑?
    exit 1
}
$nodeVersion = & node --version 2>&1
Write-Host "      [瀹屾垚] Node.js $nodeVersion" -ForegroundColor Green

# 鍒囨崲鍒伴」鐩洰褰?Set-Location $scriptDir

# 閰嶇疆鍚庣铏氭嫙鐜
Write-Host "[3/6] 閰嶇疆鍚庣鐜..." -ForegroundColor Cyan
Set-Location backend
if (-not (Test-Path "venv")) {
    Write-Host "      姝ｅ湪鍒涘缓铏氭嫙鐜..." -ForegroundColor Yellow
    & python -m venv venv
}

# 婵€娲昏櫄鎷熺幆澧冨苟瀹夎渚濊禆
& .\venv\Scripts\Activate.ps1
$fastapiCheck = & pip show fastapi 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "      姝ｅ湪瀹夎鍚庣渚濊禆..." -ForegroundColor Yellow
    & pip install -e ".[dev]" -q
} else {
    Write-Host "      [瀹屾垚] 鍚庣渚濊禆宸插氨缁? -ForegroundColor Green
}

# 瀹夎鍓嶇渚濊禆
Write-Host "[4/6] 閰嶇疆鍓嶇鐜..." -ForegroundColor Cyan
Set-Location ..\frontend
if (-not (Test-Path "node_modules")) {
    Write-Host "      姝ｅ湪瀹夎鍓嶇渚濊禆..." -ForegroundColor Yellow
    & npm install --silent
} else {
    Write-Host "      [瀹屾垚] 鍓嶇渚濊禆宸插氨缁? -ForegroundColor Green
}

# 杩斿洖椤圭洰鏍圭洰褰?Set-Location $scriptDir

Write-Host "[5/6] 鍚姩鏈嶅姟..." -ForegroundColor Cyan
Write-Host ""
Write-Host "      姝ｅ湪鍚姩鍚庣 (绔彛 8000)..." -ForegroundColor Yellow

# 鍚姩鍚庣 (PowerShell 绐楀彛)
$backendCmd = "Set-Location '$scriptDir\backend'; .\venv\Scripts\Activate.ps1; Write-Host 'Clade Backend' -ForegroundColor Green; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# 绛夊緟鍚庣鍚姩
Start-Sleep -Seconds 3

Write-Host "      姝ｅ湪鍚姩鍓嶇 (绔彛 5173)..." -ForegroundColor Yellow

# 鍚姩鍓嶇 (PowerShell 绐楀彛)
$frontendCmd = "Set-Location '$scriptDir\frontend'; Write-Host 'Clade Frontend' -ForegroundColor Green; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

# 绛夊緟鍓嶇鍚姩
Write-Host ""
Write-Host "[6/6] 绛夊緟鏈嶅姟鍚姩..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

# 鎵撳紑娴忚鍣?Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "                       鍚姩瀹屾垚锛? -ForegroundColor Green
Write-Host ""
Write-Host "     Frontend: " -NoNewline; Write-Host "http://localhost:5173" -ForegroundColor Cyan
Write-Host "     Backend:  " -NoNewline; Write-Host "http://localhost:8000" -ForegroundColor Cyan
Write-Host "     API Docs: " -NoNewline; Write-Host "http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "     姝ｅ湪鎵撳紑娴忚鍣?.." -ForegroundColor Yellow
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

Start-Process "http://localhost:5173"

Write-Host "鎸変换鎰忛敭鍏抽棴姝ょ獥鍙?.." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
