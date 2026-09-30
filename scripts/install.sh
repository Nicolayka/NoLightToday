#!/usr/bin/env bash
#
# NoLightToday — установка на Debian/Ubuntu как systemd-служба.
#
# Использование (от root):
#     sudo bash scripts/install.sh
#     sudo -E PYTHON_BIN=python3.11 bash scripts/install.sh
#
# Идемпотентно: можно запускать повторно после git pull.
#
set -euo pipefail

APP_NAME="nolighttoday"
APP_USER="nolighttoday"
APP_DIR="/opt/${APP_NAME}"
DATA_DIR="${APP_DIR}/data"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"


# ---------- цвета ----------
if [ -t 1 ]; then
    C_OK="\033[0;32m"; C_WARN="\033[0;33m"; C_ERR="\033[0;31m"; C_OFF="\033[0m"
else
    C_OK=""; C_WARN=""; C_ERR=""; C_OFF=""
fi
log()  { echo -e "${C_OK}[+]${C_OFF} $*"; }
warn() { echo -e "${C_WARN}[!]${C_OFF} $*"; }
err()  { echo -e "${C_ERR}[x]${C_OFF} $*" >&2; }


# ---------- проверки ----------
if [ "$(id -u)" -ne 0 ]; then
    err "Скрипт нужно запускать от root: sudo bash scripts/install.sh"
    exit 1
fi

if [ ! -f "${SRC_DIR}/pyproject.toml" ]; then
    err "Не найден pyproject.toml в ${SRC_DIR}. Запускайте из корня репозитория."
    exit 1
fi


# =========================================================
#           ВЫБОР PYTHON
# =========================================================
#
# Проект зависит от aiohttp, pydantic-core и других пакетов с C/Rust
# расширениями. Для Python 3.11/3.12 есть готовые бинарные wheels,
# для 3.13/3.14 их пока нет — pip пытается собирать из исходников
# и падает. Поэтому требуем 3.11 или 3.12.

SUPPORTED_MINORS=("3.11" "3.12")

_is_supported() {
    local ver="$1"
    for m in "${SUPPORTED_MINORS[@]}"; do
        [ "${ver}" = "${m}" ] && return 0
    done
    return 1
}

_get_minor() {
    "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null
}


# 1. Если PYTHON_BIN задан снаружи — уважаем выбор
if [ -n "${PYTHON_BIN:-}" ] && command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    PY_VER="$(_get_minor "${PYTHON_BIN}")"
    if ! _is_supported "${PY_VER}"; then
        err "Указанный PYTHON_BIN=${PYTHON_BIN} имеет версию ${PY_VER}."
        err "Поддерживаются только: ${SUPPORTED_MINORS[*]}"
        exit 1
    fi
    log "Использую Python из PYTHON_BIN: ${PYTHON_BIN} (${PY_VER})"

else
    # 2. Ищем подходящий Python сами
    PYTHON_BIN=""
    for candidate in python3.12 python3.11; do
        if command -v "${candidate}" >/dev/null 2>&1; then
            ver="$(_get_minor "${candidate}")"
            if _is_supported "${ver}"; then
                PYTHON_BIN="${candidate}"
                log "Найден подходящий Python: ${PYTHON_BIN} (${ver})"
                break
            fi
        fi
    done

    # 3. Ничего не нашли — ставим python3.11 из apt
    if [ -z "${PYTHON_BIN}" ]; then
        warn "Подходящий Python (3.11/3.12) не найден. Пробую поставить python3.11..."

        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            python3.11 python3.11-venv python3.11-dev \
        || {
            err "Не удалось установить python3.11."
            err "Проверьте apt (возможно, сломан из-за сторонних репозиториев):"
            err "    apt --fix-broken install"
            err "или установите вручную:"
            err "    apt install python3.11 python3.11-venv python3.11-dev"
            exit 1
        }

        if command -v python3.11 >/dev/null 2>&1; then
            PYTHON_BIN="python3.11"
            log "Установлен и выбран ${PYTHON_BIN}"
        else
            err "python3.11 не появился после установки. Разберитесь с apt."
            exit 1
        fi
    fi
fi

PY_VERSION="$(_get_minor "${PYTHON_BIN}")"
log "Итоговый Python: ${PYTHON_BIN} (${PY_VERSION})"


# ---------- системные пакеты ----------
log "Проверяю системные пакеты..."

# Проверяем, что venv-модуль для выбранного Python доступен
if ! "${PYTHON_BIN}" -c "import venv" >/dev/null 2>&1; then
    log "Ставлю ${PYTHON_BIN}-venv..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${PYTHON_BIN}-venv" || {
        err "Не удалось поставить ${PYTHON_BIN}-venv."
        err "Проверьте: apt --fix-broken install"
        exit 1
    }
