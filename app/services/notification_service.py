from aiogram.exceptions import TelegramBadRequest
from app.keyboards.main_kb import get_notification_keyboard
from app.texts.messages import build_admin_progress_text

class NotificationService:
    def __init__(self):
        self.status_messages = {}

    async def update_admin_status(self, bot, admin_id, user_id, user_name, event=None, action="update"):
        if action == "final":
            if user_id in self.status_messages:
                try: await bot.delete_message(admin_id, self.status_messages[user_id]["msg_id"])
                except Exception: pass
                del self.status_messages[user_id]
            await bot.send_message(admin_id, f"✅ <b>{user_name}</b> отправил(а) остатки.", parse_mode="HTML", reply_markup=get_notification_keyboard())
            return
        if action == "cancel":
            if user_id in self.status_messages:
                try: await bot.delete_message(admin_id, self.status_messages[user_id]["msg_id"])
                except Exception: pass
                del self.status_messages[user_id]
            await bot.send_message(admin_id, f"❌ <b>{user_name}</b> отменил(а) сбор.", parse_mode="HTML", reply_markup=get_notification_keyboard())
            return
        
        if user_id not in self.status_messages:
            self.status_messages[user_id] = {"events": [event]}
            text = f"🔔 <b>1 новое уведомление:</b>\n\n• <b>{user_name}</b> — {event}"
            msg = await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=get_notification_keyboard())
            self.status_messages[user_id]["msg_id"] = msg.message_id
        else:
            if event not in self.status_messages[user_id]["events"]:
                self.status_messages[user_id]["events"].append(event)
            events = self.status_messages[user_id]["events"]
            text = f"🔔 <b>{len(events)} новых уведомлений:</b>\n\n"
            for ev in events: text += f"• <b>{user_name}</b> — {ev}\n"
            try:
                await bot.edit_message_text(chat_id=admin_id, message_id=self.status_messages[user_id]["msg_id"], text=text, parse_mode="HTML", reply_markup=get_notification_keyboard())
            except Exception: pass

    async def update_admin_progress(self, bot, admin_id, user_name, collected, inventory, admin_msg_id):
        text = build_admin_progress_text(inventory, user_name, collected)
        if admin_msg_id:
            try:
                await bot.edit_message_text(chat_id=admin_id, message_id=admin_msg_id, text=text, parse_mode="HTML")
                return admin_msg_id
            except TelegramBadRequest as e:
                if "message is not modified" in str(e): return admin_msg_id
            except Exception: pass
        try:
            msg = await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML", reply_markup=get_notification_keyboard())
            return msg.message_id
        except Exception:  # <--- Вот тут была ошибка, теперь всё правильно
            return None