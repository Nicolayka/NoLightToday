# ============================================================
#  NoLightToday - установка окружения (Windows PowerShell)
# ============================================================
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host ""
Write-Host "[i] Проект: $root" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[x] Python не найден в PATH." -ForegroundColor Red
    Write-Host "    Установите Python 3.10+ с https://www.python.org/downloads/windows/"
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[i] Создаю виртуальное окружение .venv ..." -ForegroundColor Yellow
    python -m venv .venv
}

$py = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "[i] Обновляю pip ..." -ForegroundColor Yellow
& $py -m pip install --upgrade pip

Write-Host "[i] Устанавливаю зависимости проекта ..." -ForegroundColor Yellow
& $py -m pip install -e ".[dev]"

Write-Host ""
Write-Host "[ok] Установка завершена." -ForegroundColor Green
Write-Host "     Запуск:  .\scripts\run.ps1" -ForegroundColor Cyan