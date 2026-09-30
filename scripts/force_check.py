"""Ручная проверка: тянем данные, сохраняем кэш, шлём уведомления.

Использование (из корня проекта):
    .venv\\Scripts\\python.exe scripts\\force_check.py
    .venv\\Scripts\\python.exe scripts\\force_check.py "СНТ Фауна"
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db                                          # noqa: E402
from config import BOT_TOKEN                       # noqa: E402
from scheduler import fetch_all_outages, notify_all  # noqa: E402


async def main() -> None:
    await db.init_db()

    # Если передан аргумент — добавим его как подписку чату из ADMIN_IDS
    if len(sys.argv) > 1:
        from config import ADMIN_IDS
        if not ADMIN_IDS:
            print("[force] ADMIN_IDS пуст — не могу добавить временную подписку")
        else:
            admin_chat = next(iter(ADMIN_IDS))
            locality = sys.argv[1]
            await db.toggle_subscription(admin_chat, locality)
            print(f"[force] добавлена подписка '{locality}' для chat_id={admin_chat}")

    print("[force] собираю данные с сайта ...")
    outages = await fetch_all_outages()
    print(f"[force] получено записей: {len(outages)}")

    if not outages:
        print("[force] сайт вернул 0 записей — проверьте parser.py и подписки")
        return

    await db.save_cache(outages)
    print("[force] кэш обновлён")

    for r in outages[:10]:
        print(f"  • {r['district']} | {r['address'][:60]} | {r['start']}")

    from aiogram import Bot
    bot = Bot(token=BOT_TOKEN)
    try:
        await notify_all(bot, outages)
        print("[force] уведомления отправлены")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())