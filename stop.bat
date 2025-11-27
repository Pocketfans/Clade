@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -Command "$content = [System.IO.File]::ReadAllText('%~dp0stop.ps1', [System.Text.Encoding]::UTF8); Invoke-Expression $content"
pause
