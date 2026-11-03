from app.domain.constants import CATEGORY_NAMES, KEY_ITEMS

def build_key_remainders_text(inventory: dict) -> str:
    lines = ["📊 <b>Ключевые остатки:</b>"]
    for name in KEY_ITEMS:
        if name in inventory: lines.append(f"• {name}: <b>{inventory[name]['qty']}</b>")
    return "\n".join(lines)

def get_main_menu_text(inventory: dict, is_admin: bool, user_name: str) -> str:
    text = f"Главное меню управления остатками ({user_name}):"
    if is_admin: text += "\n\n" + build_key_remainders_text(inventory)
    return text

def build_admin_progress_text(inventory: dict, user_name: str, collected: dict) -> str:
    text = f"📝 <b>{user_name}</b> составляет остатки.\nЗаполнено: {len(collected)} из {len(inventory)}\n\n"
    if not collected: text += "<i>Пока ничего не введено...</i>"
    else:
        for name, val in collected.items():
            if isinstance(val, dict): text += f"• {name}: всего <b>{val.get('qty')}</b>, витрина <b>{val.get('display_qty')}</b>\n"
            else: text += f"• {name}: <b>{val}</b>\n"
    return text

def build_inventory_text(inventory: dict, header: str) -> str:
    lines = [header]
    current_cat = None
    for name, data in inventory.items():
        cat = data["category"]
        if cat != current_cat:
            current_cat = cat
            lines.append(f"\n<b>{CATEGORY_NAMES.get(cat, cat)}</b>")
        if data.get("is_dessert"): lines.append(f"• {name}: всего <b>{data['qty']}</b>, витрина <b>{data['display_qty']}</b>")
        else: lines.append(f"• {name}: <b>{data['qty']}</b>")
    return "\n".join(lines)