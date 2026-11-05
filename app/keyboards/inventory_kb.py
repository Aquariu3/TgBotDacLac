from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.text_utils import make_item_hash

def build_coffee_keyboard(inventory: dict) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"☕ {name} ({data.get('qty', 0)} {data.get('unit', 'шт')})", callback_data=f"set_{make_item_hash(name)}")] for name, data in inventory.items() if data["category"] == "coffee"]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_milk_keyboard(inventory: dict) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"🥛 {name} ({data.get('qty', 0)} {data.get('unit', 'шт')})", callback_data=f"set_{make_item_hash(name)}")] for name, data in inventory.items() if data["category"] == "milk"]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_drinks_keyboard(inventory: dict) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"🥤 {name} ({data.get('qty', 0)} {data.get('unit', 'шт')})", callback_data=f"set_{make_item_hash(name)}")] for name, data in inventory.items() if data["category"] == "drinks"]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_supplies_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🥤 Стаканы", callback_data="subcat_cups")],
        [InlineKeyboardButton(text="🔘 Крышки", callback_data="subcat_lids")],
        [InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")],
    ])

def build_subcat_keyboard(inventory: dict, subcat: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"{name} ({data.get('qty', 0)} {data.get('unit', 'шт')})", callback_data=f"set_{make_item_hash(name)}")] for name, data in inventory.items() if data.get("subcategory") == subcat]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к расходникам", callback_data="category_supplies")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_food_keyboard(inventory: dict) -> InlineKeyboardMarkup:
    buttons = []
    for name, data in inventory.items():
        if data["category"] == "food":
            unit = data.get('unit', 'шт')
            if data.get("is_dessert"):
                buttons.append([InlineKeyboardButton(text=f"🍰 {name} (всего {data.get('qty', 0)} {unit}, витрина {data.get('display_qty', 0)})", callback_data=f"set_{make_item_hash(name)}")])
            else:
                buttons.append([InlineKeyboardButton(text=f"🥪 {name} ({data.get('qty', 0)} {unit})", callback_data=f"set_{make_item_hash(name)}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data="edit_categories_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)