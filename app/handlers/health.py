from datetime import datetime
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from app.state import inventory, users_db, ADMIN_ID, admin_ids, manager_ids, iiko_service, iiko_async_service

router = Router()

@router.message(Command("health"))
async def cmd_health(message: Message, is_admin: bool):
    if not is_admin:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    try: await message.delete()
    except Exception: pass

    items_count = len(inventory)
    users_count = len(users_db)
    tech_cards_count = len(iiko_service.cached_tech_card_ids)
    
    if iiko_service.iiko_cache_time:
        last_stock_update = iiko_service.iiko_cache_time.strftime("%d.%m.%Y в %H:%M:%S")
    else:
        last_stock_update = "❌ Ещё не запрашивались"

    text = (
        "🟢 <b>Бот работает стабильно!</b>\n\n"
        f"📦 <b>Позиций в базе:</b> {items_count}\n"
        f"👥 <b>Пользователей:</b> {users_count}\n\n"
        f"🍽 <b>Ингредиентов в техкартах:</b> {tech_cards_count}\n"
        f"🔄 <b>Последний запрос остатков iiko:</b>\n<i>{last_stock_update}</i>\n\n"
        f"⏱ <i>Текущее время сервера: {datetime.now().strftime('%H:%M:%S')}</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")