# Clade Launcher with Chinese UI
$Host.UI.RawUI.WindowTitle = "Clade"

# Load Chinese language file
$langFile = Join-Path $PSScriptRoot "lang_zh.json"
if (Test-Path $langFile) {
    $lang = Get-Content $langFile -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
    # Fallback to English
    $lang = @{
        title = "Clade Launcher"
        directory = "Directory"
        step1 = "Checking Python..."
        step2 = "Checking Node.js..."
        step3 = "Setting up backend..."
        step4 = "Setting up frontend..."
        step5 = "Starting services..."
        step6 = "Waiting..."
        ok = "OK"
        error = "ERROR"
        warn = "WARN"
        install = "INSTALL"
        create = "CREATE"
        start = "START"
        pythonNotFound = "Python not found!"
        nodeNotFound = "Node.js not found!"
        download = "Download"
        pressEnter = "Press Enter to exit"
        creatingVenv = "Creating venv..."
        venvFailed = "Failed!"
        installingBackend = "Installing backend..."
        backendReady = "Backend ready"
        installingFrontend = "Installing frontend..."
        frontendReady = "Frontend ready"
        clearingPorts = "Clearing ports..."
        startingBackend = "Starting backend (8000)..."
        startingFrontend = "Starting frontend (5173)..."
        complete = "COMPLETE!"
        game = "Game"
        backend = "Backend"
        docs = "API Docs"
        tip1 = "Configure AI in Settings"
        tip2 = "Run stop.bat to stop"
        pressAnyKey = "Press any key to close..."
    }
}

$cTitle = "Cyan"
$cSuccess = "Green"
$cWarning = "Yellow"
$cError = "Red"
$cInfo = "Gray"

function Write-Step {
    param([string]$Step, [string]$Message)
    Write-Host "[$Step] " -ForegroundColor $cTitle -NoNewline
    Write-Host $Message
}

function Write-Status {
    param([string]$Status, [string]$Message, [string]$Color = "Green")
    Write-Host "      [$Status] " -ForegroundColor $Color -NoNewline
    Write-Host $Message
}

# 查找最佳 Python 版本（优先使用 3.11/3.12 以兼容 faiss-cpu）
function Find-BestPython {
    # 优先级列表：3.12 > 3.11 > 3.10 > 3.13（3.13+ 很多包还不支持）
    $preferredVersions = @("3.12", "3.11", "3.10", "3.13")
    
    # 检查 py launcher（Windows Python Launcher）
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        foreach ($ver in $preferredVersions) {
            $testOutput = & py "-$ver" --version 2>&1
            if ($LASTEXITCODE -eq 0 -and $testOutput -match "Python $ver") {
                return @{
                    Command = "py -$ver"
                    Version = $testOutput.ToString().Trim()
                    Minor = [int]$ver.Split('.')[1]
                }
            }
        }
    }
    
    # 如果 py launcher 没找到合适版本，尝试直接查找 python 命令
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $verOutput = & python --version 2>&1
        if ($verOutput -match 'Python 3\.(\d+)') {
            $minor = [int]$Matches[1]
            # 只接受 3.10-3.13
            if ($minor -ge 10 -and $minor -le 13) {
                return @{
                    Command = "python"
                    Version = $verOutput.ToString().Trim()
                    Minor = $minor
                }
            }
        }
    }
    
    return $null
}

Clear-Host
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor $cTitle
Write-Host "              $($lang.title)                                 " -ForegroundColor $cTitle
Write-Host "  ============================================================" -ForegroundColor $cTitle
Write-Host ""

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Write-Host "  $($lang.directory): $scriptDir" -ForegroundColor $cInfo
Write-Host ""

# ==================== Step 1: Check Python ====================
Write-Step "1/6" $lang.step1

$bestPython = Find-BestPython

if (-not $bestPython) {
    Write-Status $lang.error "Python 3.10-3.12 not found!" $cError
    Write-Host "  $($lang.download): https://www.python.org/downloads/" -ForegroundColor $cInfo
    Write-Host "  Recommended: Python 3.12.x" -ForegroundColor $cWarning
    Read-Host $lang.pressEnter
    exit 1
}

$pythonCommand = $bestPython.Command
$pythonVersion = $bestPython.Version

# 检查默认 python 版本并显示信息
$defaultCheck = & python --version 2>&1
if ($defaultCheck -match 'Python 3\.(\d+)' -and [int]$Matches[1] -gt 13) {
    Write-Status $lang.warn "System default: $defaultCheck" $cWarning
    Write-Status $lang.ok "Using: $pythonVersion (compatible)" $cSuccess
} else {
    Write-Status $lang.ok $pythonVersion $cSuccess
}

# ==================== Step 2: Check Node.js ====================
Write-Step "2/6" $lang.step2
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Write-Status $lang.error $lang.nodeNotFound $cError
    Write-Host "  $($lang.download): https://nodejs.org/" -ForegroundColor $cInfo
    Read-Host $lang.pressEnter
    exit 1
}
$nodeVersion = (& node --version 2>&1).ToString()
Write-Status $lang.ok "Node.js $nodeVersion" $cSuccess

# ==================== Step 3: Setup Backend ====================
Write-Step "3/6" $lang.step3
Set-Location "$scriptDir\backend"

# 检查 venv 是否存在且版本兼容
$needRecreateVenv = $false
$venvExists = Test-Path "venv\Scripts\python.exe"