fi

# ca-certificates нужен для SSL к сайту Россети и к Telegram
for pkg in ca-certificates; do
    if ! dpkg -s "${pkg}" >/dev/null 2>&1; then
        log "Ставлю ${pkg}..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkg}" || {
            err "Не удалось поставить ${pkg}."
            exit 1
        }
    fi
done

log "Все необходимые пакеты на месте."


# ---------- пользователь ----------
if id -u "${APP_USER}" >/dev/null 2>&1; then
    log "Пользователь ${APP_USER} уже существует"
else
    log "Создаю системного пользователя ${APP_USER}..."
    useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi


# ---------- копирование проекта ----------
log "Копирую проект в ${APP_DIR}..."
mkdir -p "${APP_DIR}"

# Чистим каталог, оставляя .venv, data, logs
find "${APP_DIR}" -mindepth 1 -maxdepth 1 \
    ! -name '.venv' ! -name 'data' ! -name 'logs' -exec rm -rf {} +

# Копируем через tar — встроен в любую систему, rsync не нужен
tar \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='data/*.db' \
    --exclude='data/*.db-shm' \
    --exclude='data/*.db-wal' \
    --exclude='logs' \
    -cf - -C "${SRC_DIR}" . | tar -xf - -C "${APP_DIR}"

mkdir -p "${DATA_DIR}" "${APP_DIR}/logs"


# ---------- venv ----------
# Если venv уже существует, но от другой версии Python — пересоздаём
if [ -x "${APP_DIR}/.venv/bin/python" ]; then
    VENV_VER="$(_get_minor "${APP_DIR}/.venv/bin/python")"
    if [ "${VENV_VER}" != "${PY_VERSION}" ]; then
        warn "Существующий venv использует Python ${VENV_VER}, нужен ${PY_VERSION}."
        warn "Пересоздаю venv..."
        rm -rf "${APP_DIR}/.venv"
    fi
fi

if [ ! -x "${APP_DIR}/.venv/bin/python" ]; then
    log "Создаю виртуальное окружение (${PYTHON_BIN})..."
    "${PYTHON_BIN}" -m venv "${APP_DIR}/.venv"
fi

log "Обновляю pip и ставлю зависимости..."
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -e "${APP_DIR}"


# ---------- .env ----------
if [ ! -f "${APP_DIR}/.env" ]; then
    if [ -f "${APP_DIR}/.env.example" ]; then
        log "Создаю .env из .env.example — не забудьте вписать токен!"
        cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    else
        warn ".env.example не найден — создайте ${APP_DIR}/.env вручную."
    fi
fi

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 750 "${APP_DIR}"
[ -f "${APP_DIR}/.env" ] && chmod 640 "${APP_DIR}/.env"


# ---------- systemd unit ----------
log "Создаю ${SERVICE_FILE}..."
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=NoLightToday — Telegram-бот отключений Россети Ленэнерго
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${APP_DIR}/.env
Environment=PYTHONIOENCODING=utf-8
Environment=PYTHONUTF8=1
ExecStart=${APP_DIR}/.venv/bin/python -m src
Restart=always
RestartSec=10

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=${APP_DIR}

StandardOutput=append:${APP_DIR}/logs/stdout.log
StandardError=append:${APP_DIR}/logs/stderr.log

[Install]
WantedBy=multi-user.target
EOF


# ---------- запуск ----------
log "Перечитываю systemd и включаю автозапуск..."
systemctl daemon-reload
systemctl enable "${APP_NAME}"
systemctl restart "${APP_NAME}"

sleep 2
systemctl --no-pager --full status "${APP_NAME}" || true


# ---------- итог ----------
echo
log "Установка завершена. Использован Python ${PY_VERSION}."
echo
echo "Файлы:"
echo "  Приложение:   ${APP_DIR}"
echo "  .env:         ${APP_DIR}/.env"
echo "  База данных:  ${DATA_DIR}/bot_data.db"
echo "  Логи:         ${APP_DIR}/logs/"
echo "  Служба:       ${SERVICE_FILE}"
echo
echo "Управление:"
echo "  sudo systemctl status  ${APP_NAME}"
echo "  sudo systemctl restart ${APP_NAME}"
echo "  sudo systemctl stop    ${APP_NAME}"
echo "  journalctl -u ${APP_NAME} -f"
echo "  tail -f ${APP_DIR}/logs/stdout.log"
echo
warn "Не забудьте вписать BOT_TOKEN и ADMIN_IDS в ${APP_DIR}/.env,"
warn "затем перезапустить: sudo systemctl restart ${APP_NAME}"