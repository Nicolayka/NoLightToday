"""Очищает таблицу sent_notifications — разрешает повторную отправку.

Использование:
    .venv\\Scripts\\python.exe scripts\\clear_sent.py
    .venv\\Scripts\\python.exe scripts\\clear_sent.py -1004477451907
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import aiosqlite                          # noqa: E402
from config import DB_PATH                # noqa: E402


async def main():
    async with aiosqlite.connect(DB_PATH) as db:
        if len(sys.argv) > 1:
            chat_id = int(sys.argv[1])
            await db.execute(
                "DELETE FROM sent_notifications WHERE chat_id = ?", (chat_id,)
            )
            print(f"[ok] очищены уведомления для chat_id={chat_id}")
        else:
            await db.execute("DELETE FROM sent_notifications")
            print("[ok] очищена вся таблица sent_notifications")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())