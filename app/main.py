import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from app.config import settings, DATA_DIR
from app.handlers import setup_routers

# Импорты из состояния
from app.state import (
    users_db, user_progress, inventory, ADMIN_ID, 
    admin_ids, manager_ids, save_state, _save_state_sync, 
    notification_service, last_menu_messages, load_state,
    wait_for_saves  # <-- ФИКС #17
)

# Импорты для меню
from app.texts.messages import get_main_menu_text
from app.keyboards.main_kb import get_main_menu
from app.handlers.common import get_user_role

async def on_startup(bot: Bot):
    logging.info("Бот запускается. Загружаем данные...")
    load_state()
    
    logging.info("Обновляем меню у пользователей...")
    
    for user_id, user_name in list(users_db.items()):
        is_super = (user_id == ADMIN_ID)
        is_manager = (user_id in manager_ids) or is_super
        is_admin = (user_id in admin_ids) or is_manager
        
        role_text, has_access = get_user_role(is_super, is_manager, is_admin)
        
        text = f"Рад видеть вас снова, <b>{user_name}</b>!\n\n{role_text}\n\n" + get_main_menu_text(inventory, has_access, user_name)
        
        if has_access:
            text = "🟢 <b>Бот снова в сети!</b>\n\n" + text

        if has_access:
            if user_id in last_menu_messages:
                try: await bot.delete_message(user_id, last_menu_messages[user_id])
                except Exception: pass
                
            try:
                msg = await bot.send_message(user_id, text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
                last_menu_messages[user_id] = msg.message_id
                await asyncio.sleep(0.05)
            except Exception as e:
                logging.warning(f"Не удалось отправить сообщение админу {user_id}: {e}")
        else:
            if user_id in last_menu_messages:
                msg_id = last_menu_messages[user_id]
                try:
                    await bot.edit_message_text(
                        chat_id=user_id,
                        message_id=msg_id,
                        text=text,
                        reply_markup=get_main_menu(has_access),
                        parse_mode="HTML"
                    )
                    await asyncio.sleep(0.05)
                except Exception:
                    try:
                        msg = await bot.send_message(user_id, text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
                        last_menu_messages[user_id] = msg.message_id
                        await asyncio.sleep(0.05)
                    except Exception as e:
                        logging.warning(f"Не удалось отправить меню пользователю {user_id}: {e}")
            else:
                try:
                    msg = await bot.send_message(user_id, text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
                    last_menu_messages[user_id] = msg.message_id
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logging.warning(f"Не удалось отправить меню пользователю {user_id}: {e}")

    save_state()
    logging.info("Бот готов к работе!")

async def on_shutdown(bot: Bot):
    logging.info("Остановка бота. Очистка сообщений...")
    
    for user_id, data in list(user_progress.items()):
        msg_id = data.get("wizard_message_id")
        if msg_id:
            try: await bot.delete_message(user_id, msg_id)
            except Exception: pass
    
    for user_id, status in list(notification_service.status_messages.items()):
        msg_id = status.get("msg_id")
        if msg_id:
            try: await bot.delete_message(ADMIN_ID, msg_id)
            except Exception: pass
        del notification_service.status_messages[user_id]

    for user_id in list(users_db.keys()):
        is_admin_user = user_id in admin_ids or user_id in manager_ids or user_id == ADMIN_ID
        
        if user_id in last_menu_messages:
            msg_id = last_menu_messages[user_id]
            
            if not is_admin_user:
                try:
                    await bot.edit_message_text(
                        chat_id=user_id,
                        message_id=msg_id,
                        text="🔴 <b>Бот сейчас не активен.</b>\n\nПожалуйста, вернитесь позже. Все ваши данные сохранены.",
                        reply_markup=None,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logging.warning(f"Не удалось изменить меню на 'неактивно' для {user_id}: {e}")
                    try: await bot.delete_message(user_id, msg_id)
                    except Exception: pass
                    last_menu_messages.pop(user_id, None)
            else:
                try: await bot.delete_message(user_id, msg_id)
                except Exception: pass
                last_menu_messages.pop(user_id, None)
                
        if is_admin_user:
            try:
                msg = await bot.send_message(
                    user_id, 
                    "🔴 <b>Бот сейчас не активен.</b>\n\nПожалуйста, вернитесь позже. Все ваши данные сохранены.", 
                    parse_mode="HTML"
                )
                last_menu_messages[user_id] = msg.message_id
                await asyncio.sleep(0.05)
            except Exception:
                pass
            
    # ФИКС #17: сначала ждем все фоновые сохранения, потом пишем финальный слепок
    await wait_for_saves()
    _save_state_sync()
    logging.info("Все данные успешно сохранены. Бот остановлен.")

def create_bot() -> Bot:
    return Bot(token=settings.BOT_TOKEN)

def create_dispatcher() -> Dispatcher:
    from app.middlewares.roles import RoleMiddleware
    
    dp = Dispatcher()
    dp.message.middleware(RoleMiddleware())
    dp.callback_query.middleware(RoleMiddleware())
    
    setup_routers(dp)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp

async def main() -> None:
    bot = create_bot()
    dp = create_dispatcher()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.warning(f"Не удалось сбросить вебхук: {e}")
        
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot)