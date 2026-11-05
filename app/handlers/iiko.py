import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.state import iiko_service, admin_ids, manager_ids, iiko_async_service, ADMIN_ID
from app.domain.constants import MAIN_KEYWORDS
from app.keyboards.admin_kb import get_iiko_menu

router = Router()

@router.callback_query(F.data == "iiko_view")
async def cb_iiko_view(callback: CallbackQuery, is_manager: bool, skip_answer=False):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    if not skip_answer:
        try: await callback.answer()
        except Exception: pass
        
    if not iiko_service.cached_tech_card_ids and not iiko_service.cached_tech_cards_map:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Сканировать техкарты", callback_data="iiko_scan_techcards")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
        ])
        await callback.message.edit_text(
            "🍽 <b>Каталог остатков из iiko</b>\n\n"
            "⚠️ <b>Техкарты ещё не отсканированы.</b>\n"
            "Нажмите кнопку ниже, чтобы просканировать их.",
            reply_markup=keyboard, parse_mode="HTML"
        )
        return

    await callback.message.edit_text(
        "🍽 <b>Каталог остатков из iiko</b>\n\n"
        "Выберите, что хотите посмотреть:\n"
        "• <b>📊 Текущие остатки</b> — что сейчас есть на складе\n"
        "• <b>🔄 Движения за сегодня</b> — что пришло, продалось или списалось",
        reply_markup=get_iiko_menu(), parse_mode="HTML"
    )

@router.callback_query(F.data == "iiko_scan_techcards")
async def cb_iiko_scan(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    try: await callback.answer("Сканируем...")
    except Exception: pass
    
    await callback.message.edit_text("⏳ <b>Сканируем техкарты...</b>\n\nПожалуйста, подождите (это может занять до 1-2 минут, в зависимости от количества блюд).")
    try:
        count = await iiko_service.scan_tech_cards_and_nomenclature()
        await callback.message.edit_text(f"✅ <b>Сканирование завершено!</b>\nНайдено {count} уникальных ингредиентов в техкартах.")
        await asyncio.sleep(2)
        await cb_iiko_view(callback, is_manager=is_manager, skip_answer=True)
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_other_menu")]])
        await callback.message.edit_text(f"❌ Ошибка при сканировании:\n<code>{e}</code>", reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "iiko_current_stock")
async def cb_iiko_current_stock(callback: CallbackQuery, is_manager: bool, skip_answer=False):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    if not skip_answer:
        try: await callback.answer()
        except Exception: pass
        
    if not iiko_service.iiko_stock_cache:
        await callback.message.edit_text("⏳ <b>Запрашиваем остатки из iiko...</b>\n\nЭто займёт 2-3 секунды.")
        try:
            stock_data = await iiko_async_service.get_stock_balance()
            iiko_service.iiko_stock_cache = stock_data
            # Обновляем метку — её показывает /health как "последний запрос остатков"
            iiko_service.iiko_cache_time = datetime.now()
        except Exception as e:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Повторить", callback_data="iiko_current_stock")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="iiko_view")]
            ])
            await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=keyboard, parse_mode="HTML")
            return

    counts = {"kitchen": 0, "bar": 0, "desserts": 0, "supplies": 0, "other": 0}
    for item in iiko_service.iiko_stock_cache:
        cat = iiko_service.classify_iiko_item(item['name'])
        counts[cat] += 1

    update_time = datetime.now().strftime("%d.%m.%Y %H:%M")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🍳 Кухня ({counts['kitchen']})", callback_data="iiko_cat_kitchen")],
        [InlineKeyboardButton(text=f"☕ Бар / Напитки ({counts['bar']})", callback_data="iiko_cat_bar")],
        [InlineKeyboardButton(text=f"🍰 Десерты ({counts['desserts']})", callback_data="iiko_cat_desserts")],
        [InlineKeyboardButton(text=f"📦 Расходники ({counts['supplies']})", callback_data="iiko_cat_supplies")],
        [InlineKeyboardButton(text=f"🗂 Прочее ({counts['other']})", callback_data="iiko_cat_other")],
        [InlineKeyboardButton(text="🔄 Обновить остатки", callback_data="iiko_refresh_stock")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="iiko_view")]
    ])
    await callback.message.edit_text(
        f"📊 <b>Текущие остатки из iiko</b>\n<i>Последнее обновление: {update_time}</i>\n\nВыберите категорию для просмотра.",
        reply_markup=keyboard, parse_mode="HTML"
    )

