from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.state import inventory, users_db, ADMIN_ID, admin_ids, manager_ids, iiko_service, iiko_async_service

router = Router()

@router.message(Command("health"))
async def cmd_health(message: Message):
    user_id = message.from_user.id
    
    # Проверка прав: только админы и управляющие
    if user_id != ADMIN_ID and user_id not in admin_ids and user_id not in manager_ids:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    # 1. Данные о локальной базе
    items_count = len(inventory)
    users_count = len(users_db)
    
    # 2. Данные о техкартах iiko (локальный кеш)
    tech_cards_count = len(iiko_service.cached_tech_card_ids)
    
    # 3. Данные о последнем запросе остатков из iiko
    if iiko_service.iiko_cache_time:
        last_stock_update = iiko_service.iiko_cache_time.strftime("%d.%m.%Y в %H:%M:%S")
    else:
        last_stock_update = "❌ Ещё не запрашивались"

    # Формируем красивый отчет
    text = (
        "🟢 <b>Бот работает стабильно!</b>\n\n"
        f"📦 <b>Позиций в базе:</b> {items_count}\n"
        f"👥 <b>Пользователей:</b> {users_count}\n\n"
        f"🍽 <b>Ингредиентов в техкартах:</b> {tech_cards_count}\n"
        f"🔄 <b>Последний запрос остатков iiko:</b>\n<i>{last_stock_update}</i>\n\n"
        f"⏱ <i>Текущее время сервера: {datetime.now().strftime('%H:%M:%S')}</i>"
    )
    
    await message.answer(text, parse_mode="HTML")