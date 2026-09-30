@echo off
REM ============================================================
REM  NoLightToday — запуск для Windows (cmd.exe)
REM ============================================================
chcp 65001 >nul
setlocal

REM Переходим в корень проекта (на уровень выше scripts)
cd /d "%~dp0.."

REM Проверяем, есть ли виртуальное окружение
if not exist ".venv\Scripts\python.exe" (
    echo [i] Виртуальное окружение не найдено, создаю...
    python -m venv .venv
    if errorlevel 1 (
        echo [x] Не удалось создать .venv. Проверьте, что Python 3.10+ установлен и доступен в PATH.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -e ".[dev]"
)

REM UTF-8 для Python
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM Запуск
".venv\Scripts\python.exe" -m src
endlocal