@router.callback_query(F.data == "iiko_refresh_stock")
async def cb_iiko_refresh_stock(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    try: await callback.answer("Обновляем...")
    except Exception: pass
    
    # Обнуляем именно тот кэш, по которому cb_iiko_current_stock решает,
    # что данные "свежие" и не идёт в iiko повторно.
    iiko_service.iiko_stock_cache = []
    iiko_service.iiko_cache_time = None
    await cb_iiko_current_stock(callback, is_manager=is_manager, skip_answer=True)

@router.callback_query(F.data.startswith("iiko_cat_"))
async def cb_iiko_category(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    try: await callback.answer()
    except Exception: pass
    
    cat = callback.data.replace("iiko_cat_", "")
    names = {"kitchen": "🍳 Кухня", "bar": "☕ Бар / Напитки", "desserts": "🍰 Десерты", "supplies": "📦 Расходники", "other": "🗂 Прочее"}
    cat_items = [item for item in iiko_service.iiko_stock_cache if iiko_service.classify_iiko_item(item['name']) == cat]
    if not cat_items:
        text = f"{names[cat]}\n\n<i>В этой категории пока нет позиций.</i>"
    else:
        cat_items.sort(key=lambda x: x['name'])
        update_time = datetime.now().strftime("%d.%m.%Y %H:%M")
        text = f"{names[cat]} (найдено {len(cat_items)})\n<i>Данные на: {update_time}</i>\n\n"
        for item in cat_items:
            qty = item['qty']
            qty_str = str(int(qty)) if qty.is_integer() else f"{qty:.3f}".rstrip('0').rstrip('.')
            text += f"• {item['name']}: <b>{qty_str}</b> {item['unit']}\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить остатки", callback_data="iiko_refresh_stock")],
        [InlineKeyboardButton(text="⬅️ К категориям", callback_data="iiko_current_stock")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "iiko_movements")
