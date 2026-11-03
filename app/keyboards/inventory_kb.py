from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def build_coffee_keyboard(inventory: dict) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"☕ {name} ({data['qty']})", callback_data=f"set_{name}")] for name, data in inventory.items() if data["category"] == "coffee"]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_milk_keyboard(inventory: dict) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"🥛 {name} ({data['qty']})", callback_data=f"set_{name}")] for name, data in inventory.items() if data["category"] == "milk"]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_drinks_keyboard(inventory: dict) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"🥤 {name} ({data['qty']})", callback_data=f"set_{name}")] for name, data in inventory.items() if data["category"] == "drinks"]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_supplies_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥤 Стаканы", callback_data="subcat_cups")],
        [InlineKeyboardButton(text="🔘 Крышки", callback_data="subcat_lids")],
        [InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")],
    ])

def build_subcat_keyboard(inventory: dict, subcat: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"{name} ({data['qty']})", callback_data=f"set_{name}")] for name, data in inventory.items() if data.get("subcategory") == subcat]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к расходникам", callback_data="category_supplies")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_food_keyboard(inventory: dict) -> InlineKeyboardMarkup:
    buttons = []
    for name, data in inventory.items():
        if data["category"] == "food":
            if data.get("is_dessert"): buttons.append([InlineKeyboardButton(text=f"🍰 {name} (всего {data['qty']}, витрина {data['display_qty']})", callback_data=f"set_{name}")])
            else: buttons.append([InlineKeyboardButton(text=f"🥪 {name} ({data['qty']})", callback_data=f"set_{name}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)