import asyncio
from collections import defaultdict

from aiogram import Bot

import db
import time
from config import CHECK_INTERVAL
from parser import parse_outages


async def fetch_all_outages() -> list[dict]:
    """Обходит подписки и собирает отключения по каждой отдельно.

    Сайт без фильтра отдаёт усечённую выборку — поэтому спрашиваем
    именно по каждому НП/адресу, который есть в подписках.
    """
    chats = await db.get_all_chats_with_subs()
    localities: set[str] = set()
    for chat_id in chats:
        for loc, _ in await db.get_subscriptions(chat_id):
            localities.add(loc)

    if not localities:
        print("[scheduler] подписок нет — пропускаю сбор данных")
        return []

    print(f"[scheduler] собираю данные по {len(localities)} НП")
    seen_ids: set[str] = set()
    result: list[dict] = []

    for loc in sorted(localities):
        records = parse_outages(street=loc, max_pages=2)
        added = 0
        for r in records:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                result.append(r)
                added += 1
        print(f"[scheduler] '{loc}': +{added} записей")
        await asyncio.sleep(1)

    return result

def format_outage(o: dict) -> str:
    """Формирует текст уведомления. Пропускает пустые поля.

    Адрес разбивается на отдельные части (тер., д., ул., СНТ и т.д.)
    и выводится списком — длинные адреса читаются легче.
    """
    import re

    lines: list[str] = ["⚡ <b>Плановое отключение</b>"]

    district = (o.get("district") or "").strip()
    address = (o.get("address") or "").strip()

    # Район — отдельной строкой с жирным
    if district:
        lines.append(f"📍 <b>{district}</b>")

    # Адрес — разбиваем на части и выводим списком
    if address:
        # Разделяем по маркерам, сохраняя сам маркер в начале части
        parts = re.split(
            r"\s+(?=тер\.|д\.|д |п |с |г\.|г |ш |ул |пер\.|снт |днп |с/п )",
            address,
        )
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) > 1:
            for p in parts:
                lines.append(f"   • {p}")
        else:
            lines.append(f"   {address[:200]}{'…' if len(address) > 200 else ''}")

    # Время
    start = (o.get("start") or "").strip()
    end = (o.get("end") or "").strip()
    if start or end:
        lines.append(f"🕒 {start} → {end}")

    # Филиал / РЭС — только если что-то есть
    branch = (o.get("branch") or "").strip()
    res = (o.get("res") or "").strip()
    if branch or res:
        org = " / ".join(p for p in (branch, res) if p)
        lines.append(f"🏢 {org}")

    # Комментарий
    comment = (o.get("comment") or "").strip()
    if comment:
        # «Согласование 329» → «Согласование № 329»
        # «Заявка 1234» → «Заявка № 1234»
        # «Договор 55» → «Договор № 55»
        comment = re.sub(
            r"^(Согласование|Заявка|Договор|Распоряжение|Предписание)\s+(\d+)\s*$",
            r"\1 № \2",
            comment,
            flags=re.IGNORECASE,
        )
        lines.append(f"💬 {comment}")
    return "\n".join(lines)

def matches_locality(o: dict, needle: str) -> bool:
    """Ищет needle в районе, адресе и населённом пункте (регистронезависимо)."""
    hay = " ".join([
        o.get("district", ""),
        o.get("address", ""),
        o.get("locality", ""),
    ]).lower()
    return needle.lower() in hay


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
            if any(matches_locality(o, loc) for loc in loc_to_prio)
        ]
        if not relevant:
            continue

        by_date: dict[str, list[dict]] = defaultdict(list)
        for o in relevant:
            by_date[o["date_key"]].append(o)

        for date_key, items in by_date.items():
            def prio_of(rec: dict) -> int:
                for loc, prio in loc_to_prio.items():
                    if matches_locality(rec, loc):
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
    while True:
        try:
            outages = await fetch_all_outages()      # <── было parse_outages()
            if outages:
                await db.save_cache(outages)
                await notify_all(bot, outages)
            print(f"[scheduler] обработано записей: {len(outages)}")
        except Exception as e:
            print(f"[scheduler] ошибка: {e}")
        await asyncio.sleep(CHECK_INTERVAL)