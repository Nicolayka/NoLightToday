import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import db
from config import BOT_TOKEN, LOCALITIES
from filters import is_admin, require_admin_callback, require_admin_message
from scheduler import format_outage, scheduler

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
#                       КЛАВИАТУРЫ
# =========================================================

def reply_menu_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text="📋 Меню")
    return b.as_markup(resize_keyboard=True)


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⚙️ Подписки", callback_data="menu:subs")
    b.button(text="🏆 Приоритет", callback_data="menu:prio")
    b.button(text="📅 Отключения", callback_data="menu:dates")
    b.button(text="ℹ️ Помощь", callback_data="menu:help")
    b.adjust(2, 2)
    return b.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data="menu:main")
    return b.as_markup()


async def subs_menu_kb(chat_id: int) -> InlineKeyboardMarkup:
    subs = await db.get_subscribed_localities(chat_id)
    b = InlineKeyboardBuilder()
    for loc in LOCALITIES:
        mark = "✅" if loc in subs else "⬜"
        b.button(text=f"{mark} {loc}", callback_data=f"subs:toggle:{loc}")
    b.button(text="🗑 Очистить всё", callback_data="subs:clear")
    b.button(text="⬅️ Назад", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


async def prio_menu_kb(chat_id: int) -> tuple[InlineKeyboardMarkup, str]:
    rows = await db.get_subscriptions_with_ids(chat_id)
    b = InlineKeyboardBuilder()
    if not rows:
        b.button(text="⬅️ Назад", callback_data="menu:main")
        return (
            b.as_markup(),
            "📭 Подписок пока нет.\nСначала выберите НП в разделе «⚙️ Подписки».",
        )

    lines = [
        "🏆 <b>Порядок НП</b>",
        "Сверху — главный: если на одну дату есть отключения в нескольких НП, "
        "придёт уведомление только по нему.\n",
    ]
    for i, (_sid, loc, _p) in enumerate(rows):
        lines.append(f"{i + 1}. {loc}")

    for sid, loc, _prio in rows:
        b.button(text=f"⬆️ {loc}", callback_data=f"prio:up:{sid}")
        b.button(text=f"⬇️ {loc}", callback_data=f"prio:down:{sid}")
    b.button(text="⬅️ Назад", callback_data="menu:main")
    b.adjust(2)
    return b.as_markup(), "\n".join(lines)


async def dates_menu_kb() -> tuple[InlineKeyboardMarkup, str]:
    dates = await db.get_available_dates()
    b = InlineKeyboardBuilder()
    if not dates:
        b.button(text="⬅️ Назад", callback_data="menu:main")
        return (
            b.as_markup(),
            "📭 Данных пока нет.\nДождитесь первой проверки сайта.",
        )
    for d in dates[:20]:
        b.button(text=f"📅 {d}", callback_data=f"date:{d}")
    b.button(text="⬅️ Назад", callback_data="menu:main")
    b.adjust(2)
    return b.as_markup(), "📅 Выберите дату:"


def help_text() -> str:
    return (
        "ℹ️ <b>Справка</b>\n\n"
        "• <b>⚙️ Подписки</b> — выберите населённые пункты, за которыми следит бот.\n"
        "• <b>🏆 Приоритет</b> — если на одну дату есть отключения в нескольких НП, "
        "уведомление придёт только по «главному» (верхнему). Остальные доступны "
        "в разделе «📅 Отключения».\n"
        "• <b>📅 Отключения</b> — просмотр всех записей по вашим НП на выбранную дату.\n\n"
        "⚙️ Управление доступно только администратору."
    )


# =========================================================
#                ТОЧКА ВХОДА (публичное)
# =========================================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🕯 <b>NoLightToday</b>\n\n"
        "Бот следит за плановыми отключениями электроэнергии "
        "на сайте Россети Ленэнерго и присылает уведомления в группу.\n\n"
        "Нажмите «📋 Меню», чтобы открыть настройки.\n"
        "Управление доступно только администратору.",
        reply_markup=reply_menu_kb(),
        parse_mode="HTML",
    )


