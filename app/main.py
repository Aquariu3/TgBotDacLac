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
    notification_service, last_menu_messages, load_state
)

# Импорты для меню
from app.texts.messages import get_main_menu_text
from app.keyboards.main_kb import get_main_menu

async def on_startup(bot: Bot):
    logging.info("Бот запускается. Загружаем данные...")
    # П.10: Загружаем данные, когда логирование уже настроено
    load_state()
    
    logging.info("Рассылаем меню пользователям...")
    for user_id, user_name in list(users_db.items()):
        # 1. Удаляем предыдущее сообщение с меню, если оно было
        if user_id in last_menu_messages:
            try:
                await bot.delete_message(user_id, last_menu_messages[user_id])
            except Exception:
                pass # Если сообщение старое (>48ч) или уже удалено
        
        # 2. Отправляем новое меню
        is_admin = user_id in admin_ids or user_id in manager_ids
        text = f"🟢 <b>Бот снова в сети!</b>\n\n" + get_main_menu_text(inventory, is_admin, user_name)
        
        try:
            msg = await bot.send_message(
                user_id, 
                text, 
                reply_markup=get_main_menu(is_admin), 
                parse_mode="HTML"
            )
            last_menu_messages[user_id] = msg.message_id
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.warning(f"Не удалось отправить стартовое сообщение {user_id}: {e}")
    
    save_state()
    logging.info("Бот готов к работе!")

async def on_shutdown(bot: Bot):
    logging.info("Остановка бота. Очистка сообщений...")
    
    # 1. Удаляем активные сообщения мастеров
    for user_id, data in list(user_progress.items()):
        msg_id = data.get("wizard_message_id")
        if msg_id:
            try: await bot.delete_message(user_id, msg_id)
            except Exception: pass
    
    # 2. Удаляем висящие статусные сообщения у Админа
    for user_id, status in list(notification_service.status_messages.items()):
        msg_id = status.get("msg_id")
        if msg_id:
            try: await bot.delete_message(ADMIN_ID, msg_id)
            except Exception: pass
        del notification_service.status_messages[user_id]

    # 3. Удаляем старые меню и оповещаем ТОЛЬКО АДМИНОВ (П.9: защита от таймаута)
    for user_id in list(users_db.keys()):
        if user_id in last_menu_messages:
            try:
                await bot.delete_message(user_id, last_menu_messages[user_id])
            except Exception:
                pass
                
        # Отправляем сообщение о неактивности только тем, кому это важно
        if user_id in admin_ids or user_id in manager_ids:
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
            
    _save_state_sync()  # Ждём, пока всё гарантированно запишется на диск
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
    # П.22: Убран лишний отступ
    bot = create_bot()
    dp = create_dispatcher()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.warning(f"Не удалось сбросить вебхук: {e}")
        
    print("Бот запущен и готов к работе!")
    await dp.start_polling(bot)