#!/usr/bin/env bash
#
# NoLightToday — установка на Debian/Ubuntu как systemd-служба.
#
# Использование (от root):
#     sudo bash scripts/install-debian.sh
#
# Что делает:
#   1. Устанавливает системные пакеты (python3, venv, git, sqlite3).
#   2. Создаёт системного пользователя nolighttoday (без логина).
#   3. Копирует проект в /opt/nolighttoday.
#   4. Создаёт venv и ставит зависимости.
#   5. Создаёт /etc/systemd/system/nolighttoday.service.
#   6. Включает автозапуск и стартует службу.
#
# После установки:
#   - отредактируйте /opt/nolighttoday/.env (токен и админы)
#   - перезапустите:  sudo systemctl restart nolighttoday
#
set -euo pipefail

# ---------- настройки ----------
APP_NAME="nolighttoday"
APP_USER="nolighttoday"
APP_DIR="/opt/${APP_NAME}"
DATA_DIR="${APP_DIR}/data"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

# Директория, откуда запускается скрипт (корень репозитория)
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
    err "Скрипт нужно запускать от root: sudo bash scripts/install-debian.sh"
    exit 1
fi

if [ ! -f "${SRC_DIR}/pyproject.toml" ]; then
    err "Не найден pyproject.toml в ${SRC_DIR}. Запускайте скрипт из корня репозитория."
    exit 1
fi


# ---------- установка системных пакетов ----------
log "Обновляю apt и ставлю зависимости..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    git \
    sqlite3 \
    ca-certificates

# Для Python 3.12+ может потребоваться ensurepip
python3 -m ensurepip --upgrade 2>/dev/null || true


# ---------- создание пользователя ----------
if id -u "${APP_USER}" >/dev/null 2>&1; then
    log "Пользователь ${APP_USER} уже существует"
else
    log "Создаю системного пользователя ${APP_USER}..."
    useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi


# ---------- копирование проекта ----------
log "Копирую проект в ${APP_DIR}..."
mkdir -p "${APP_DIR}"
# Копируем содержимое репозитория, исключая уже существующие .venv, data, logs
rsync -a --delete \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='data/*.db' \
    --exclude='data/*.db-*' \
    --exclude='logs' \
    "${SRC_DIR}/" "${APP_DIR}/"

mkdir -p "${DATA_DIR}" "${APP_DIR}/logs"


# ---------- виртуальное окружение ----------
if [ ! -x "${APP_DIR}/.venv/bin/python" ]; then
    log "Создаю виртуальное окружение..."
    python3 -m venv "${APP_DIR}/.venv"
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

# Права на весь каталог — владелец системный пользователь
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 750 "${APP_DIR}"
chmod 640 "${APP_DIR}/.env" 2>/dev/null || true


# ---------- systemd unit ----------
log "Создаю ${SERVICE_FILE}..."
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=NoLightToday — Telegram-бот отключений Россети Ленэнерго
Documentation=https://github.com/<ваш_ник>/nolighttoday
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

# Ограничения безопасности
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=${APP_DIR}

# Логи
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
log "Установка завершена."
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