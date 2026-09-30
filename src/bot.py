"""NoLightToday — Telegram-бот для мониторинга отключений электроэнергии.

В группе бот только получает уведомления.
Все настройки — в личке с ботом, с выбором группы.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    ForumTopicCreated,
    ForumTopicEdited,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
from config import ADMIN_IDS, BOT_USERNAME, BOT_TOKEN, LOCALITIES, TELEGRAM_PROXY
from filters import is_admin, require_admin_callback
from scheduler import format_outage, matches_locality, notify_all, scheduler
from parser import parse_outages


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

from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN, TELEGRAM_PROXY

# На RU VPS Telegram блокируется по SNI — идём через прокси.
# Если TELEGRAM_PROXY пуст — работаем напрямую.
if TELEGRAM_PROXY:
    _session = AiohttpSession(proxy=TELEGRAM_PROXY)
    log.info("Telegram через прокси: %s", TELEGRAM_PROXY.split("@")[-1])
else:
    _session = AiohttpSession()
    log.info("Telegram напрямую (без прокси)")

bot = Bot(token=BOT_TOKEN, session=_session)
dp = Dispatcher()


# =========================================================
#                        УТИЛИТЫ
# =========================================================

def _safe_button_text(text: str, limit: int = 60) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _safe_callback(data: str) -> str:
    b = data.encode("utf-8")
    if len(b) > 64:
        data = b[:64].decode("utf-8", errors="ignore")
    return data


async def safe_edit_message(cb: CallbackQuery, text: str, reply_markup=None) -> None:
    """Редактирует сообщение callback'а; при неудаче — отправляет новое."""
    try:
        await cb.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        log.debug("edit_text не удался (%s), отправляю новое", e)
        try:
            await cb.bot.send_message(
                chat_id=cb.from_user.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        except Exception as e2:
            log.warning("send_message не удался: %s", e2)


async def safe_edit_markup(cb: CallbackQuery, reply_markup) -> None:
    try:
        await cb.message.edit_reply_markup(reply_markup=reply_markup)
    except Exception:
        pass


async def is_group_admin(chat_id: int, user_id: int) -> bool:
    try:
        chat = await bot.get_chat(chat_id)
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        if chat.type == "channel":
            # В канале пользователь-админ должен иметь право постить
            return (
                member.status in ("administrator", "creator")
                and getattr(member, "can_post_messages", False)
            )
        return member.status in ("administrator", "creator")
    except Exception as e:
        log.debug("get_chat_member(%s, %s): %s", chat_id, user_id, e)
        return False


async def chat_kind(chat_id: int) -> str:
    """Возвращает 'group', 'supergroup', 'channel' или 'unknown'."""
    try:
        chat = await bot.get_chat(chat_id)
        return chat.type
    except Exception:
        return "unknown"

async def user_admin_groups(user_id: int) -> list[tuple[int, str]]:
    """Возвращает [(chat_id, title)] — группы, где пользователь админ."""
    all_chats = await db.get_all_chats()
    result: list[tuple[int, str]] = []
    for chat_id, title in all_chats:
        if await is_group_admin(chat_id, user_id):
            result.append((chat_id, title))
    return result


# =========================================================
#                       КЛАВИАТУРЫ
# =========================================================

def groups_kb(groups: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for chat_id, title in groups:
        b.button(
            text=_safe_button_text(f"📢 {title}"),
            callback_data=_safe_callback(f"g:{chat_id}"),
        )
    b.adjust(1)
    return b.as_markup()


def main_menu_kb(chat_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⚙️ Подписки", callback_data=f"m:subs:{chat_id}")
    b.button(text="🏆 Приоритет", callback_data=f"m:prio:{chat_id}")
    b.button(text="📅 Отключения", callback_data=f"m:dates:{chat_id}")
    b.button(text="🎯 Куда писать (подтемы)", callback_data=f"m:topic:{chat_id}")
    b.button(text="ℹ️ Помощь", callback_data=f"m:help:{chat_id}")
    b.button(text="🔄 Сменить чат", callback_data="g:list")
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def back_to_main_kb(chat_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=f"m:main:{chat_id}")
    return b.as_markup()


async def subs_menu_kb(chat_id: int) -> InlineKeyboardMarkup:
    rows = await db.get_subscriptions_with_ids(chat_id)
    subs_map = {loc: sid for sid, loc, _ in rows}

    b = InlineKeyboardBuilder()
    for idx, loc in enumerate(LOCALITIES):
        if loc in subs_map:
            b.button(
                text=_safe_button_text(f"✅ {loc}"),
                callback_data=_safe_callback(f"s:rm:{chat_id}:{subs_map[loc]}"),
            )
        else:
            b.button(
                text=_safe_button_text(f"⬜ {loc}"),
                callback_data=_safe_callback(f"s:add:{chat_id}:{idx}"),
            )
    for sid, loc, _ in rows:
        if loc not in LOCALITIES:
            b.button(
                text=_safe_button_text(f"✅ {loc}"),
                callback_data=_safe_callback(f"s:rm:{chat_id}:{sid}"),
            )
    b.button(text="➕ Добавить свой НП", callback_data=f"s:custom:{chat_id}")
    b.button(text="🗑 Очистить всё", callback_data=f"s:clear:{chat_id}")
    b.button(text="⬅️ Назад", callback_data=f"m:main:{chat_id}")
    b.adjust(1)
    return b.as_markup()


async def prio_menu_kb(chat_id: int) -> tuple[InlineKeyboardMarkup, str]:
    rows = await db.get_subscriptions_with_ids(chat_id)
    b = InlineKeyboardBuilder()
    if not rows:
        b.button(text="⬅️ Назад", callback_data=f"m:main:{chat_id}")
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
            callback_data=_safe_callback(f"p:up:{chat_id}:{sid}"),
        )
        b.button(
            text=_safe_button_text(f"⬇️ {loc}"),
            callback_data=_safe_callback(f"p:down:{chat_id}:{sid}"),
        )
    b.button(text="⬅️ Назад", callback_data=f"m:main:{chat_id}")
    b.adjust(2)
    return b.as_markup(), "\n".join(lines)


async def dates_menu_kb(chat_id: int) -> tuple[InlineKeyboardMarkup, str]:
    dates = await db.get_available_dates()
    b = InlineKeyboardBuilder()
    if not dates:
        b.button(text="⬅️ Назад", callback_data=f"m:main:{chat_id}")
        return (
            b.as_markup(),
            "📭 Данных пока нет.\nДождитесь первой проверки сайта.",
        )
    for d in dates[:20]:
        b.button(
            text=_safe_button_text(f"📅 {d}"),
            callback_data=_safe_callback(f"d:{chat_id}:{d}"),
        )
    b.button(text="⬅️ Назад", callback_data=f"m:main:{chat_id}")
    b.adjust(2)
    return b.as_markup(), "📅 Выберите дату:"

async def topics_menu_kb(chat_id: int) -> InlineKeyboardMarkup:
    topics = await db.get_topics(chat_id)
    current = await db.get_chat_thread(chat_id)

    b = InlineKeyboardBuilder()
    # «Основная» (General) — thread_id отсутствует
    mark = "✅" if current is None else "⬜"
    b.button(
        text=_safe_button_text(f"{mark} 📌 Основная тема"),
        callback_data=f"t:set:{chat_id}:0",
    )
    for tid, name in topics:
        mark = "✅" if current == tid else "⬜"
        b.button(
            text=_safe_button_text(f"{mark} {name}"),
            callback_data=_safe_callback(f"t:set:{chat_id}:{tid}"),
        )
    b.button(text="⬅️ Назад", callback_data=f"m:main:{chat_id}")
    b.adjust(1)
    return b.as_markup()


def help_text() -> str:
    return (
        "ℹ️ <b>Справка</b>\n\n"
        "• <b>⚙️ Подписки</b> — выберите населённые пункты или впишите свой.\n"
        "• <b>🏆 Приоритет</b> — если на одну дату есть отключения в разных НП, "
        "придёт только по «главному» (верхнему).\n"
        "• <b>📅 Отключения</b> — просмотр всех записей на выбранную дату.\n\n"
        "Все настройки применяются к выбранной группе.\n"
        "Уведомления приходят в саму группу."
    )


# =========================================================
#               ДОБАВЛЕНИЕ БОТА В ГРУППУ
# =========================================================

@dp.my_chat_member()
async def on_bot_added_to_chat(update: ChatMemberUpdated):
    chat = update.chat
    if chat.type not in ("group", "supergroup", "channel"):
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status

    if new_status in ("member", "administrator") and old_status in ("left", "kicked"):
        kind = chat.type
        await db.upsert_chat(chat.id, chat.title or "Без названия")
        log.info("Бот добавлен в %s (%s, %s)", chat.title, chat.id, kind)

        deep_link = f"https://t.me/{BOT_USERNAME}?start=g_{chat.id}"

        adder_id = update.from_user.id if update.from_user else None
        if adder_id is not None:
            b = InlineKeyboardBuilder()
            b.button(text="⚙️ Настроить", url=deep_link)
            label = "канал" if kind == "channel" else "группу"
            try:
                await bot.send_message(
                    adder_id,
                    f"🕯 <b>NoLightToday</b> добавлен в {label} "
                    f"<b>{chat.title or 'без названия'}</b>.\n\n"
                    f"Настройки — здесь, в личке.",
                    reply_markup=b.as_markup(),
                    parse_mode="HTML",
                )
            except Exception as e:
                log.info("Не смог написать в личку %s: %s", adder_id, e)

        for admin_id in ADMIN_IDS:
            if admin_id == adder_id:
                continue
            try:
                await bot.send_message(
                    admin_id,
                    f"🕯 Бот добавлен в <b>{chat.title}</b>\n"
                    f"chat_id: <code>{chat.id}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    elif new_status in ("left", "kicked"):
        await db.delete_chat(chat.id)
        log.info("Бот удалён из чата %s (%s)", chat.title, chat.id)


@dp.message(F.forum_topic_created)
async def on_topic_created(message: Message):
    """Ловит создание темы в форуме и запоминает её."""
    if message.chat.type not in ("group", "supergroup"):
        return
    if message.forum_topic_created is None or message.message_thread_id is None:
        return
    await db.upsert_topic(
        message.chat.id,
        message.message_thread_id,
        message.forum_topic_created.name,
    )
    log.info("Тема создана: %s в %s", message.forum_topic_created.name, message.chat.id)


@dp.message(F.forum_topic_edited)
async def on_topic_edited(message: Message):
    """Ловит переименование темы."""
    if message.chat.type not in ("group", "supergroup"):
        return
    if message.forum_topic_edited is None or message.message_thread_id is None:
        return
    new_name = message.forum_topic_edited.name or "без названия"
    await db.upsert_topic(message.chat.id, message.message_thread_id, new_name)


# =========================================================
#                       /start
# =========================================================

@dp.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    chat = message.chat

    # В группе — молчим (приветствие уже ушло при добавлении)
    if chat.type != "private":
        return

    # В личке — показываем список групп
    if not is_admin(message.from_user.id):
        return

    payload = (command.args or "").strip()

    # Deep-link: /start g_<chat_id>
    if payload.startswith("g_"):
        try:
            chat_id = int(payload[2:])
        except ValueError:
            chat_id = None
        if chat_id is not None:
            title = await db.get_chat_title(chat_id)
            if title and await is_group_admin(chat_id, message.from_user.id):
                await db.upsert_chat(chat_id, title)
                await message.answer(
                    f"⚙️ <b>Настройки группы</b>\n<b>{title}</b>\n\n"
                    f"Все изменения будут применяться именно к ней.",
                    reply_markup=main_menu_kb(chat_id),
                    parse_mode="HTML",
                )
                return

    groups = await user_admin_groups(message.from_user.id)
    if not groups:
        await message.answer(
            "🕯 <b>NoLightToday</b>\n\n"
            "Добавьте бота в группу — там появится кнопка для настройки.",
            parse_mode="HTML",
        )
        return

    await message.answer(
        "🕯 <b>NoLightToday</b>\n\nВыберите группу для настройки:",
        reply_markup=groups_kb(groups),
        parse_mode="HTML",
    )


# =========================================================
#                ВЫБОР ГРУППЫ
# =========================================================

@dp.callback_query(F.data == "g:list")
async def cb_group_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только для администратора", show_alert=True)
        return
    await cb.answer()

    groups = await user_admin_groups(cb.from_user.id)
    if not groups:
        await safe_edit_message(
            cb,
            "🕯 Нет групп, где вы админ и где есть бот.",
            reply_markup=None,
        )
        return
    await safe_edit_message(
        cb,
        "Выберите группу для настройки:",
        reply_markup=groups_kb(groups),
    )


@dp.callback_query(F.data.startswith("g:") & ~F.data.startswith("g:list"))
async def cb_group_select(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только для администратора", show_alert=True)
        return
    await cb.answer()

    try:
        chat_id = int(cb.data.split(":", 1)[1])
    except ValueError:
        return

    title = await db.get_chat_title(chat_id)
    if not title or not await is_group_admin(chat_id, cb.from_user.id):
        await safe_edit_message(
            cb, "⛔ Эта группа недоступна.", reply_markup=None
        )
        return

    await safe_edit_message(
        cb,
        f"⚙️ <b>Настройки группы</b>\n<b>{title}</b>\n\n"
        f"Все изменения будут применяться именно к ней.",
        reply_markup=main_menu_kb(chat_id),
    )


# =========================================================
#                НАВИГАЦИЯ ПО МЕНЮ
# =========================================================

async def _guard(cb: CallbackQuery, chat_id: int) -> bool:
    """Проверяет права пользователя на управление группой chat_id."""
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только для администратора", show_alert=True)
        return False
    if not await is_group_admin(chat_id, cb.from_user.id):
        await cb.answer("⛔ Вы не админ этой группы", show_alert=True)
        return False
    return True


@dp.callback_query(F.data.startswith("m:main:"))
async def cb_main(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    await db.clear_awaiting(cb.from_user.id)

    title = await db.get_chat_title(chat_id) or "группа"
    await safe_edit_message(
        cb,
        f"⚙️ <b>Настройки группы</b>\n<b>{title}</b>\n\nВыберите раздел:",
        reply_markup=main_menu_kb(chat_id),
    )


@dp.callback_query(F.data.startswith("m:help:"))
async def cb_help(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    await safe_edit_message(
        cb, help_text(), reply_markup=back_to_main_kb(chat_id)
    )


# ---------- Подписки ----------

@dp.callback_query(F.data.startswith("m:subs:"))
async def cb_subs(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    await db.clear_awaiting(cb.from_user.id)

    kb = await subs_menu_kb(chat_id)
    await safe_edit_message(
        cb,
        "⚙️ <b>Подписки</b>\nОтметьте НП (можно несколько) или добавьте свой:",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("s:add:"))
async def cb_subs_add(cb: CallbackQuery):
    parts = cb.data.split(":")
    chat_id = int(parts[2])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    try:
        idx = int(parts[3])
    except (ValueError, IndexError):
        return
    if not (0 <= idx < len(LOCALITIES)):
        return
    await db.toggle_subscription(chat_id, LOCALITIES[idx])
    await safe_edit_markup(cb, await subs_menu_kb(chat_id))


@dp.callback_query(F.data.startswith("s:rm:"))
async def cb_subs_rm(cb: CallbackQuery):
    parts = cb.data.split(":")
    chat_id = int(parts[2])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    try:
        sid = int(parts[3])
    except (ValueError, IndexError):
        return
    await db.delete_subscription_by_id(chat_id, sid)
    await safe_edit_markup(cb, await subs_menu_kb(chat_id))


@dp.callback_query(F.data.startswith("s:clear:"))
async def cb_subs_clear(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer("Все подписки удалены")
    await db.clear_subscriptions(chat_id)
    await safe_edit_markup(cb, await subs_menu_kb(chat_id))


# ---------- Ручной ввод НП ----------

@dp.callback_query(F.data.startswith("s:custom:"))
async def cb_subs_custom(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()

    # awaiting по user_id, но помним chat_id группы
    await db.set_awaiting(cb.from_user.id, chat_id, "locality")

    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data=f"s:cancel:{chat_id}")
    await safe_edit_message(
        cb,
        "✏️ <b>Свой населённый пункт</b>\n\n"
        "Отправьте название следующим сообщением.\n\n"
        "<b>Примеры:</b>\n"
        "• <code>СНТ Фауна</code>\n"
        "• <code>Петровское</code>\n"
        "• <code>Ломоносовский</code>",
        reply_markup=b.as_markup(),
    )


@dp.callback_query(F.data.startswith("s:cancel:"))
async def cb_subs_cancel(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    await db.clear_awaiting(cb.from_user.id)

    kb = await subs_menu_kb(chat_id)
    await safe_edit_message(
        cb,
        "⚙️ <b>Подписки</b>\nОтметьте НП (можно несколько) или добавьте свой:",
        reply_markup=kb,
    )


# ---------- Приоритет ----------

@dp.callback_query(F.data.startswith("m:prio:"))
async def cb_prio(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    kb, text = await prio_menu_kb(chat_id)
    await safe_edit_message(cb, text, reply_markup=kb)


@dp.callback_query(F.data.startswith("p:up:") | F.data.startswith("p:down:"))
async def cb_prio_move(cb: CallbackQuery):
    parts = cb.data.split(":")
    direction = parts[1]
    chat_id = int(parts[2])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    try:
        sid = int(parts[3])
    except (ValueError, IndexError):
        return

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


# ---------- Отключения ----------

@dp.callback_query(F.data.startswith("m:dates:"))
async def cb_dates(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()
    kb, text = await dates_menu_kb(chat_id)
    await safe_edit_message(cb, text, reply_markup=kb)


@dp.callback_query(F.data.startswith("d:"))
async def cb_date_show(cb: CallbackQuery):
    # d:<chat_id>:<date_key>
    parts = cb.data.split(":", 2)
    chat_id = int(parts[1])
    date_key = parts[2]
    if not await _guard(cb, chat_id):
        return
    await cb.answer()

    cached = await db.get_cache_by_date(date_key)
    subs = await db.get_subscribed_localities(chat_id)
    items = [o for o in cached if any(matches_locality(o, loc) for loc in subs)]

    if not items:
        text = f"📭 На {date_key} по вашим НП отключений нет."
    else:
        text = f"📅 <b>Отключения на {date_key}</b>\n\n" + "\n\n".join(
            format_outage(o) for o in items
        )
        if len(text) > 4000:
            text = text[:3980] + "\n…обрезано"

    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=f"m:dates:{chat_id}")
    await safe_edit_message(cb, text, reply_markup=b.as_markup())

# ---------- Раздел «Куда писать» (тема форума) ----------

@dp.callback_query(F.data.startswith("m:topic:"))
async def cb_topic_menu(cb: CallbackQuery):
    chat_id = int(cb.data.rsplit(":", 1)[1])
    if not await _guard(cb, chat_id):
        return
    await cb.answer()

    kind = await chat_kind(chat_id)
    if kind not in ("group", "supergroup"):
        await safe_edit_message(
            cb,
            "ℹ️ Выбор темы доступен только в форумах (супергруппах с темами).",
            reply_markup=back_to_main_kb(chat_id),
        )
        return

    kb = await topics_menu_kb(chat_id)
    await safe_edit_message(
        cb,
        "🎯 <b>Куда писать уведомления</b>\n\n"
        "Выберите тему форума. Если бот её не видит — создайте тему при боте, "
        "он её запомнит.",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("t:set:"))
async def cb_topic_set(cb: CallbackQuery):
    parts = cb.data.split(":")
    chat_id = int(parts[2])
    thread_id = int(parts[3]) or None   # 0 → None
    if not await _guard(cb, chat_id):
        return
    await cb.answer("Сохранено")

    await db.set_chat_thread(chat_id, thread_id)

    kb = await topics_menu_kb(chat_id)
    await safe_edit_markup(cb, kb)

@dp.message(Command("topic"))
async def cmd_register_topic(message: Message, command: CommandObject):
    """Сохраняет текущую тему форума под указанным именем.

    Использование: внутри темы отправить
        /topic Отключения
    """
    if message.chat.type not in ("group", "supergroup"):
        return
    thread_id = getattr(message, "message_thread_id", None)
    if not thread_id:
        await message.answer(
            "Команда работает только внутри темы форума.",
            message_thread_id=None,
        )
        return
    name = (command.args or "").strip() or "Без названия"
    await db.upsert_topic(message.chat.id, thread_id, name)
    await message.answer(
        f"✅ Тема зарегистрирована: <b>{name}</b> (thread_id={thread_id})",
        message_thread_id=thread_id,
        parse_mode="HTML",
    )
    log.info("Тема зарегистрирована вручную: %s (%s) в %s",
             name, thread_id, message.chat.id)


# =========================================================
#                ВВОД НАЗВАНИЯ НП (в личке)
# =========================================================
async def _check_locality_now(chat_id: int, locality: str) -> tuple[int, list[str]]:
    """Парсит сайт по одному НП и обновляет кэш.

    Возвращает (количество_записей, отсортированные_даты).
    Если парсинг упал — вернёт (-1, []).
    """
    try:
        records = parse_outages(street=locality, max_pages=2)
    except Exception as e:
        log.warning("parse_outages('%s') упал: %s", locality, e)
        return -1, []

    if not records:
        return 0, []

    try:
        await db.save_cache(records)
    except Exception as e:
        log.warning("save_cache упал: %s", e)

    # Сразу рассылаем уведомления всем подписанным
    try:
        await notify_all(bot, records)
    except Exception as e:
        log.warning("notify_all после проверки упал: %s", e)

    dates = sorted({r["date_key"] for r in records})
    return len(records), dates


@dp.message(F.text, ~F.text.startswith("/"))
async def fallback_text(message: Message):
    """В личке принимает ввод названия НП, если ждём.

    В группе молчит.
    """
    # В группе — молчим всегда
    if message.chat.type in ("group", "supergroup"):
        return

    # В личке — только админам
    if not is_admin(message.from_user.id):
        return

    awaiting = await db.get_awaiting(message.from_user.id)
    if awaiting is None:
        return

    chat_id, kind = awaiting
    if kind != "locality":
        return

    await db.clear_awaiting(message.from_user.id)

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пустая строка. Нажмите «➕ Добавить свой НП» снова.")
        return
    if len(text) > 100:
        await message.answer("Слишком длинное название (максимум 100 символов).")
        return

    # Добавляем подписку
    await db.toggle_subscription(chat_id, text)

    # Сразу проверяем — есть ли что-то на сайте по этому НП
    info = await message.answer(f"🔍 Проверяю сайт по «{text}»…")

    try:
        count, dates = await _check_locality_now(chat_id, text)
    except Exception as e:
        log.warning("Автопроверка '%s' упала: %s", text, e)
        count, dates = -1, []

    # Убираем «Проверяю…»
    try:
        await info.delete()
    except Exception:
        pass

    # Формируем итог
    if count > 0:
        dates_str = ", ".join(d.replace("-", ".") for d in dates[:5])
        if len(dates) > 5:
            dates_str += "…"
        hint = (
            f"✅ Найдено <b>{count}</b> записей на даты: {dates_str}\n"
            f"Уведомления уже отправлены в чат."
        )
    elif count == 0:
        hint = (
            "⚠️ На сайте пока нет отключений по этому НП. "
            "Если появятся — бот пришлёт уведомление при следующей проверке."
        )
    else:
        hint = (
            "⚠️ Не удалось получить данные с сайта. "
            "Подписка сохранена, проверка будет в следующий цикл."
        )

    kb = await subs_menu_kb(chat_id)
    await message.answer(
        f"✅ Добавлено: <b>{text}</b>\n{hint}\n\n"
        f"⚙️ <b>Подписки</b> — отметьте НП или добавьте свой:",
        reply_markup=kb,
        parse_mode="HTML",
    )


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