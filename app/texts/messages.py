from app.domain.constants import CATEGORY_NAMES, KEY_ITEMS

def build_key_remainders_text(inventory: dict) -> str:
    lines = ["📊 <b>Ключевые остатки:</b>"]
    for name in KEY_ITEMS:
        if name in inventory: 
            unit = inventory[name].get("unit", "шт")
            lines.append(f"• {name}: <b>{inventory[name]['qty']}</b> {unit}")
    return "\n".join(lines)

def get_main_menu_text(inventory: dict, has_access: bool, user_name: str) -> str:
    text = f"Главное меню управления остатками ({user_name}):"
    if has_access: text += "\n\n" + build_key_remainders_text(inventory)
    return text

def build_admin_progress_text(inventory: dict, user_name: str, collected: dict) -> str:
    text = f"📝 <b>{user_name}</b> составляет остатки.\nЗаполнено: {len(collected)} из {len(inventory)}\n\n"
    if not collected: text += "<i>Пока ничего не введено...</i>"
    else:
        for name, val in collected.items():
            unit = inventory[name].get("unit", "шт") if name in inventory else "шт"
            if isinstance(val, dict): text += f"• {name}: всего <b>{val.get('qty')}</b> {unit}, витрина <b>{val.get('display_qty')}</b>\n"
            else: text += f"• {name}: <b>{val}</b> {unit}\n"
    return text

def build_inventory_text(inventory: dict, header: str) -> str:
    lines = [header]
    current_cat = None
    for name, data in inventory.items():
        cat = data["category"]
        if cat != current_cat:
            current_cat = cat
            lines.append(f"\n<b>{CATEGORY_NAMES.get(cat, cat)}</b>")
        unit = data.get("unit", "шт")
        if data.get("is_dessert"): lines.append(f"• {name}: всего <b>{data['qty']}</b> {unit}, витрина <b>{data['display_qty']}</b>")
        else: lines.append(f"• {name}: <b>{data['qty']}</b> {unit}")
    return "\n".join(lines)