import asyncio
from collections import defaultdict

from aiogram import Bot

import db
from config import CHECK_INTERVAL
from parser import parse_outages


def format_outage(o: dict) -> str:
    return (
        f"⚡ <b>Плановое отключение</b>\n"
        f"📍 {o['locality']}, {o['address']}\n"
        f"🕒 {o['start']} → {o['end']}\n"
        f"🏢 {o.get('branch','')} / {o.get('res','')}\n"
        f"💬 {o.get('comment','')}"
    )


def _truncate(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[: limit - 20] + "\n…обрезано"


async def notify_all(bot: Bot, outages: list[dict]) -> None:
    chats = await db.get_all_chats_with_subs()

    for chat_id in chats:
        subs = await db.get_subscriptions(chat_id)   # [(locality, priority), ...]
        if not subs:
            continue
        loc_to_prio = {loc.lower(): prio for loc, prio in subs}

        relevant = [
            o for o in outages
            if any(loc in o["locality"].lower() for loc in loc_to_prio)
        ]
        if not relevant:
            continue

        # Группируем по дате начала
        by_date: dict[str, list[dict]] = defaultdict(list)
        for o in relevant:
            by_date[o["date_key"]].append(o)

        for date_key, items in by_date.items():
            def prio_of(rec: dict) -> int:
                for loc, prio in loc_to_prio.items():
                    if loc in rec["locality"].lower():
                        return prio
                return 10**9

            main = min(items, key=prio_of)
            others = [x for x in items if x["id"] != main["id"]]

            if await db.already_sent(chat_id, main["id"]):
                continue

            text = format_outage(main)
            if others:
                text += (
                    f"\n\n📎 В этот же день ещё {len(others)} отключ. "
                    f"в других НП. Откройте «📅 Отключения → {date_key}» в меню."
                )

            try:
                await bot.send_message(
                    chat_id, _truncate(text), parse_mode="HTML"
                )
                await db.mark_sent(chat_id, main["id"])
            except Exception as e:
                print(f"[notify] чат {chat_id}: {e}")


async def scheduler(bot: Bot) -> None:
    """Бесконечный цикл: проверяем сайт каждые CHECK_INTERVAL секунд."""
    while True:
        try:
            outages = parse_outages()
            if outages:
                await db.save_cache(outages)
                await notify_all(bot, outages)
            print(f"[scheduler] обработано записей: {len(outages)}")
        except Exception as e:
            print(f"[scheduler] ошибка: {e}")
        await asyncio.sleep(CHECK_INTERVAL)