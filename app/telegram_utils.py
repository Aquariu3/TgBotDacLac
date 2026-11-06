import logging
from aiogram.exceptions import TelegramBadRequest

async def safe_edit(message, text, reply_markup=None, parse_mode=None) -> bool:
    """Безопасно редактирует сообщение.
    Если сообщение не изменилось — молча выходит (двойной клик).
    Если сообщение нельзя отредактировать (например, удалено) — пытается отправить новое.
    Возвращает True, если удалось отредактировать.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return False
        logging.warning(f"safe_edit (TelegramBadRequest): {e}")
        try:
            await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e2:
            logging.error(f"safe_edit fallback: {e2}")
        return False
    except Exception as e:
        logging.warning(f"safe_edit: {e}")
        return False