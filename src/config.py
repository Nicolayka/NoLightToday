import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent   # корень проекта


def _load_env_file(path: Path) -> None:
    """Минимальный .env-загрузчик: KEY=VALUE, # комментарии, кавычки обрезаются."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(BASE_DIR / ".env")


# --- Секреты ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬТЕ_ТОКЕН_ОТ_BOTFATHER")

ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
}

# --- Пути ---
DB_PATH = str(BASE_DIR / "data" / "bot_data.db")
LOG_DIR = BASE_DIR / "logs"                          # пригодится на Windows
LOG_DIR.mkdir(exist_ok=True)

# --- Парсер ---
BASE_URL = "https://rosseti-lenenergo.ru/planned_work/"
MAX_PAGES = 15
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))

# --- Список НП для меню подписок ---
LOCALITIES = [
    "Санкт-Петербург",
    "Ломоносов",
    "Петровское",
    "СНТ Фауна",
]

BOT_USERNAME = "NoLightToday_bot"   # без @, для deep-link

# Прокси для Telegram (на RU VPS провайдер блокирует по SNI).
# Формат: http://user:pass@host:port или socks5://user:pass@host:port
# Пусто = без прокси (для серверов вне РФ).
import os
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "").strip()