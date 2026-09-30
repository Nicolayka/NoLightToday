"""Ручной прогон парсера + рассылка уведомлений.

Использование (из корня проекта):

    # Прогнать по всем существующим подпискам (обычный сценарий)
    .venv\\Scripts\\python.exe scripts\\force_check.py

    # Прогнать только для одной группы (по её chat_id)
    .venv\\Scripts\\python.exe scripts\\force_check.py -1004477451907

    # Добавить НП указанной группе и сразу прогнать
    .venv\\Scripts\\python.exe scripts\\force_check.py -1004477451907 "СНТ Фауна"
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db                                          # noqa: E402
from config import BOT_TOKEN                       # noqa: E402
from scheduler import fetch_all_outages, notify_all  # noqa: E402


def _parse_args():
    """Возвращает (chat_id | None, locality | None)."""
    args = sys.argv[1:]
    if not args:
        return None, None

    # Первый аргумент — chat_id (число), иначе считаем его названием НП
    try:
        chat_id = int(args[0])
    except ValueError:
        return None, args[0]

    locality = args[1] if len(args) > 1 else None
    return chat_id, locality


async def main() -> None:
    await db.init_db()

    chat_id, locality = _parse_args()

    # Если передали chat_id + locality — добавим подписку именно этому чату
    if chat_id is not None and locality is not None:
        await db.upsert_chat(chat_id, f"chat {chat_id}")
        await db.toggle_subscription(chat_id, locality)
        print(f"[force] добавлена подписка '{locality}' для chat_id={chat_id}")

    # Если передали только chat_id — покажем его текущие подписки
    if chat_id is not None:
        subs = await db.get_subscriptions(chat_id)
        if not subs:
            print(f"[force] у чата {chat_id} нет подписок — нечего собирать")
            return
        print(f"[force] подписки чата {chat_id}: "
              f"{', '.join(loc for loc, _ in subs)}")

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