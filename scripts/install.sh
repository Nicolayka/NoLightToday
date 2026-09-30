#!/usr/bin/env bash
#
# NoLightToday — установка на Debian/Ubuntu как systemd-служба.
#
# Использование (от root):
#     sudo bash scripts/install.sh
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


# ---------- системные пакеты ----------
log "Проверяю системные пакеты..."

REQUIRED_PKGS=(python3 python3-venv python3-pip ca-certificates)
MISSING_PKGS=()
for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! dpkg -s "${pkg}" >/dev/null 2>&1; then
        MISSING_PKGS+=("${pkg}")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    log "Ставлю недостающие пакеты: ${MISSING_PKGS[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${MISSING_PKGS[@]}" || {
        err "Не удалось поставить пакеты. Проверьте apt: apt --fix-broken install"
        exit 1
    }
else
    log "Все необходимые пакеты уже установлены."
fi


# ---------- проверка venv ----------
# Проверяем, что python3 -m venv реально работает (бывает, что пакет есть,
# но pip внутри не создаётся)
if ! python3 -c "import venv" >/dev/null 2>&1; then
    err "Модуль venv не работает. Установите python3-venv и попробуйте снова."
    exit 1
fi


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