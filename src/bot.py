"""NoLightToday — Telegram-бот для мониторинга отключений электроэнергии."""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import db
from config import ADMIN_IDS, BOT_TOKEN, LOCALITIES
from filters import require_admin_callback, require_admin_message
from scheduler import format_outage, matches_locality, scheduler


# =========================================================
#                       ЛОГИРОВАНИЕ
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("nolighttoday")


# =========================================================
#                          БОТ
# =========================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
#                        УТИЛИТЫ
# =========================================================

def _safe_button_text(text: str, limit: int = 60) -> str:
    """Обрезает текст кнопки до лимита Telegram (64 символа)."""
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _safe_callback(data: str) -> str:
    """Проверяет, что callback_data укладывается в 64 байта Telegram."""
    b = data.encode("utf-8")
    if len(b) > 64:
        data = b[:64].decode("utf-8", errors="ignore")
    return data


def _chat_id_from_cb(cb: CallbackQuery) -> int:
    """Возвращает chat_id из callback'а даже для InaccessibleMessage."""
    if cb.message is not None:
        return cb.message.chat.id
    return cb.from_user.id


async def safe_edit_message(
    cb: CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode: str | None = "HTML",
) -> None:
    """Безопасно редактирует сообщение callback'а.

    Если сообщение недоступно (слишком старое) — отправляет новое в тот же чат.
    """
    try:
        await cb.message.edit_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode
        )
    except Exception as e:
        log.debug("edit_text не удался (%s), отправляю новое сообщение", e)
        try:
            await cb.bot.send_message(
                chat_id=_chat_id_from_cb(cb),
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception as e2:
            log.warning("Не удалось отправить сообщение: %s", e2)


async def safe_edit_markup(cb: CallbackQuery, reply_markup) -> None:
    """Безопасно обновляет клавиатуру сообщения callback'а."""
    try:
        await cb.message.edit_reply_markup(reply_markup=reply_markup)
    except Exception:
        # Недоступно — ничего страшного, пользователь увидит актуальное
        # состояние при следующем действии
        pass


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
    rows = await db.get_subscriptions_with_ids(chat_id)
    subs_map = {loc: sid for sid, loc, _ in rows}

    b = InlineKeyboardBuilder()

    # 1. Предустановленные НП из config
    for idx, loc in enumerate(LOCALITIES):
        if loc in subs_map:
            b.button(
                text=_safe_button_text(f"✅ {loc}"),
                callback_data=_safe_callback(f"subs:rm:{subs_map[loc]}"),
            )
        else:
            b.button(
                text=_safe_button_text(f"⬜ {loc}"),
                callback_data=_safe_callback(f"subs:add:{idx}"),
            )

    # 2. Кастомные НП из БД (не входящие в LOCALITIES)
    for sid, loc, _ in rows:
        if loc not in LOCALITIES:
            b.button(
                text=_safe_button_text(f"✅ {loc}"),
                callback_data=_safe_callback(f"subs:rm:{sid}"),
            )

    # 3. Служебные кнопки
    b.button(text="➕ Добавить свой НП", callback_data="subs:custom")
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
        b.button(
            text=_safe_button_text(f"⬆️ {loc}"),
            callback_data=_safe_callback(f"prio:up:{sid}"),
        )
        b.button(
            text=_safe_button_text(f"⬇️ {loc}"),
            callback_data=_safe_callback(f"prio:down:{sid}"),
        )
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
        b.button(
            text=_safe_button_text(f"📅 {d}"),
            callback_data=_safe_callback(f"date:{d}"),
        )
    b.button(text="⬅️ Назад", callback_data="menu:main")
    b.adjust(2)
    return b.as_markup(), "📅 Выберите дату:"


def help_text() -> str:
    return (
        "ℹ️ <b>Справка</b>\n\n"
        "• <b>⚙️ Подписки</b> — выберите населённые пункты или впишите свой "
        "(например, «СНТ Фауна» или «Петровское»). Поиск идёт по району и адресу.\n"
        "• <b>🏆 Приоритет</b> — если на одну дату есть отключения в нескольких НП, "
        "уведомление придёт только по «главному» (верхнему).\n"
        "• <b>📅 Отключения</b> — просмотр всех записей по вашим НП на выбранную дату.\n\n"
        "⚙️ Управление доступно только администратору."
    )


# =========================================================
#                ТОЧКА ВХОДА (публичное)
# =========================================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    chat = message.chat

    if chat.type in ("group", "supergroup"):
        await db.upsert_chat(chat.id, chat.title or "Группа")
        b = InlineKeyboardBuilder()
        b.button(
            text=_safe_button_text(f"⚙️ Настроить: {chat.title or 'группу'}"),
            callback_data="grp:open",
        )
        await message.answer(
            f"🕯 <b>NoLightToday</b>\n\n"
            f"Бот следит за плановыми отключениями электроэнергии "
            f"на сайте Россети Ленэнерго.\n"
            f"Группа: <b>{chat.title or 'без названия'}</b>\n\n"
            f"Нажмите кнопку ниже, чтобы открыть настройки, "
            f"или используйте reply-кнопку «📋 Меню».",
            reply_markup=reply_menu_kb(),
            parse_mode="HTML",
        )
        await message.answer(
            "Настройки группы:",
            reply_markup=b.as_markup(),
        )
        return

    # личка
    await message.answer(
        "🕯 <b>NoLightToday</b>\n\n"
        "Добавьте бота в группу — там появятся настройки отслеживания "
        "отключений.",
        parse_mode="HTML",
    )


# =========================================================
#               ДОБАВЛЕНИЕ БОТА В ГРУППУ
# =========================================================

@dp.my_chat_member()
async def on_bot_added_to_chat(update: ChatMemberUpdated):
    """Ловит добавление и удаление бота в группе."""
    chat = update.chat
    if chat.type not in ("group", "supergroup"):
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    # --- Бот добавлен в группу ---
    if new_status in ("member", "administrator") and old_status in ("left", "kicked"):
        await db.upsert_chat(chat.id, chat.title or "Группа")

        b = InlineKeyboardBuilder()
        b.button(
            text=_safe_button_text(f"⚙️ Настроить: {chat.title or 'группу'}"),
            callback_data="grp:open",
        )
        try:
            await bot.send_message(
                chat.id,
                f"🕯 <b>NoLightToday</b> подключён к группе "
                f"<b>{chat.title or 'без названия'}</b>.\n\n"
                f"Нажмите кнопку ниже, чтобы выбрать населённые пункты "
                f"и настроить отслеживание отключений.",
                reply_markup=b.as_markup(),
                parse_mode="HTML",
            )
        except Exception as e:
            log.warning("Не удалось отправить приветствие в %s: %s", chat.id, e)

        # Уведомим админов в личку
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🕯 Бот добавлен в группу <b>{chat.title}</b>\n"
                    f"chat_id: <code>{chat.id}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass  # админ не начинал диалог с ботом

    # --- Бот удалён из группы ---
    elif new_status in ("left", "kicked"):
        await db.delete_chat(chat.id)
        log.info("Бот удалён из группы %s (%s)", chat.title, chat.id)


@dp.message(Command("setup"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_setup(message: Message):
    """Ручной вызов приветствия с кнопкой настроек."""
    if not await require_admin_message(message):
        return

    chat = message.chat
    await db.upsert_chat(chat.id, chat.title or "Группа")

    b = InlineKeyboardBuilder()
    b.button(
        text=_safe_button_text(f"⚙️ Настроить: {chat.title or 'группу'}"),
        callback_data="grp:open",
    )
    await message.answer(
        f"⚙️ Настройки группы <b>{chat.title}</b>:",
        reply_markup=b.as_markup(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "grp:open")
async def cb_group_open(cb: CallbackQuery):
    """Открывает меню настроек для группы, где нажата кнопка."""
    if not await require_admin_callback(cb):
        return
    await cb.answer()

    chat = cb.message.chat if cb.message is not None else None
    if chat is None or chat.type not in ("group", "supergroup"):
        await safe_edit_message(
            cb,
            "Эта кнопка работает только в группе. "
            "Добавьте бота в группу и нажмите её там.",
            reply_markup=None,
        )
        return

    await db.upsert_chat(chat.id, chat.title or "Группа")

    await safe_edit_message(
        cb,
        f"⚙️ <b>Настройки группы</b>\n"
        f"<b>{chat.title or 'без названия'}</b>\n\n"
        f"Все изменения будут применяться именно к этой группе.\n\n"
        f"Выберите раздел:",
        reply_markup=main_menu_kb(),
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
    await cb.answer()

    chat_id = _chat_id_from_cb(cb)
    await db.clear_awaiting(chat_id)

    await safe_edit_message(
        cb,
        "📋 <b>Главное меню</b>\nВыберите раздел:",
        reply_markup=main_menu_kb(),
    )


@dp.callback_query(F.data == "menu:help")
async def cb_help(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()
    await safe_edit_message(
        cb, help_text(), reply_markup=back_to_main_kb()
    )


# ---------- Раздел «Подписки» ----------

@dp.callback_query(F.data == "menu:subs")
async def cb_subs(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()

    chat_id = _chat_id_from_cb(cb)
    await db.clear_awaiting(chat_id)

    kb = await subs_menu_kb(chat_id)
    await safe_edit_message(
        cb,
        "⚙️ <b>Подписки</b>\nОтметьте населённые пункты (можно несколько) "
        "или добавьте свой:",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("subs:add:"))
async def cb_subs_add(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()
    try:
        idx = int(cb.data.split(":")[-1])
    except ValueError:
        return
    if not (0 <= idx < len(LOCALITIES)):
        return
    loc = LOCALITIES[idx]
    chat_id = _chat_id_from_cb(cb)
    if cb.message is not None:
        await db.upsert_chat(chat_id, cb.message.chat.title or "Группа")
    await db.toggle_subscription(chat_id, loc)
    kb = await subs_menu_kb(chat_id)
    await safe_edit_markup(cb, kb)


@dp.callback_query(F.data.startswith("subs:rm:"))
async def cb_subs_rm(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()
    try:
        sid = int(cb.data.split(":")[-1])
    except ValueError:
        return
    chat_id = _chat_id_from_cb(cb)
    await db.delete_subscription_by_id(chat_id, sid)
    kb = await subs_menu_kb(chat_id)
    await safe_edit_markup(cb, kb)


@dp.callback_query(F.data == "subs:clear")
async def cb_subs_clear(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer("Все подписки удалены")
    chat_id = _chat_id_from_cb(cb)
    await db.clear_subscriptions(chat_id)
    kb = await subs_menu_kb(chat_id)
    await safe_edit_markup(cb, kb)


# ---------- Ручной ввод НП ----------

@dp.callback_query(F.data == "subs:custom")
async def cb_subs_custom(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()

    chat_id = _chat_id_from_cb(cb)
    await db.set_awaiting(chat_id, cb.from_user.id, "locality")

    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data="subs:custom_cancel")
    await safe_edit_message(
        cb,
        "✏️ <b>Свой населённый пункт</b>\n\n"
        "Введите название (можно часть). Бот ищет совпадение в полях\n"
        "«Район / Населённый пункт» и «Адрес».\n\n"
        "<b>Примеры:</b>\n"
        "• <code>СНТ Фауна</code>\n"
        "• <code>Петровское</code>\n"
        "• <code>Ломоносовский</code>\n\n"
        "Отправьте название следующим сообщением.",
        reply_markup=b.as_markup(),
    )


@dp.callback_query(F.data == "subs:custom_cancel")
async def cb_subs_custom_cancel(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()

    chat_id = _chat_id_from_cb(cb)
    await db.clear_awaiting(chat_id)

    kb = await subs_menu_kb(chat_id)
    await safe_edit_message(
        cb,
        "⚙️ <b>Подписки</b>\nОтметьте населённые пункты (можно несколько) "
        "или добавьте свой:",
        reply_markup=kb,
    )


async def _add_locality_and_reply(
    chat_id: int, text: str
) -> tuple[str, InlineKeyboardMarkup]:
    """Общая логика добавления НП. Возвращает (текст, клавиатура)."""
    all_dates = await db.get_available_dates()
    has_any = False
    for d in all_dates:
        cached = await db.get_cache_by_date(d)
        if any(matches_locality(o, text) for o in cached):
            has_any = True
            break

    await db.toggle_subscription(chat_id, text)
    kb = await subs_menu_kb(chat_id)

    if has_any:
        hint = "✅ Совпадения в текущем кэше найдены — уведомления будут приходить."
    else:
        hint = (
            "⚠️ В текущем кэше совпадений пока нет. "
            "Если это ожидаемо (отключений ещё не публиковали) — всё в порядке."
        )

    text_msg = (
        f"✅ Добавлено: <b>{text}</b>\n{hint}\n\n"
        f"⚙️ <b>Подписки</b>\nОтметьте населённые пункты (можно несколько) "
        f"или добавьте свой:"
    )
    return text_msg, kb


# ---------- Раздел «Приоритет» ----------

@dp.callback_query(F.data == "menu:prio")
async def cb_prio(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()
    kb, text = await prio_menu_kb(_chat_id_from_cb(cb))
    await safe_edit_message(cb, text, reply_markup=kb)


@dp.callback_query(F.data.startswith("prio:"))
async def cb_prio_move(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()
    _, direction, sid = cb.data.split(":")
    sid = int(sid)
    chat_id = _chat_id_from_cb(cb)

    rows = await db.get_subscriptions_with_ids(chat_id)
    ids = [r[0] for r in rows]
    if sid not in ids:
        return
    idx = ids.index(sid)
    swap_idx = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap_idx < len(ids):
        await db.swap_priority(chat_id, sid, ids[swap_idx])

    kb, text = await prio_menu_kb(chat_id)
    await safe_edit_message(cb, text, reply_markup=kb)


# ---------- Раздел «Отключения» ----------

@dp.callback_query(F.data == "menu:dates")
async def cb_dates(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()
    kb, text = await dates_menu_kb()
    await safe_edit_message(cb, text, reply_markup=kb)


@dp.callback_query(F.data.startswith("date:"))
async def cb_date_show(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()
    date_key = cb.data.split(":", 1)[1]
    chat_id = _chat_id_from_cb(cb)

    cached = await db.get_cache_by_date(date_key)
    subs = await db.get_subscribed_localities(chat_id)
    items = [
        o for o in cached
        if any(matches_locality(o, loc) for loc in subs)
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
    await safe_edit_message(cb, text, reply_markup=b.as_markup())


# =========================================================
#                ВВОД НАЗВАНИЯ НП (без FSM)
# =========================================================

@dp.message(F.text, ~F.text.startswith("/"))
async def fallback_text(message: Message):
    """Ловит любой текст от админа.

    1) Если БД говорит «ждём ввод» — добавляем НП.
    2) Иначе — предлагаем подтвердить добавление через кнопку.
    """
    if not await require_admin_message(message):
        return

    text = (message.text or "").strip()

    # Reply-кнопка «📋 Меню» ловится хендлером выше — здесь пропускаем
    if text == "📋 Меню":
        return

    chat_id = message.chat.id

    # 1) Ждём ввод от этого чата?
    awaiting = await db.get_awaiting(chat_id)
    if awaiting is not None:
        _user_id, kind = awaiting
        if kind == "locality":
            await db.clear_awaiting(chat_id)
            if not text:
                await message.answer(
                    "Пустая строка. Введите название или нажмите «Отмена»."
                )
                return
            if len(text) > 100:
                await message.answer(
                    "Слишком длинное название (максимум 100 символов)."
                )
                return

            await db.upsert_chat(chat_id, message.chat.title or "Группа")
            reply_text, kb = await _add_locality_and_reply(chat_id, text)
            await message.answer(
                reply_text, reply_markup=kb, parse_mode="HTML"
            )
            return

    # 2) Обычный текст — предложим добавить НП
    looks_like_locality = (
        0 < len(text) <= 100
        and "http" not in text.lower()
        and "\n" not in text
    )
    if looks_like_locality:
        b = InlineKeyboardBuilder()
        b.button(
            text=_safe_button_text(f"✅ Да, добавить «{text}»"),
            callback_data=_safe_callback(f"confirm_add:{text}"),
        )
        b.button(text="❌ Отмена", callback_data="menu:main")
        b.adjust(1)
        await message.answer(
            f"Добавить населённый пункт <b>{text}</b> "
            f"в подписки этого чата?",
            reply_markup=b.as_markup(),
            parse_mode="HTML",
        )
        return

    await message.answer(
        "Не понял команду. Откройте «📋 Меню → ⚙️ Подписки», "
        "чтобы управлять отслеживанием."
    )


@dp.callback_query(F.data.startswith("confirm_add:"))
async def cb_confirm_add(cb: CallbackQuery):
    if not await require_admin_callback(cb):
        return
    await cb.answer()

    loc = cb.data.split(":", 1)[1].strip()
    if not loc:
        return

    chat_id = _chat_id_from_cb(cb)
    if cb.message is not None:
        await db.upsert_chat(chat_id, cb.message.chat.title or "Группа")

    reply_text, kb = await _add_locality_and_reply(chat_id, loc)
    await safe_edit_message(cb, reply_text, reply_markup=kb)


# =========================================================
#                        ЗАПУСК
# =========================================================

async def main():
    await db.init_db()
    asyncio.create_task(scheduler(bot))
    print(f"🕯 NoLightToday запущен. Файл БД: {db.DB_PATH}")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


if __name__ == "__main__":
    asyncio.run(main())