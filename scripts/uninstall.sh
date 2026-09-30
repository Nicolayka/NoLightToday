#!/usr/bin/env bash
#
# NoLightToday — удаление с Debian/Ubuntu.
#
# Использование (от root):
#     sudo bash scripts/uninstall.sh             # спросит подтверждение
#     sudo bash scripts/uninstall.sh --yes       # без подтверждения
#     sudo bash scripts/uninstall.sh --keep-data # сохранить БД и .env
#
# Что удаляет:
#   1. Останавливает и отключает службу nolighttoday.
#   2. Удаляет /etc/systemd/system/nolighttoday.service.
#   3. Удаляет /opt/nolighttoday (или только код, если --keep-data).
#   4. Удаляет системного пользователя nolighttoday.
#   5. Делает daemon-reload.
#
set -euo pipefail

APP_NAME="nolighttoday"
APP_USER="nolighttoday"
APP_DIR="/opt/${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

# ---------- флаги ----------
YES=0
KEEP_DATA=0
for arg in "$@"; do
    case "${arg}" in
        --yes|-y)       YES=1 ;;
        --keep-data)    KEEP_DATA=1 ;;
        --help|-h)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Неизвестный флаг: ${arg}" >&2
            echo "Используйте --help для справки." >&2
            exit 1
            ;;
    esac
done


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
    err "Скрипт нужно запускать от root: sudo bash scripts/uninstall.sh"
    exit 1
fi

if [ ! -d "${APP_DIR}" ] && [ ! -f "${SERVICE_FILE}" ]; then
    warn "Не найдено ни ${APP_DIR}, ни ${SERVICE_FILE}."
    warn "Похоже, NoLightToday не установлен."
    exit 0
fi


# ---------- подтверждение ----------
if [ "${YES}" -ne 1 ]; then
    echo
    warn "Будут удалены:"
    echo "    • служба        ${APP_NAME}"
    echo "    • unit-файл     ${SERVICE_FILE}"
    if [ "${KEEP_DATA}" -eq 1 ]; then
        echo "    • каталог       ${APP_DIR} (кроме data/ и .env)"
    else
        echo "    • каталог       ${APP_DIR} (всё, включая БД и .env)"
    fi
    echo "    • пользователь  ${APP_USER}"
    echo
    read -r -p "Продолжить? [y/N] " answer
    case "${answer}" in
        y|Y|yes|YES) ;;
        *) echo "Отменено."; exit 0 ;;
    esac
fi


# ---------- служба ----------
if systemctl list-unit-files | grep -q "^${APP_NAME}\.service"; then
    log "Останавливаю службу ${APP_NAME}..."
    systemctl stop "${APP_NAME}" 2>/dev/null || true
    systemctl disable "${APP_NAME}" 2>/dev/null || true
else
    log "Служба ${APP_NAME} не зарегистрирована."
fi

if [ -f "${SERVICE_FILE}" ]; then
    log "Удаляю ${SERVICE_FILE}..."
    rm -f "${SERVICE_FILE}"
    systemctl daemon-reload
    systemctl reset-failed "${APP_NAME}" 2>/dev/null || true
fi


# ---------- каталог ----------
if [ -d "${APP_DIR}" ]; then
    if [ "${KEEP_DATA}" -eq 1 ]; then
        # Сохраняем БД, .env и логи
        BACKUP_DIR="/root/${APP_NAME}-backup-$(date +%Y%m%d-%H%M%S)"
        log "Сохраняю данные в ${BACKUP_DIR}..."
        mkdir -p "${BACKUP_DIR}/data"
        [ -d "${APP_DIR}/data" ] && cp -a "${APP_DIR}/data/." "${BACKUP_DIR}/data/" 2>/dev/null || true
        [ -f "${APP_DIR}/.env" ] && cp -a "${APP_DIR}/.env" "${BACKUP_DIR}/.env" || true
        [ -d "${APP_DIR}/logs" ] && cp -a "${APP_DIR}/logs" "${BACKUP_DIR}/logs" || true
        chmod 600 "${BACKUP_DIR}/.env" 2>/dev/null || true
        warn "Резервная копия: ${BACKUP_DIR}"
        log "Удаляю каталог ${APP_DIR}..."
        rm -rf "${APP_DIR}"
    else
        log "Удаляю каталог ${APP_DIR} (включая БД, .env, логи)..."
        rm -rf "${APP_DIR}"
    fi
else
    log "Каталог ${APP_DIR} не найден."
fi


# ---------- пользователь ----------
if id -u "${APP_USER}" >/dev/null 2>&1; then
    log "Удаляю пользователя ${APP_USER}..."
    # -r удаляет домашний каталог, если он есть
    userdel -r "${APP_USER}" 2>/dev/null || userdel "${APP_USER}" 2>/dev/null || {
        warn "Не удалось удалить пользователя ${APP_USER}."
        warn "Возможно, от него ещё работают процессы. Проверьте: ps -u ${APP_USER}"
    }
else
    log "Пользователь ${APP_USER} уже удалён."
fi


# ---------- итог ----------
echo
log "Удаление завершено."

if [ "${KEEP_DATA}" -eq 1 ]; then
    echo
    echo "Данные сохранены в: ${BACKUP_DIR}"
    echo "Чтобы восстановить:"
    echo "  git clone <repo> /home/NoLightToday"
    echo "  cd /home/NoLightToday && sudo bash scripts/install.sh"
    echo "  sudo cp -a ${BACKUP_DIR}/data/. /opt/nolighttoday/data/"
    echo "  sudo cp ${BACKUP_DIR}/.env /opt/nolighttoday/.env"
    echo "  sudo chown -R ${APP_USER}:${APP_USER} /opt/nolighttoday"
    echo "  sudo systemctl restart ${APP_NAME}"
fi