async def cb_iiko_movements(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    try: await callback.answer()
    except Exception: pass
    
    await callback.message.edit_text("⏳ <b>Собираем движения за сегодня из iiko...</b>\n\nПожалуйста, подождите (обычно 5-15 секунд).")

    try:
        token = await asyncio.to_thread(iiko_service.sync_get_token)
        if not token:
            raise Exception("Не удалось получить токен iiko.")

        product_map = await asyncio.to_thread(iiko_service.sync_get_products, token)
        groups_map = await asyncio.to_thread(iiko_service.sync_get_groups, token)
        
        sales = await asyncio.to_thread(iiko_service.sync_get_documents, token, "sales_document")
        writeoffs = await asyncio.to_thread(iiko_service.sync_get_documents, token, "writeoff_document")
                # iiko может вернуть как list, так и dict с ключом "items" — приводим к list
        if isinstance(sales, dict):
            sales = sales.get("items", [])
        if isinstance(writeoffs, dict):
            writeoffs = writeoffs.get("items", [])


        total_revenue = 0.0
        grouped_sales = {}  
        direct_writeoffs = {}

        exclude_keywords = ["молоко", "сироп", "арахис", "лимон", "шот", "на вынос", "доп", "пудра", "корица", "маршмеллоу"]

        for doc in sales:
            total_revenue += float(doc.get("sum", 0))
            for item in doc.get("items", []):
                dish_id = item.get("productId") or item.get("product") or item.get("product_id")
                sold_qty = float(item.get("amount", 0))
                if not dish_id or sold_qty <= 0: continue
                
                p_info = product_map.get(dish_id)
                if not p_info: continue
                
                dish_name = p_info.get("name", "Неизвестное блюдо")
                dish_name_lower = dish_name.lower()

                if p_info.get("type") in ["MODIFIER", "GOODS"] and any(kw in dish_name_lower for kw in exclude_keywords): continue
                
                clean_name = dish_name.split('_')[0].strip() 
                group_name = groups_map.get(p_info.get("group_id"), "Без категории")
                
                if group_name not in grouped_sales:
                    grouped_sales[group_name] = {}
                grouped_sales[group_name][clean_name] = grouped_sales[group_name].get(clean_name, 0) + sold_qty

        for doc in writeoffs:
            for item in doc.get("items", []):
                prod_id = item.get("productId") or item.get("product") or item.get("product_id")
                qty = float(item.get("amount", 0))
                if not prod_id or qty <= 0: continue
                p_info = product_map.get(prod_id)
                if not p_info or p_info.get("type") == "MODIFIER": continue
                
                prod_name = p_info.get("name", "Неизвестный товар")
                direct_writeoffs[prod_name] = direct_writeoffs.get(prod_name, 0) + qty

        today_str = datetime.now().strftime("%d.%m.%Y")
        update_time = datetime.now().strftime("%H:%M")
        
        def get_priority(g_name):
            g = g_name.upper()
            if "КЛАССИКА КОФЕ" in g: return 1
            if "ЗАВТРАК" in g: return 2
            if "ЛАНЧ" in g: return 3
            if "АВТОРСКОЙ КОФЕ" in g: return 4
            if "ОСЕН" in g: return 5
            if "ЛЕТО" in g: return 6
            return 99

        sorted_groups = sorted(grouped_sales.keys(), key=get_priority)

        text = f"🔄 <b>Движения за {today_str}</b>\n<i>Обновлено в {update_time}</i>\n\n"
        text += f"💰 <b>Текущая касса:</b> <b>{total_revenue:,.2f} ₽</b>\n\n"

        kitchen_header = False
        signature_header = False
        other_header = False

        for group_name in sorted_groups:
            g_upper = group_name.upper()
            
            if get_priority(group_name) == 99 and not other_header:
                text += "📦 <b>ОСТАЛЬНОЕ МЕНЮ</b>\n\n"
                other_header = True
                
            if ("ЗАВТРАК" in g_upper or "ЛАНЧ" in g_upper) and not kitchen_header:
                text += "🍳 <b>КУХНЯ</b>\n\n"
                kitchen_header = True
                
            if ("АВТОРСКОЙ КОФЕ" in g_upper or "ОСЕН" in g_upper or "ЛЕТО" in g_upper) and not signature_header:
                text += "✨ <b>ФИРМЕННЫЕ</b>\n\n"
                signature_header = True

            text += f"<b>{group_name.upper()}</b>\n"
            for dish_name in sorted(grouped_sales[group_name].keys()):
                qty = grouped_sales[group_name][dish_name]
                text += f"• {dish_name}: <b>{qty:g}</b>\n"
            text += "\n"

        if direct_writeoffs:
            text += "📉 <b>СПИСАНИЯ:</b>\n"
            for name, qty in sorted(direct_writeoffs.items()):
                text += f"• {name}: <b>{qty:g}</b>\n"
            text += "\n"

        if not grouped_sales and not direct_writeoffs:
            text += "<i>Движений не найдено.</i>"

               # Безопасная обрезка: режем по строкам, чтобы не разорвать HTML-теги.
        # В этой функции каждый <b>...</b> находится внутри одной строки,
        # поэтому обрезка по \n гарантированно не ломает разметку.
        MAX_LEN = 3800
        if len(text) > MAX_LEN:
            lines = text.split("\n")
            truncated = []
            current_len = 0
            for line in lines:
                line_len = len(line) + 1  # +1 за \n
                if current_len + line_len > MAX_LEN:
                    break
                truncated.append(line)
                current_len += line_len
            text = "\n".join(truncated) + "\n\n<i>(Слишком много позиций, список обрезан)</i>"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="iiko_movements")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="iiko_view")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="iiko_view")]
        ])
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=keyboard, parse_mode="HTML")