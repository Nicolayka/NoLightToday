"""Проверка содержимого БД: что видит бот.

Использование:
    .venv\\Scripts\\python.exe scripts\\check_db.py
    .venv\\Scripts\\python.exe scripts\\check_db.py -1004477451907
"""
import asyncio
import sys
from pathlib import Path

# Добавляем src/ в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db  # noqa: E402


async def main():
    await db.init_db()

    print("\n=== ГРУППЫ (chats) ===")
    chats = await db.get_all_chats()
    if not chats:
        print("  (пусто)")
    for cid, title in chats:
        print(f"  {cid}  →  {title!r}")

    print("\n=== ВСЕ ПОДПИСКИ ===")
    async with db.aiosqlite.connect(db.DB_PATH) as conn:
        async with conn.execute(
            "SELECT chat_id, locality, priority FROM subscriptions "
            "ORDER BY chat_id, priority"
        ) as cur:
            subs = await cur.fetchall()
    if not subs:
        print("  (пусто)")
    for chat_id, loc, prio in subs:
        print(f"  chat={chat_id}  locality={loc!r}  priority={prio}")

    print("\n=== ОЖИДАНИЕ ВВОДА (awaiting_input) ===")
    async with db.aiosqlite.connect(db.DB_PATH) as conn:
        async with conn.execute(
            "SELECT chat_id, user_id, kind, created_at FROM awaiting_input"
        ) as cur:
            awaiting = await cur.fetchall()
    if not awaiting:
        print("  (пусто)")
    for chat_id, user_id, kind, created in awaiting:
        print(f"  chat={chat_id}  user={user_id}  kind={kind!r}  at={created}")

    # Если передан chat_id — проверяем его точечно
    if len(sys.argv) > 1:
        try:
            cid = int(sys.argv[1])
        except ValueError:
            print(f"\n[!] Не удалось разобрать chat_id: {sys.argv[1]}")
            return
        print(f"\n=== ПРОВЕРКА CHAT {cid} ===")
        print(f"  awaiting: {await db.get_awaiting(cid)}")
        print(f"  subs: {sorted(await db.get_subscribed_localities(cid))}")


if __name__ == "__main__":
    asyncio.run(main())