from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def require_admin_message(message: Message) -> bool:
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Управление доступно только администратору.")
        return False
    return True


async def require_admin_callback(cb: CallbackQuery) -> bool:
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только администратор", show_alert=True)
        return False
    return True