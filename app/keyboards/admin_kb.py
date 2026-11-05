from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_admin_panel_keyboard(is_full_access: bool) -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text="✏️ Изменить позиции", callback_data="admin_edit_items")]]
    if is_full_access:
        kb.extend([
            [InlineKeyboardButton(text="📊 Остатки по iiko", callback_data="iiko_view")],
            [InlineKeyboardButton(text="🍽 Текущие техкарты", callback_data="admin_tech_cards")], # <-- ВОТ КНОПКА
            [InlineKeyboardButton(text="🔗 Сопоставление с iiko", callback_data="admin_mapping")],
            [InlineKeyboardButton(text="👥 Пользователи и история", callback_data="admin_users")],
            [InlineKeyboardButton(text="📢 Отправить уведомление", callback_data="admin_notify")],
            [InlineKeyboardButton(text="⚙️ Остальное", callback_data="admin_other_menu")]
        ])
    kb.append([InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_admin_other_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Администраторы", callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="💼 Управляющие", callback_data="admin_manage_managers")],
        [InlineKeyboardButton(text="🔄 Обновить техкарты", callback_data="iiko_scan_techcards")],
        [InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin_panel")]
    ])

def get_role_management_keyboard(role_type: str, users: list) -> InlineKeyboardMarkup:
    kb = []
    if not users:
        kb.append([InlineKeyboardButton(text="Список пуст", callback_data="noop")])
    else:
        for uid, name in users:
            kb.append([InlineKeyboardButton(text=f"👤 {name}", callback_data="noop")])
    kb.append([InlineKeyboardButton(text="➕ Добавить", callback_data=f"admin_add_role_{role_type}")])
    if users:
        kb.append([InlineKeyboardButton(text="➖ Удалить", callback_data=f"admin_del_role_{role_type}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_other_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_users_to_promote_keyboard(users_db: dict, current_role_ids: set, role_type: str) -> InlineKeyboardMarkup:
    buttons = []
    for uid, uname in users_db.items():
        if uid not in current_role_ids:
            buttons.append([InlineKeyboardButton(text=f"👤 {uname}", callback_data=f"make_{role_type}_{uid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_manage_{role_type}s")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_users_to_demote_keyboard(users_db: dict, current_role_ids: set, role_type: str) -> InlineKeyboardMarkup:
    buttons = []
    for uid in current_role_ids:
        uname = users_db.get(uid, "Сотрудник")
        buttons.append([InlineKeyboardButton(text=f"❌ {uname}", callback_data=f"del_{role_type}_{uid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_manage_{role_type}s")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_adm_categories_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☕ Кофе", callback_data="adm_cat_coffee")],
        [InlineKeyboardButton(text="🥛 Молочка", callback_data="adm_cat_milk")],
        [InlineKeyboardButton(text="🥤 Напитки", callback_data="adm_cat_drinks")],
        [InlineKeyboardButton(text="📦 Расходники", callback_data="adm_cat_supplies")],
        [InlineKeyboardButton(text="🍰 Десерты и Еда", callback_data="adm_cat_food")],
        [InlineKeyboardButton(text="🔄 Синхронизировать ед. изм. с iiko", callback_data="adm_sync_units")],
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
        [InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin_panel")]
    ])