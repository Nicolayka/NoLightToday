import json
import os

import aiosqlite

from config import DB_PATH


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id   INTEGER NOT NULL,
    locality  TEXT    NOT NULL,
    priority  INTEGER NOT NULL DEFAULT 100,
    UNIQUE(chat_id, locality)
);

CREATE TABLE IF NOT EXISTS sent_notifications (
    chat_id   INTEGER NOT NULL,
    outage_id TEXT    NOT NULL,
    sent_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, outage_id)
);

CREATE TABLE IF NOT EXISTS outage_cache (
    outage_id  TEXT PRIMARY KEY,
    date_key   TEXT NOT NULL,
    locality   TEXT NOT NULL,
    payload    TEXT NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_subs_chat  ON subscriptions(chat_id);
CREATE INDEX IF NOT EXISTS idx_cache_date ON outage_cache(date_key);
"""


async def init_db() -> None:
    """Создаёт файл БД и таблицы, если их ещё нет."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_SQL)
        await db.commit()


# ---------- Подписки ----------

async def get_subscriptions(chat_id: int) -> list[tuple[str, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT locality, priority FROM subscriptions "
            "WHERE chat_id = ? ORDER BY priority, id",
            (chat_id,),
        ) as cur:
            return [(r[0], r[1]) for r in await cur.fetchall()]


async def get_subscriptions_with_ids(chat_id: int) -> list[tuple[int, str, int]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, locality, priority FROM subscriptions "
            "WHERE chat_id = ? ORDER BY priority, id",
            (chat_id,),
        ) as cur:
            return await cur.fetchall()


async def get_subscribed_localities(chat_id: int) -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT locality FROM subscriptions WHERE chat_id = ?",
            (chat_id,),
        ) as cur:
            return {r[0] for r in await cur.fetchall()}


async def toggle_subscription(chat_id: int, locality: str) -> bool:
    """Добавляет или удаляет подписку. Возвращает True, если теперь подписан."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM subscriptions WHERE chat_id = ? AND locality = ?",
            (chat_id, locality),
        ) as cur:
            row = await cur.fetchone()

        if row:
            await db.execute("DELETE FROM subscriptions WHERE id = ?", (row[0],))
            await db.commit()
            return False

        async with db.execute(
            "SELECT COALESCE(MAX(priority), 0) + 1 "
            "FROM subscriptions WHERE chat_id = ?",
            (chat_id,),
        ) as cur:
            next_prio = (await cur.fetchone())[0]

        await db.execute(
            "INSERT INTO subscriptions (chat_id, locality, priority) "
            "VALUES (?, ?, ?)",
            (chat_id, locality, next_prio),
        )
        await db.commit()
        return True


async def clear_subscriptions(chat_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscriptions WHERE chat_id = ?", (chat_id,))
        await db.commit()


async def swap_priority(chat_id: int, sub_id_a: int, sub_id_b: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, priority FROM subscriptions "
            "WHERE chat_id = ? AND id IN (?, ?)",
            (chat_id, sub_id_a, sub_id_b),
        ) as cur:
            rows = {r[0]: r[1] for r in await cur.fetchall()}
        if len(rows) != 2:
            return
        pa, pb = rows[sub_id_a], rows[sub_id_b]
        await db.execute(
            "UPDATE subscriptions SET priority = ? WHERE id = ?", (pb, sub_id_a)
        )
        await db.execute(
            "UPDATE subscriptions SET priority = ? WHERE id = ?", (pa, sub_id_b)
        )
        await db.commit()


async def get_all_chats_with_subs() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT chat_id FROM subscriptions") as cur:
            return [r[0] for r in await cur.fetchall()]


# ---------- Уведомления ----------

async def already_sent(chat_id: int, outage_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM sent_notifications WHERE chat_id = ? AND outage_id = ?",
            (chat_id, outage_id),
        ) as cur:
            return await cur.fetchone() is not None


async def mark_sent(chat_id: int, outage_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sent_notifications (chat_id, outage_id) "
            "VALUES (?, ?)",
            (chat_id, outage_id),
        )
        await db.commit()


# ---------- Кэш отключений ----------

async def save_cache(records: list[dict]) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR REPLACE INTO outage_cache "
            "(outage_id, date_key, locality, payload, fetched_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                (
                    r["id"],
                    r["date_key"],
                    r["locality"],
                    json.dumps(r, ensure_ascii=False),
                )
                for r in records
            ],
        )
        await db.commit()


async def get_cache_by_date(date_key: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT payload FROM outage_cache WHERE date_key = ?", (date_key,)
        ) as cur:
            return [json.loads(r[0]) for r in await cur.fetchall()]


async def get_available_dates() -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT date_key FROM outage_cache") as cur:
            dates = [r[0] for r in await cur.fetchall()]

    def key(d: str):
        try:
            dd, mm, yyyy = d.split(".")
            return (int(yyyy), int(mm), int(dd))
        except Exception:
            return (0, 0, 0)

    return sorted(dates, key=key)