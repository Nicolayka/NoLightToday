@echo off
REM ============================================================
REM  NoLightToday - установка окружения (Windows cmd.exe)
REM ============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo.
echo [i] Проект: %CD%
echo.

REM Проверяем Python
where python >nul 2>nul
if errorlevel 1 (
    echo [x] Python не найден в PATH.
    echo     Установите Python 3.10+ с https://www.python.org/downloads/windows/
    echo     и отметьте галочку "Add python.exe to PATH" при установке.
    pause
    exit /b 1
)

REM Создаём виртуальное окружение
if not exist ".venv\Scripts\python.exe" (
    echo [i] Создаю виртуальное окружение .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [x] Не удалось создать .venv
        pause
        exit /b 1
    )
)

REM Обновляем pip и ставим зависимости
echo [i] Обновляю pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo [i] Устанавливаю зависимости проекта ...
".venv\Scripts\python.exe" -m pip install -e ".[dev]"

if errorlevel 1 (
    echo [x] Установка завершилась с ошибкой.
    pause
    exit /b 1
)

echo.
echo [ok] Установка завершена.
echo      Запуск:  scripts\run.bat
echo.
pause
endlocal