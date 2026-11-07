from app.domain.constants import CATEGORY_NAMES, KEY_ITEMS

def build_key_remainders_text(inventory: dict) -> str:
    lines = ["📊 <b>Ключевые остатки:</b>"]
    for name in KEY_ITEMS:
        if name in inventory: 
            unit = inventory[name].get("unit", "шт")
            lines.append(f"• {name}: <b>{inventory[name].get('qty', 0)}</b> {unit}")
    return "\n".join(lines)

def build_shift_info_text(active_employees: list[dict] | None) -> str:
    # Защита: если сервис вернул None (или упадёт и вернёт старый кэш) — не падаем
    if not active_employees:
        return "👥 <b>Сегодня на смене:</b> <i>никого нет</i>"
    
    lines = ["👥 <b>Сегодня на смене:</b>"]
    for emp in active_employees:
        name = emp.get("name", "Сотрудник")
        time = emp.get("time", "")
        if time:
            lines.append(f"• {name} (с {time})")
        else:
            lines.append(f"• {name}")
    return "\n".join(lines)

def get_main_menu_text(inventory: dict, has_access: bool, user_name: str) -> str:
    text = f"Главное меню управления остатками ({user_name}):"
    if has_access:
        key_text = build_key_remainders_text(inventory)
        # ФИКС #29: защита от превышения лимита Telegram (4096)
        if len(text) + len(key_text) > 3500:
            key_text = key_text[:3500 - len(text)] + "\n\n<i>(Список ключевых остатков обрезан)</i>"
        text += "\n\n" + key_text
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
    
    grouped = {}
    for name, data in inventory.items():
        cat = data.get("category", "other")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append((name, data))
        
    for cat, items in grouped.items():
        lines.append(f"\n<b>{CATEGORY_NAMES.get(cat, cat)}</b>")
        for name, data in items:
            unit = data.get("unit", "шт")
            if data.get("is_dessert"): 
                lines.append(f"• {name}: всего <b>{data.get('qty', 0)}</b> {unit}, витрина <b>{data.get('display_qty', 0)}</b>")
            else: 
                lines.append(f"• {name}: <b>{data.get('qty', 0)}</b> {unit}")
                
    full_text = "\n".join(lines)
    
    MAX_LEN = 3900
    if len(full_text) > MAX_LEN:
        truncated = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > MAX_LEN:
                break
            truncated.append(line)
            current_len += len(line) + 1
        full_text = "\n".join(truncated) + "\n\n<i>(Слишком много позиций, список обрезан)</i>"
        
    return full_text