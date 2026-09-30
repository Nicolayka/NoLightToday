#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv .venv
    .venv/bin/pip install -e ".[dev]"
fi

exec .venv/bin/python -m src