@dp.message(F.text == "📋 Меню")
@dp.message(Command("menu"))
async def open_menu(message: Message):
    if not await require_admin_message(message):
        return
    await message.answer(
        "📋 <b>Главное меню</b>\nВыберите раздел:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


# =========================================================
#                НАВИГАЦИЯ ПО МЕНЮ
# =========================================================

@dp.callback_query(F.data == "menu:main")
async def cb_main(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.message.edit_text(
        "📋 <b>Главное меню</b>\nВыберите раздел:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
    await cb.answer()


@dp.callback_query(F.data == "menu:help")
async def cb_help(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.message.edit_text(
        help_text(), reply_markup=back_to_main_kb(), parse_mode="HTML"
    )
    await cb.answer()


# ---------- Раздел «Подписки» ----------

@dp.callback_query(F.data == "menu:subs")
async def cb_subs(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    kb = await subs_menu_kb(cb.message.chat.id)
    await cb.message.edit_text(
        "⚙️ <b>Подписки</b>\nОтметьте населённые пункты (можно несколько):",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await cb.answer()


@dp.callback_query(F.data.startswith("subs:toggle:"))
async def cb_subs_toggle(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    loc = cb.data.split(":", 2)[2]
    now_subscribed = await db.toggle_subscription(cb.message.chat.id, loc)
    kb = await subs_menu_kb(cb.message.chat.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await cb.answer(f"{loc}: {'вкл' if now_subscribed else 'выкл'}")


@dp.callback_query(F.data == "subs:clear")
async def cb_subs_clear(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await db.clear_subscriptions(cb.message.chat.id)
    kb = await subs_menu_kb(cb.message.chat.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await cb.answer("Все подписки удалены")


# ---------- Раздел «Приоритет» ----------

@dp.callback_query(F.data == "menu:prio")
async def cb_prio(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    kb, text = await prio_menu_kb(cb.message.chat.id)
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data.startswith("prio:"))
async def cb_prio_move(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    _, direction, sid = cb.data.split(":")
    sid = int(sid)
    chat_id = cb.message.chat.id

    rows = await db.get_subscriptions_with_ids(chat_id)
    ids = [r[0] for r in rows]
    if sid not in ids:
        await cb.answer("Не найдено")
        return
    idx = ids.index(sid)
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_idx < len(ids):
        await db.swap_priority(chat_id, sid, ids[swap_idx])

    kb, text = await prio_menu_kb(chat_id)
    try:
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await cb.answer("Порядок обновлён")


# ---------- Раздел «Отключения» ----------

@dp.callback_query(F.data == "menu:dates")
async def cb_dates(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    kb, text = await dates_menu_kb()
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@dp.callback_query(F.data.startswith("date:"))
async def cb_date_show(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    date_key = cb.data.split(":", 1)[1]
    chat_id = cb.message.chat.id

    cached = await db.get_cache_by_date(date_key)
    subs = await db.get_subscribed_localities(chat_id)
    subs_lower = {s.lower() for s in subs}
    items = [
        o for o in cached
        if any(loc in o["locality"].lower() for loc in subs_lower)
    ]

    if not items:
        text = f"📭 На {date_key} по вашим НП отключений нет."
    else:
        text = f"📅 <b>Отключения на {date_key}</b>\n\n" + "\n\n".join(
            format_outage(o) for o in items
        )
        if len(text) > 4000:
            text = text[:3980] + "\n…обрезано"

    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data="menu:dates")
    try:
        await cb.message.edit_text(
            text, reply_markup=b.as_markup(), parse_mode="HTML"
        )
    except Exception:
        pass
    await cb.answer()


# =========================================================
#                        ЗАПУСК
# =========================================================

async def main():
    await db.init_db()
    asyncio.create_task(scheduler(bot))
    print(f"🕯 NoLightToday запущен. Файл БД: {db.DB_PATH}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())