if ($venvExists) {
    $venvPyVer = & .\venv\Scripts\python.exe --version 2>&1
    if ($venvPyVer -match 'Python 3\.(\d+)') {
        $venvMinor = [int]$Matches[1]
        # 如果 venv Python 版本不在兼容范围内，重建
        if ($venvMinor -lt 10 -or $venvMinor -gt 13) {
            Write-Status $lang.warn "Venv Python $venvMinor incompatible, rebuilding..." $cWarning
            $needRecreateVenv = $true
        }
        # 如果找到了更好的版本（3.12优于3.14等），也重建
        elseif ($venvMinor -gt 12 -and $bestPython.Minor -le 12) {
            Write-Status $lang.warn "Switching to $pythonVersion for better compatibility..." $cWarning
            $needRecreateVenv = $true
        }
    }
}

if ($needRecreateVenv -and $venvExists) {
    Remove-Item -Recurse -Force "venv" -ErrorAction SilentlyContinue
    $venvExists = $false
}

# 创建虚拟环境
if (-not $venvExists) {
    Write-Status $lang.create "$($lang.creatingVenv) ($pythonVersion)" $cWarning
    
    if ($pythonCommand -like "py *") {
        $pyArgs = $pythonCommand.Substring(3).Trim()
        & py $pyArgs -m venv venv
    } else {
        & $pythonCommand -m venv venv
    }
    
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "venv\Scripts\python.exe")) {
        Write-Status $lang.error $lang.venvFailed $cError
        Read-Host $lang.pressEnter
        exit 1
    }
}

# 激活虚拟环境
& .\venv\Scripts\Activate.ps1

# 检查依赖是否完整安装（检查关键包）
$needInstallBackend = $false
$packagesToCheck = @("fastapi", "uvicorn", "sqlmodel", "numpy", "scipy")

foreach ($pkg in $packagesToCheck) {
    $check = & pip show $pkg 2>&1
    if ($LASTEXITCODE -ne 0) {
        $needInstallBackend = $true
        break
    }
}

if ($needInstallBackend) {
    Write-Status $lang.install $lang.installingBackend $cWarning
    # 先升级 pip 以避免兼容性问题
    & python -m pip install --upgrade pip --quiet --disable-pip-version-check 2>&1 | Out-Null
    # 安装所有依赖
    & pip install -e ".[dev]" --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Write-Status $lang.error "Backend install failed!" $cError
        Write-Host "  Try manually: cd backend && pip install -e .[dev]" -ForegroundColor $cInfo
        Read-Host $lang.pressEnter
        exit 1
    }
}
Write-Status $lang.ok $lang.backendReady $cSuccess

# ==================== Step 4: Setup Frontend ====================
Write-Step "4/6" $lang.step4
Set-Location "$scriptDir\frontend"

# 更可靠的前端依赖检查
$needInstallFrontend = $false

if (-not (Test-Path "node_modules")) {
    $needInstallFrontend = $true
} elseif (-not (Test-Path "node_modules\.bin\vite.cmd")) {
    $needInstallFrontend = $true
} elseif (-not (Test-Path "node_modules\react-markdown")) {
    # 检查关键依赖是否存在
    $needInstallFrontend = $true
} else {
    # 检查 package-lock.json 是否比 node_modules 新（说明有更新）
    if (Test-Path "package-lock.json") {
        $lockTime = (Get-Item "package-lock.json").LastWriteTime
        $modulesTime = (Get-Item "node_modules").LastWriteTime
        if ($lockTime -gt $modulesTime) {
            $needInstallFrontend = $true
        }
    }
}

if ($needInstallFrontend) {
    Write-Status $lang.install $lang.installingFrontend $cWarning
    # 清理可能损坏的 node_modules
    if (Test-Path "node_modules") {
        Remove-Item -Recurse -Force "node_modules" -ErrorAction SilentlyContinue
    }
    & npm install --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) {
        Write-Status $lang.error "Frontend install failed!" $cError
        Write-Host "  Try manually: cd frontend && npm install" -ForegroundColor $cInfo
        Read-Host $lang.pressEnter
        exit 1
    }
}
Write-Status $lang.ok $lang.frontendReady $cSuccess

# ==================== Step 5: Start Services ====================
Write-Step "5/6" $lang.step5
Set-Location $scriptDir

# 清理占用的端口
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$port5173 = Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue
if ($port8000 -or $port5173) {
    Write-Status $lang.warn $lang.clearingPorts $cWarning
    if ($port8000) { 
        $port8000 | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { 
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue 
        } 
    }
    if ($port5173) { 
        $port5173 | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { 
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue 
        } 
    }
    Start-Sleep -Seconds 2
}

Write-Host ""
Write-Status $lang.start $lang.startingBackend $cWarning

$be = "Set-Location '$scriptDir\backend'; & .\venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $be

Start-Sleep -Seconds 4

Write-Status $lang.start $lang.startingFrontend $cWarning

$fe = "Set-Location '$scriptDir\frontend'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $fe

# ==================== Step 6: Complete ====================
Write-Step "6/6" $lang.step6
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor $cSuccess
Write-Host "                      $($lang.complete)                      " -ForegroundColor $cSuccess
Write-Host "  ============================================================" -ForegroundColor $cSuccess
Write-Host ""
Write-Host "     $($lang.game):     http://localhost:5173" -ForegroundColor Cyan
Write-Host "     $($lang.backend):  http://localhost:8000" -ForegroundColor Cyan
Write-Host "     $($lang.docs):     http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "  ------------------------------------------------------------" -ForegroundColor $cInfo
Write-Host "     $($lang.tip1)" -ForegroundColor $cInfo
Write-Host "     $($lang.tip2)" -ForegroundColor $cInfo
Write-Host "  ------------------------------------------------------------" -ForegroundColor $cInfo
Write-Host ""

Start-Process "http://localhost:5173"

Write-Host "  $($lang.pressAnyKey)" -ForegroundColor $cInfo
[void][System.Console]::ReadKey($true)
