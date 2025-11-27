# Clade Launcher - PowerShell
$Host.UI.RawUI.WindowTitle = "Clade Launcher"

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "                     Clade Launcher" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

# Get script directory
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $scriptDir) { $scriptDir = Get-Location }
Write-Host "  Working Directory: $scriptDir" -ForegroundColor Gray
Write-Host ""

# Check Python
Write-Host "[1/6] Checking Python..." -ForegroundColor Cyan
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "      [ERROR] Python not found! Please install Python 3.11+" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
$pythonVersion = & python --version 2>&1
Write-Host "      [OK] $pythonVersion" -ForegroundColor Green

# Check Node.js
Write-Host "[2/6] Checking Node.js..." -ForegroundColor Cyan
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Host "      [ERROR] Node.js not found! Please install Node.js 18+" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
$nodeVersion = & node --version 2>&1
Write-Host "      [OK] Node.js $nodeVersion" -ForegroundColor Green

# Switch to project directory
Set-Location $scriptDir

# Setup backend virtual environment
Write-Host "[3/6] Setting up backend..." -ForegroundColor Cyan
Set-Location backend
if (-not (Test-Path "venv")) {
    Write-Host "      Creating virtual environment..." -ForegroundColor Yellow
    & python -m venv venv
}

# Activate venv and install dependencies
& .\venv\Scripts\Activate.ps1
$fastapiCheck = & pip show fastapi 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Installing backend dependencies..." -ForegroundColor Yellow
    & pip install -e ".[dev]" -q
} else {
    Write-Host "      [OK] Backend dependencies ready" -ForegroundColor Green
}

# Install frontend dependencies
Write-Host "[4/6] Setting up frontend..." -ForegroundColor Cyan
Set-Location ..\frontend
if (-not (Test-Path "node_modules")) {
    Write-Host "      Installing frontend dependencies..." -ForegroundColor Yellow
    & npm install --silent
} else {
    Write-Host "      [OK] Frontend dependencies ready" -ForegroundColor Green
}

# Return to project root
Set-Location $scriptDir

Write-Host "[5/6] Starting services..." -ForegroundColor Cyan
Write-Host ""
Write-Host "      Starting backend (port 8000)..." -ForegroundColor Yellow

# Start backend (PowerShell window)
$backendCmd = "Set-Location '$scriptDir\backend'; .\venv\Scripts\Activate.ps1; Write-Host 'Clade Backend' -ForegroundColor Green; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# Wait for backend
Start-Sleep -Seconds 3

Write-Host "      Starting frontend (port 5173)..." -ForegroundColor Yellow

# Start frontend (PowerShell window)
$frontendCmd = "Set-Location '$scriptDir\frontend'; Write-Host 'Clade Frontend' -ForegroundColor Green; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

# Wait for frontend
Write-Host ""
Write-Host "[6/6] Waiting for services..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

# Open browser
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "                     Launch Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "     Frontend: " -NoNewline; Write-Host "http://localhost:5173" -ForegroundColor Cyan
Write-Host "     Backend:  " -NoNewline; Write-Host "http://localhost:8000" -ForegroundColor Cyan
Write-Host "     API Docs: " -NoNewline; Write-Host "http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "     Opening browser..." -ForegroundColor Yellow
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""

Start-Process "http://localhost:5173"

Write-Host "Press any key to close this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')