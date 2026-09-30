# ============================================================
#  NoLightToday — запуск для Windows (PowerShell)
# ============================================================
$ErrorActionPreference = "Stop"

# Кодировка консоли UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Корень проекта (на уровень выше scripts)
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Виртуальное окружение
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "[i] Виртуальное окружение не найдено, создаю..." -ForegroundColor Yellow
    python -m venv .venv
    & $py -m pip install --upgrade pip
    & $py -m pip install -e ".[dev]"
}

# UTF-8 для Python-процесса
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# Запуск
& $py -m src