<div align="center">

# 🕯 NoLightToday

**Telegram-бот, который следит за плановыми отключениями электроэнергии
на сайте [Россети Ленэнерго](https://rosseti-lenenergo.ru/planned_work/)
и присылает уведомления в группу.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?logo=telegram&logoColor=white)](https://docs.aiogram.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-4B8BBE)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

*«No light today» — сегодня света нет. Но вы узнаете об этом заранее.*

</div>

---

## 📖 О проекте

**NoLightToday** — небольшой Telegram-бот на Python, который периодически
проверяет [страницу плановых работ](https://rosseti-lenenergo.ru/planned_work/)
Россети Ленэнерго, сравнивает свежие записи с вашими подписками и присылает
уведомления в групповой чат.

Управление — через удобное меню с кнопками, доступное только администраторам
группы. Работает на Linux, macOS и Windows.

Проект рассчитан на жителей Санкт-Петербурга и Ленинградской области,
которым важно заранее знать о предстоящих отключениях света.

---

## ✨ Возможности

| Возможность | Описание |
|---|---|
| 🔔 **Уведомления в группу** | Как только на сайте появляется новая запись по отслеживаемому НП, бот пишет об этом в чат. |
| ⚙️ **Мультивыбор НП** | Можно подписаться сразу на несколько населённых пунктов. |
| ➕ **Ручной ввод** | Если нужного НП нет в списке (например, «СНТ Фауна» или «Петровское») — добавьте его вручную. Поиск идёт по полям «Район / Населённый пункт» и «Адрес». |
| 🏆 **Приоритеты** | Если на одну дату приходится несколько отключений в разных НП, приходит **одно** уведомление — по «главному» НП. Остальные доступны в разделе «📅 Отключения». |
| 📅 **Просмотр по датам** | Список всех отключений по вашим НП на конкретный день — прямо в боте, без повторного обращения к сайту (данные кэшируются). |
| 👥 **Привязка к группе** | Настройки у каждой группы свои. При добавлении бота в группу появляется кнопка с её названием. |
| 🔒 **Только для администраторов** | Все настройки доступны пользователям из белого списка ID. Остальные получают только уведомления. |
| 💾 **Файловая БД** | Всё хранится в одном файле `data/bot_data.db` — легко бэкапить и переносить. |
| 🎛 **Меню на кнопках** | Основное управление — через reply-кнопку «📋 Меню» и inline-навигацию. Есть несколько служебных команд: `/start`, `/menu`, `/setup`. |
| 🖥 **Кроссплатформенность** | Linux, macOS и Windows. Скрипты запуска для всех трёх систем. |

---

## 🗺️ Схема работы

```
┌──────────────────────────┐       ┌──────────────────────────┐
│  rosseti-lenenergo.ru    │       │  Telegram группа         │
│  /planned_work/          │       │  (получатели)            │
└────────────┬─────────────┘       └────────────┬─────────────┘
             │ HTTP GET + парсинг               │ сообщение
             │ (requests + BeautifulSoup)       │
             ▼                                  │
      ┌──────────────┐                  ┌───────┴─────────┐
      │  parser.py   │───list[dict]────▶│  scheduler.py   │
      └──────────────┘                  │  (раз в час)    │
                                        └───────┬─────────┘
                                                │
                              ┌─────────────────┴──────────────────┐
                              ▼                                    ▼
                      ┌───────────────┐                   ┌────────────────┐
                      │ bot_data.db   │◀────чтение────────│    bot.py      │
                      │  (SQLite)     │─────запись───────▶│  (aiogram 3)   │
                      └───────────────┘                   └────────────────┘
```

---

## 🗓️ График проверок

По умолчанию бот проверяет сайт **раз в час**, 24/7. При старте запускается
немедленная проверка, чтобы не ждать первого интервала.

| Событие | Когда выполняется |
|---|---|
| Первая проверка сайта | Сразу после запуска бота |
| Последующие проверки | Каждые `CHECK_INTERVAL` секунд (по умолчанию 3600) |
| Отправка уведомления в чат | В момент обнаружения новой записи |
| Обновление кэша `outage_cache` | На каждой проверке |
| Пометка «уже отправлено» | Сразу после успешной отправки сообщения |

### Типичная суточная активность

```
00:00 ─── ●  проверка
01:00 ─── ●
02:00 ─── ●
...
12:00 ─── ●
13:00 ─── ●
...
23:00 ─── ●
```

Интервал легко поменять в `src/config.py` или через `.env`:

```dotenv
CHECK_INTERVAL=1800    # 30 минут
CHECK_INTERVAL=3600    # 1 час (по умолчанию)
CHECK_INTERVAL=7200    # 2 часа
```

> ⚠️ Не рекомендуется ставить интервал меньше 30 минут — это создаёт
> лишнюю нагрузку на сайт Россети и может привести к временной блокировке
> вашего IP.

---

## 🏗️ Структура проекта

```
nolighttoday/
├── src/                     # исходники (плоский src-layout)
│   ├── __init__.py
│   ├── __main__.py          # точка входа: python -m src
│   ├── bot.py               # хендлеры, меню, клавиатуры
│   ├── config.py            # токен, админы, НП, интервалы
│   ├── db.py                # работа с SQLite
│   ├── parser.py            # парсинг сайта Россети
│   ├── scheduler.py         # фоновая проверка и уведомления
│   └── filters.py           # проверка «админ ли пользователь»
├── tests/
│   └── test_parser.py
├── data/                    # сюда пишется bot_data.db
│   └── .gitkeep
├── scripts/
│   ├── run.sh               # запуск на Linux/macOS
│   ├── run.bat              # запуск на Windows (cmd)
│   ├── run.ps1              # запуск на Windows (PowerShell)
│   ├── install.bat          # установка на Windows (cmd)
│   ├── install.ps1          # установка на Windows (PowerShell)
│   ├── force_check.py       # ручной прогон парсера + рассылка уведомлений
│   ├── check_db.py          # диагностика БД
│   ├── debug_html.py        # сохраняет HTML и скриншот страницы сайта
│   └── debug_match.py       # сверяет записи кэша с подписками
├── .env.example
├── .gitattributes           # LF/CRLF для разных ОС
├── .gitignore
├── LICENSE
├── README.md
├── pyproject.toml
└── requirements.txt
```

---

## 🚀 Быстрый старт

### Общие шаги (все ОС)

1. **Получите токен бота** у [@BotFather](https://t.me/BotFather) — команда `/newbot`.
2. **Узнайте свой Telegram ID** у [@userinfobot](https://t.me/userinfobot).
3. **Склонируйте репозиторий** и перейдите в него:

   ```bash
   git clone https://github.com/<ваш_ник>/nolighttoday.git
   cd nolighttoday
   ```

4. **Создайте `.env`** из шаблона и заполните:

   ```dotenv
   BOT_TOKEN=123456789:AA...ваш_токен
   ADMIN_IDS=123456789
   CHECK_INTERVAL=3600
   ```

5. **Установите зависимости и запустите** — по инструкции для вашей ОС ниже.

---

### 🐧 Linux / 🍎 macOS

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"

python -m src
```

Или через удобный скрипт:

```bash
chmod +x scripts/run.sh
./scripts/run.sh
```

---

### 🪟 Windows

#### Шаг 1. Установите Python

Скачайте **Python 3.11+** с [python.org](https://www.python.org/downloads/windows/).
При установке обязательно отметьте:

- ✅ **Add python.exe to PATH**
- ✅ **Install launcher for all users**

#### Шаг 2. Установите Git (опционально)

Если хотите клонировать репозиторий, а не скачивать ZIP —
установите [Git for Windows](https://git-scm.com/download/win).

#### Шаг 3. Скачайте проект

```cmd
git clone https://github.com/<ваш_ник>/nolighttoday.git
cd nolighttoday
```

Или просто распакуйте ZIP в удобную папку, например `C:\Projects\nolighttoday`.

#### Шаг 4. Настройте `.env`

Скопируйте `.env.example` → `.env` и заполните в Блокноте / VS Code:

```dotenv
BOT_TOKEN=123456789:AA...ваш_токен
ADMIN_IDS=123456789
```

> 💡 Сохраняйте `.env` в кодировке **UTF-8 без BOM**.
> Notepad++ и VS Code сохраняют правильно по умолчанию.

#### Шаг 5. Установите зависимости

Двойной клик по **`scripts\install.bat`** или из cmd:

```cmd
scripts\install.bat
```

#### Шаг 6. Запустите бота

Двойной клик по **`scripts\run.bat`** или из PowerShell:

```powershell
.\scripts\run.ps1
```

Если PowerShell блокирует скрипты, разрешите локальные:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

#### Шаг 7. Автозапуск (опционально)

См. раздел [Автозапуск на Windows](#-автозапуск-на-windows) ниже.

---

## 🎛 Использование

### Добавление бота в группу

1. Добавьте бота в группу.
2. Убедитесь, что у него есть право **отправлять сообщения**.
3. **Отключите Privacy Mode** через @BotFather: `/setprivacy` → выберите бота → **Disable**. Без этого бот **не увидит** обычный текст в группе.
4. **Перезайдите бота в группу** (удалите → добавьте снова), чтобы Telegram применил Privacy Mode.
5. Напишите в группе `/start` — бот покажет приветствие и кнопку «⚙️ Настроить: <группа>».

> 💡 **Важно:** добавляйте бота в группу под аккаунтом из `ADMIN_IDS`.
> Только тогда откроется меню.

Если бот был в группе до обновления кода и приветствие не пришло — отправьте в группе команду `/setup`. Она вызовет то же сообщение с кнопкой.

### Карта меню

```
📋 Меню (reply-кнопка)
│
└── Главное меню (inline)
    │
    ├── ⚙️ Подписки
    │   ├── ⬜ Санкт-Петербург
    │   ├── ✅ Всеволожск          ← клик — включить/выключить
    │   ├── ✅ Гатчина
    │   ├── ⬜ Выборг
    │   ├── ➕ Добавить свой НП
    │   ├── 🗑 Очистить всё
    │   └── ⬅️ Назад
    │
    ├── 🏆 Приоритет
    │   ├── ⬆️ Гатчина   ⬇️ Гатчина
    │   ├── ⬆️ Всеволожск ⬇️ Всеволожск
    │   └── ⬅️ Назад
    │
    ├── 📅 Отключения
    │   ├── 📅 15.03.2026
    │   ├── 📅 16.03.2026
    │   ├── 📅 17.03.2026
    │   └── ⬅️ Назад
    │
    └── ℹ️ Помощь
```

### Ручной ввод населённого пункта

Если в списке нет нужного адреса (например, «СНТ Фауна», «Петровское»,
«Ломоносовский») — нажмите **➕ Добавить свой НП** и отправьте название
следующим сообщением. Бот ищет совпадения сразу в трёх полях:
«Район / Населённый пункт», «Адрес» и «Населённый пункт». Так находятся
и районы, и СНТ, и отдельные деревни.

> 💡 Можно вводить часть названия: «Фауна» найдёт и «тер. СНТ Фауна»,
> и «д Петровское тер. СНТ Фауна». Регистр не важен.

### Логика «главного» НП

Допустим, вы подписаны на **Гатчину** и **Всеволожск**, и у Гатчины приоритет
выше (в списке «🏆 Приоритет» она сверху). На 15 марта есть отключения в обоих НП.

**Что произойдёт:** бот пришлёт **одно** сообщение — по Гатчине, а про отключение
во Всеволожске напишет короткой припиской. Полный список по обоим НП доступен
в разделе **📅 Отключения → 15.03.2026**.

Это защищает чат от спама, когда на один день выпадает сразу много записей.

---

## 📊 Пример уведомления

```
⚡ Плановое отключение
📍 р-н Ломоносовский
   • тер. СНТ Фауна
   • д Петровское
   • тер. ДНП Петровское
🕒 30-09-2026 09:00 → 30-09-2026 17:00
💬 Согласование № 329

📎 В этот же день ещё 2 отключ. в других НП.
Откройте «📅 Отключения → 30.09.2026» в меню.
```

Пустые поля (филиал, РЭС) не выводятся — никаких «🏢 /». Адрес разбивается
на отдельные части по маркерам `тер.`, `д`, `ул`, `СНТ`, `ДНП` и т.д.

---

## 💾 Работа с базой данных

Все данные — в одном файле `data/bot_data.db` (SQLite).

### Таблицы

**`subscriptions`** — подписки чата на НП:

| id | chat_id | locality | priority |
|----|---------|----------|----------|
| 1  | -1001234567890 | Гатчина | 1 |
| 2  | -1001234567890 | Всеволожск | 2 |

**`sent_notifications`** — что уже отправлено (защита от дублей):

| chat_id | outage_id | sent_at |
|---------|-----------|---------|
| -100… | `a1b2c3…` | 2026-03-14 08:00:11 |

**`outage_cache`** — кэш всех спарсенных записей:

| outage_id | date_key | locality | payload (JSON) | fetched_at |
|---|---|---|---|---|

**`chats`** — список групп, куда добавлен бот:

| chat_id | title | added_at | updated_at |
|---|---|---|---|
| -1001234567890 | Моя группа | 2026-09-30 12:00 | 2026-09-30 12:00 |

**`awaiting_input`** — флаг «ждём ввод названия НП»:

| chat_id | user_id | kind | created_at |
|---|---|---|---|
| -1001234567890 | 140769359 | `locality` | 2026-09-30 14:03 |

> `awaiting_input` заменяет FSM: когда вы нажали «➕ Добавить свой НП», бот
> ставит здесь флаг и ждёт следующего текстового сообщения. Это переживает
> перезапуск бота, чего FSM не умеет без внешнего хранилища.

### Резервная копия

```bash
cp data/bot_data.db data/bot_data.db.bak            # простая копия
sqlite3 data/bot_data.db ".backup backup.db"        # «горячий» бэкап
```

### Просмотр из консоли

```bash
sqlite3 data/bot_data.db
sqlite> .tables
sqlite> SELECT * FROM subscriptions;
sqlite> .quit
```

### Полный сброс

Остановите бота и просто удалите файл:

```bash
rm data/bot_data.db          # Linux/macOS
del data\bot_data.db         # Windows
```

При следующем запуске он создастся заново.

---

## 🧰 Полезные скрипты

Все запускаются из корня проекта.

| Команда | Что делает |
|---|---|
| `.venv\Scripts\python.exe scripts\force_check.py` | Вручную прогоняет парсер и рассылает уведомления. Полезно, если не хотите ждать плановой проверки. |
| `.venv\Scripts\python.exe scripts\check_db.py <chat_id>` | Показывает содержимое БД: группы, подписки, ожидание ввода. |
| `.venv\Scripts\python.exe scripts\debug_html.py "СНТ Фауна"` | Сохраняет HTML и скриншот страницы сайта в `debug/` — для отладки парсера. |
| `.venv\Scripts\python.exe scripts\debug_match.py` | Проверяет, матчатся ли записи из кэша с вашими подписками. |

---

## 🐳 Docker (Linux / macOS / Windows с Docker Desktop)

**Dockerfile:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install -e .
CMD ["python", "-m", "src"]
```

**docker-compose.yml:**

```yaml
services:
  nolighttoday:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
    environment:
      - TZ=Europe/Moscow
```

Запуск:

```bash
docker compose up -d --build
docker compose logs -f
```

---

## 🖥 Автозапуск на Linux (systemd)

Создайте `/etc/systemd/system/nolighttoday.service`:

```ini
[Unit]
Description=NoLightToday — Telegram-бот отключений Россети Ленэнерго
After=network.target

[Service]
Type=simple
User=nolighttoday
WorkingDirectory=/opt/nolighttoday
EnvironmentFile=/opt/nolighttoday/.env
ExecStart=/opt/nolighttoday/.venv/bin/python -m src
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активация:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nolighttoday
sudo systemctl status nolighttoday
journalctl -u nolighttoday -f
```

---

## 🪟 Автозапуск на Windows

### Вариант A — Планировщик задач (Task Scheduler)

Родной способ, без сторонних программ. Создаём задачу, которая запускает
бота при входе пользователя.

1. Откройте **Task Scheduler** (`taskschd.msc`).
2. **Create Task** → вкладка **General**:
   - Name: `NoLightToday`
   - ✅ Run with highest privileges
3. Вкладка **Triggers** → **New…** → **At log on**.
4. Вкладка **Actions** → **New…**:
   - Action: `Start a program`
   - Program/script: `C:\путь\до\nolighttoday\scripts\run.bat`
   - Start in: `C:\путь\до\nolighttoday`
5. Вкладка **Settings**:
   - ✅ If the task fails, restart every **1 minute**, up to **3** times.
   - ❌ Stop the task if it runs longer than… *(снять галочку — бот работает постоянно)*.
6. **OK**.

Проверить из командной строки:

```cmd
schtasks /Run /TN "NoLightToday"
```

### Вариант B — NSSM (служба Windows)

Превращает bat в настоящую службу Windows. Скачайте
[NSSM](https://nssm.cc/download), распакуйте `nssm.exe` в `C:\Tools\nssm\`.

В **cmd от имени администратора**:

```cmd
C:\Tools\nssm\nssm.exe install NoLightToday "C:\путь\до\nolighttoday\.venv\Scripts\python.exe" "-m src"
C:\Tools\nssm\nssm.exe set NoLightToday AppDirectory "C:\путь\до\nolighttoday"
C:\Tools\nssm\nssm.exe set NoLightToday AppStdout "C:\путь\до\nolighttoday\logs\stdout.log"
C:\Tools\nssm\nssm.exe set NoLightToday AppStderr "C:\путь\до\nolighttoday\logs\stderr.log"
C:\Tools\nssm\nssm.exe set NoLightToday AppEnvironmentExtra "PYTHONIOENCODING=utf-8" "PYTHONUTF8=1"
C:\Tools\nssm\nssm.exe set NoLightToday Start SERVICE_AUTO_START
C:\Tools\nssm\nssm.exe start NoLightToday
```

Управление:

```cmd
nssm.exe status  NoLightToday
nssm.exe restart NoLightToday
nssm.exe stop    NoLightToday
nssm.exe remove  NoLightToday confirm
```

### Вариант C — Docker Desktop

Если стоит Docker Desktop с WSL2 — используйте тот же `docker-compose.yml`,
что и на Linux.

---

## ⚙️ Кастомизация

### Свой список населённых пунктов

Отредактируйте `LOCALITIES` в `src/config.py`. Бот перерисует меню подписок
по этому списку. Это лишь **быстрые кнопки** — пользователь всё равно может
добавить любой НП вручную через «➕ Добавить свой НП».

### Несколько администраторов

В `.env`:

```dotenv
ADMIN_IDS=111111111,222222222,333333333
```

Любой из списка может управлять ботом из своей группы.

### Проверка только определённого района

В `src/parser.py` после парсинга строки можно фильтровать по `region` / `district`:

```python
records = [r for r in records if "Гатчинский" in r["district"]]
```

### Отправка уведомлений не в группу, а в личку

Замените `chat_id` в таблице `subscriptions` на личный ID пользователя.
Бот отправит сообщение туда же, куда и подписка.

---

## 🧪 Тестирование парсера

Перед первым запуском бота полезно убедиться, что парсер достаёт данные:

```cmd
.venv\Scripts\python.exe -c "from src.parser import parse_outages; import json; data = parse_outages(street='СНТ Фауна', max_pages=1); print('Найдено:', len(data)); [print(' •', r['district'], '|', r['address'][:60], '|', r['start']) for r in data]"
```

Ожидаемый вывод:

```
[parser] street='СНТ Фауна' стр.1: 2 записей
Найдено: 2
 • р-н Ломоносовский | тер. СНТ Фауна д Петровское тер. ДНП Петровское | 30-09-2026 09:00
 • р-н Ломоносовский | д Петровское тер. СНТ Фауна Петровская слобода… | 25-09-2026 09:00
```

Если вывод пустой — проверьте **индексы колонок** в `src/parser.py`, открыв
HTML таблицы на сайте через F12 → Elements. На странице три `<table>`:
форма фильтра, данные, служебная. Нам нужна вторая — с классом `tableous_facts`.

Запуск юнит-тестов:

```bash
pytest -q
```

---

## 🛠 Частые проблемы

| Симптом | Причина / решение |
|---|---|
| **Бот не отвечает на «📋 Меню»** | Ваш ID не в `ADMIN_IDS`. Узнайте через [@userinfobot](https://t.me/userinfobot). |
| **Бот молчит в группе на обычный текст** | Включён Privacy Mode. Отключите через @BotFather → `/setprivacy` → Disable, и перезайдите бота в группу. |
| **Не приходит приветствие при добавлении в группу** | Отправьте в группе `/setup` — это вручную вызовет то же сообщение с кнопкой. |
| **Парсер возвращает `[]`** | Изменилась вёрстка таблицы — поправьте индексы колонок в `src/parser.py`. |
| **`requests` падает с `403`** | Смените `User-Agent` в `src/parser.py`. |
| **SSL CERTIFICATE_VERIFY_FAILED на Windows** | Установите `pip-system-certs`: `.venv\Scripts\python.exe -m pip install pip-system-certs` |
| **Уведомления не приходят** | Бот не добавлен в группу или у него нет прав на отправку. Проверьте `SELECT DISTINCT chat_id FROM subscriptions`. |
| **Дубли уведомлений** | Проверьте таблицу `sent_notifications` и уникальный индекс. |
| **«📅 Отключения» показывает пусто** | Кэш ещё не заполнен или по вашим НП нет отключений на эту дату. |
| **Не добавляется свой НП** | Если бот молчит — вы, вероятно, в группе с включённым Privacy Mode, либо не в `ADMIN_IDS`. |
| 🪟 **`python не является внутренней командой`** | Python не в PATH. Переустановите с галочкой **Add python.exe to PATH**. |
| 🪟 **Русские буквы в консоли — «кракозябры»** | Выполните `chcp 65001` перед запуском. В `run.bat` уже включено. |
| 🪟 **`UnicodeEncodeError: 'charmap' codec`** | Обновите `src/__main__.py` — там принудительный UTF-8. |
| 🪟 **PowerShell блокирует `run.ps1`** | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 🪟 **Windows Defender блокирует сеть** | Добавьте `.venv\Scripts\python.exe` в исключения. |
| 🪟 **Файл БД в OneDrive / Dropbox повреждён** | Не храните `bot_data.db` в облачной синхронизации. |

---

## 🗺 Дорожная карта

- [x] Парсинг страницы `planned_work`
- [x] Мультивыбор НП через inline-кнопки
- [x] Приоритеты НП
- [x] Кэш отключений в SQLite
- [x] Ограничение доступа по `ADMIN_IDS`
- [x] Кроссплатформенность (Linux / macOS / Windows)
- [x] Ручной ввод произвольного НП
- [x] Привязка настроек к конкретной группе
- [x] Приветствие с кнопкой при добавлении в группу
- [ ] Настройка `CHECK_INTERVAL` из меню
- [ ] Экспорт отключений в CSV / ICS (для календарей)
- [ ] Поддержка других филиалов Россети (МОЭСК, Кубаньэнерго и т.д.)
- [ ] Веб-панель для просмотра подписок
- [ ] Уведомления по расписанию (например, только 08:00–22:00)

---

## 🤝 Вклад

Pull request'ы приветствуются. Если нашли баг или хотите предложить фичу —
откройте [Issue](https://github.com/<ваш_ник>/nolighttoday/issues).

Перед PR:

```bash
pip install ruff
ruff check .
pytest -q
```

---

## 📜 Лицензия

Проект распространяется под лицензией **MIT** — см. файл [LICENSE](LICENSE).

---

## ⚠️ Дисклеймер

Проект **не связан** с ПАО «Россети Ленэнерго» и является независимым
инструментом для удобного просмотра **публично доступной** информации
с официального сайта. Данные предоставляются «как есть», без гарантий
актуальности. Для официальной информации об отключениях всегда
сверяйтесь с сайтом компании.

---

<div align="center">

Сделано с 🕯 для тех, кто не любит сидеть без света.

</div>