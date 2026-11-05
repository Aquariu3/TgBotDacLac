from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_notification_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Хорошо (прочитано)", callback_data="dismiss_msg")]])

def get_main_menu(has_access: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="📦 Скинуть остатки (мастер)", callback_data="start_wizard")],
        [InlineKeyboardButton(text="✏️ Редактировать по категориям", callback_data="edit_categories_menu")],
        [InlineKeyboardButton(text="📊 Посмотреть все остатки", callback_data="view_all")],
    ]
    if has_access: 
        keyboard.append([InlineKeyboardButton(text="📉 Остатки с учетом продаж", callback_data="estimated_stock")])
        keyboard.append([InlineKeyboardButton(text="📊 Продажи", callback_data="sales_menu")]) # <-- НОВАЯ КНОПКА
        keyboard.append([InlineKeyboardButton(text="⚙️ Панель администратора", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_edit_categories_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☕ Кофе", callback_data="category_coffee")],
        [InlineKeyboardButton(text="🥛 Молочка", callback_data="category_milk")],
        [InlineKeyboardButton(text="🥤 Напитки в банке", callback_data="category_drinks")],
        [InlineKeyboardButton(text="📦 Расходники", callback_data="category_supplies")],
        [InlineKeyboardButton(text="🍰 Десерты и Еда", callback_data="category_food")],
        [InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="main_menu")],
    ])