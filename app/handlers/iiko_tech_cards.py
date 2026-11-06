import asyncio
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.state import iiko_service, iiko_async_service

router = Router()

@router.callback_query(F.data.in_({"admin_tech_cards", "tech_cards_refresh"}))
async def cb_admin_tech_cards(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return

    if not iiko_service.cached_tech_cards_map:
        await callback.message.edit_text(
            "🍽 <b>Текущие техкарты</b>\n\n⚠️ <b>Техкарты ещё не отсканированы.</b>\nЗайдите в «Остатки по iiko» и нажмите «Сканировать техкарты».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]]), parse_mode="HTML"
        )
        return await callback.answer()

    if callback.data == "tech_cards_refresh":
        iiko_async_service.clear_cache()
        iiko_service.iiko_products_cache = None
        iiko_service.iiko_products_cache_time = None
        await callback.answer("Кэш сброшен, запрашиваем свежие данные...")
        await callback.message.edit_text("⏳ Получаем свежие категории из iiko, подождите...")
    else:
        await callback.answer("Загружаем данные...")

    try:
        token = await asyncio.to_thread(iiko_service.sync_get_token)
        if not token: raise Exception("Не удалось получить токен iiko.")
        
        groups_map = await asyncio.to_thread(iiko_service.sync_get_groups, token)
        products = await iiko_async_service.get_nomenclature()

        group_counts = {}
        for dish_id in iiko_service.cached_tech_cards_map.keys():
            p_info = products.get(dish_id)
            if not p_info or p_info.get("isDeleted") or p_info.get("type") not in ["DISH", "PREPARATION"]: continue
            g_id = p_info.get("group_id") or "other"
            group_counts[g_id] = group_counts.get(g_id, 0) + 1

        buttons = []
        if not groups_map:
            total_count = sum(group_counts.values())
            buttons.append([InlineKeyboardButton(text=f"📁 Все блюда с техкартами ({total_count})", callback_data="tech_cat_all_0")])
        else:
            sorted_groups = sorted(group_counts.items(), key=lambda x: groups_map.get(x[0], "ЯЯЯ (Без категории)"))
            for g_id, count in sorted_groups:
                g_name = groups_map.get(g_id, "Без категории")
                buttons.append([InlineKeyboardButton(text=f"📁 {g_name} ({count})", callback_data=f"tech_cat_{g_id}_0")])

        buttons.append([InlineKeyboardButton(text="🔄 Обновить данные из iiko", callback_data="tech_cards_refresh")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin_panel")])
        
        await callback.message.edit_text(
            "🍽 <b>Текущие техкарты</b>\n\nВыберите категорию для просмотра:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]]))

@router.callback_query(F.data.startswith("tech_cat_"))
async def cb_tech_cat(callback: CallbackQuery, is_manager: bool):
    if not is_manager: return await callback.answer()
    data_str = callback.data[len("tech_cat_"):]
    group_id, page_str = data_str.rsplit("_", 1)
    page = int(page_str)
    await callback.answer("Загружаем блюда...")
    
    try:
        products = await iiko_async_service.get_nomenclature()
        group_name = "Все блюда"
        if group_id != "all":
            token = await asyncio.to_thread(iiko_service.sync_get_token)
            groups_map = await asyncio.to_thread(iiko_service.sync_get_groups, token)
            group_name = groups_map.get(group_id, "Техкарты")

        dishes = []
        for dish_id in iiko_service.cached_tech_cards_map.keys():
            p_info = products.get(dish_id)
            if not p_info or p_info.get("isDeleted") or p_info.get("type") not in ["DISH", "PREPARATION"]: continue
            if group_id == "all" or (p_info.get("group_id") or "other") == group_id:
                dishes.append((dish_id, p_info["name"]))
        dishes.sort(key=lambda x: x[1])
        
        if not dishes:
            await callback.message.edit_text(f"В категории «{group_name}» пока нет активных блюд с техкартами.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_tech_cards")]]), parse_mode="HTML")
            return

        page_size, start = 10, page * 10
        end = start + page_size
        page_items = dishes[start:end]
        total_pages = max(1, (len(dishes) + page_size - 1) // page_size)
        text = f"🍽 <b>Категория: {group_name}</b>\n<i>Страница {page + 1} из {total_pages}</i>\n\nВыберите блюдо для просмотра состава:"

        buttons = [[InlineKeyboardButton(text=f"👁 {d_name[:32] + '...' if len(d_name) > 35 else d_name}", callback_data=f"tech_view_{d_id}")] for d_id, d_name in page_items]
        nav_row = []
        if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tech_cat_{group_id}_{page - 1}"))
        if end < len(dishes): nav_row.append(InlineKeyboardButton(text="Далее ➡️", callback_data=f"tech_cat_{group_id}_{page + 1}"))
        if nav_row: buttons.append(nav_row)
        buttons.append([InlineKeyboardButton(text="⬅️ К категориям", callback_data="admin_tech_cards")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при загрузке блюд: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_tech_cards")]]))

@router.callback_query(F.data.startswith("tech_view_"))
async def cb_tech_view(callback: CallbackQuery, is_manager: bool):
    if not is_manager: return await callback.answer()
    dish_id = callback.data[len("tech_view_"):]
    await callback.answer("Загружаем состав...")

    try:
        products = await iiko_async_service.get_nomenclature()
        dish_name = products.get(dish_id, {}).get("name", "Неизвестное блюдо")
        ingredients = iiko_service.cached_tech_cards_map.get(dish_id, {})
        text = f"🍽 <b>{dish_name}</b>\n\n<b>Состав по техкарте:</b>\n"
        sorted_ings = sorted(ingredients.items(), key=lambda x: products.get(x[0], {}).get("name", ""))
        
        if not sorted_ings: text += "<i>(Техкарта пуста)</i>"
        else:
            for ing_id, amount in sorted_ings:
                ing_info = products.get(ing_id, {})
                amt_str = f"{amount:g}" if amount % 1 != 0 else str(int(amount))
                text += f"• {ing_info.get('name', 'Неизвестный ингредиент')}: <b>{amt_str}</b> {ing_info.get('unit', 'шт')}\n"

        if len(text) > 3800: text = text[:3800] + "\n\n<i>(Список обрезан)</i>"
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К категориям", callback_data="admin_tech_cards")]]), parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при получении состава: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_tech_cards")]]))