"""Фильтры и утилиты проверки прав."""

from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS


def is_admin(user_id: int) -> bool:
    """Тихая проверка: является ли пользователь администратором."""
    return user_id in ADMIN_IDS


async def require_admin_message(message: Message, *, silent: bool = True) -> bool:
    """Проверяет, что отправитель — админ.

    silent=True (по умолчанию) — молча возвращает False, ничего не отправляя.
    silent=False — отвечает «Управление доступно только администратору».

    Используйте silent=False только для команд, где ответ уместен
    (например, в личке). В группах — всегда silent=True, чтобы не спамить.
    """
    if is_admin(message.from_user.id):
        return True
    if not silent:
        await message.answer("⛔ Управление доступно только администратору.")
    return False


async def require_admin_callback(cb: CallbackQuery) -> bool:
    """Проверяет, что нажатие кнопки — от админа.

    Показывает всплывающее окно (show_alert) только нажавшему.
    В чат ничего не пишет.
    """
    if is_admin(cb.from_user.id):
        return True
    await cb.answer("⛔ Только администратор", show_alert=True)
    return False