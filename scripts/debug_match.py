"""Диагностика: что лежит в БД, что в кэше, кто с кем матчится.

Использование:
    .venv\\Scripts\\python.exe scripts\\debug_match.py
    .venv\\Scripts\\python.exe scripts\\debug_match.py 30-09-2026
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db                                                   # noqa: E402
from scheduler import matches_locality                      # noqa: E402


async def main():
    date_key = sys.argv[1] if len(sys.argv) > 1 else "30-09-2026"

    await db.init_db()

    # 1. Все подписки
    async with db.aiosqlite.connect(db.DB_PATH) as conn:
        async with conn.execute(
            "SELECT chat_id, locality, priority FROM subscriptions ORDER BY chat_id, priority"
        ) as cur:
            subs = await cur.fetchall()

    print(f"\n=== ПОДПИСКИ ({len(subs)}) ===")
    for chat_id, loc, prio in subs:
        # repr покажет пробелы/невидимые символы
        print(f"  chat={chat_id}  locality={loc!r}  priority={prio}")

    # 2. Записи из кэша на указанную дату
    records = await db.get_cache_by_date(date_key)
    print(f"\n=== КЭШ НА {date_key} ({len(records)} записей) ===")
    for i, r in enumerate(records):
        print(
            f"  [{i}] district={r.get('district','')!r}\n"
            f"       address={r.get('address','')!r}\n"
            f"       start={r.get('start','')!r}"
        )

    # 3. Проверяем матчинг
    print(f"\n=== МАТЧИНГ ===")
    for _chat, loc, _prio in subs:
        matched = [r for r in records if matches_locality(r, loc)]
        status = "✅" if matched else "❌"
        print(f"  {status} '{loc}' → найдено {len(matched)} из {len(records)}")

    # 4. Сводка по всем датам кэша
    async with db.aiosqlite.connect(db.DB_PATH) as conn:
        async with conn.execute(
            "SELECT date_key, COUNT(*) FROM outage_cache GROUP BY date_key ORDER BY date_key"
        ) as cur:
            dates = await cur.fetchall()
    print(f"\n=== ВСЕ ДАТЫ В КЭШЕ ===")
    for d, cnt in dates:
        print(f"  {d}  →  {cnt} записей")


if __name__ == "__main__":
    asyncio.run(main())