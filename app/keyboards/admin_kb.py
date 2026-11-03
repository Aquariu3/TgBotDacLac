from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_admin_panel_keyboard(is_super: bool) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="✏️ Изменить позиции", callback_data="admin_edit_items")], # НОВАЯ КНОПКА
        [InlineKeyboardButton(text="📊 Остатки по iiko", callback_data="iiko_view")],
        [InlineKeyboardButton(text="🔄 Движения за сегодня", callback_data="iiko_movements")],
        [InlineKeyboardButton(text="👥 Пользователи и история", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Отправить уведомление", callback_data="admin_notify")],
    ]
    if is_super:
        kb.append([InlineKeyboardButton(text="👑 Добавить администратора", callback_data="admin_add_admin")])
        kb.append([InlineKeyboardButton(text="💼 Добавить управляющего", callback_data="admin_add_manager")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_users_to_promote_keyboard(users_db: dict, current_role_ids: set, callback_prefix: str) -> InlineKeyboardMarkup:
    buttons = []
    for uid, uname in users_db.items():
        if uid not in current_role_ids:
            buttons.append([InlineKeyboardButton(text=f"👤 {uname}", callback_data=f"{callback_prefix}_{uid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_adm_categories_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☕ Кофе", callback_data="adm_cat_coffee")],
        [InlineKeyboardButton(text="🥛 Молочка", callback_data="adm_cat_milk")],
        [InlineKeyboardButton(text="🥤 Напитки", callback_data="adm_cat_drinks")],
        [InlineKeyboardButton(text="📦 Расходники", callback_data="adm_cat_supplies")],
        [InlineKeyboardButton(text="🍰 Десерты и Еда", callback_data="adm_cat_food")],
        [InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin_panel")]
    ])

def get_adm_subcats_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥤 Стаканы", callback_data="adm_subcat_cups")],
        [InlineKeyboardButton(text="🔘 Крышки", callback_data="adm_subcat_lids")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_edit_items")]
    ])

def get_iiko_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Текущие остатки", callback_data="iiko_current_stock")],
        [InlineKeyboardButton(text="🔄 Движения за сегодня", callback_data="iiko_movements")],
        [InlineKeyboardButton(text="⚙️ Обновить техкарты", callback_data="iiko_scan_techcards")],
        [InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin_panel")]
    ])