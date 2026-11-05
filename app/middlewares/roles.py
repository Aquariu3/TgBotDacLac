import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery, Message
from app.state import ADMIN_ID, admin_ids, manager_ids, last_menu_messages

class RoleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        data.setdefault("is_super", False)
        data.setdefault("is_manager", False)
        data.setdefault("is_admin", False)

        user = data.get("event_from_user")
        
        if user:
            is_super = (user.id == ADMIN_ID)
            data["is_super"] = is_super
            data["is_manager"] = (user.id in manager_ids) or is_super
            data["is_admin"] = (user.id in admin_ids) or data["is_manager"]

            current_msg_id = None
            if isinstance(event, CallbackQuery) and event.message:
                current_msg_id = event.message.message_id
            elif isinstance(event, Message):
                current_msg_id = event.message_id

            if user.id in last_menu_messages and last_menu_messages[user.id] != current_msg_id:
                try:
                    await event.bot.delete_message(user.id, last_menu_messages[user.id])
                except Exception as e:
                    logging.warning(f"Middleware: не удалось удалить старое меню {user.id}: {e}")
                last_menu_messages.pop(user.id, None)
            
        return await handler(event, data)