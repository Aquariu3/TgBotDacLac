import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.state import iiko_service, admin_ids, manager_ids
from app.domain.constants import MAIN_KEYWORDS
from app.keyboards.admin_kb import get_iiko_menu

router = Router()

@router.callback_query(F.data == "iiko_view")
async def cb_iiko_view(callback: CallbackQuery, skip_answer=False):
    if callback.from_user.id not in admin_ids and callback.from_user.id not in manager_ids: return
    
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
async def cb_iiko_scan(callback: CallbackQuery):
    if callback.from_user.id not in admin_ids and callback.from_user.id not in manager_ids: return
    
    try: await callback.answer("Сканируем...")
    except Exception: pass
    
    await callback.message.edit_text("⏳ <b>Сканируем техкарты...</b>\n\nПожалуйста, подождите (это может занять до 1-2 минут, в зависимости от количества блюд).")
    try:
        count = await iiko_service.scan_tech_cards_and_nomenclature()
        await callback.message.edit_text(f"✅ <b>Сканирование завершено!</b>\nНайдено {count} уникальных ингредиентов в техкартах.")
        await asyncio.sleep(2)
        await cb_iiko_view(callback, skip_answer=True)
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])
        await callback.message.edit_text(f"❌ Ошибка при сканировании:\n<code>{e}</code>", reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "iiko_current_stock")
async def cb_iiko_current_stock(callback: CallbackQuery, skip_answer=False):
    if callback.from_user.id not in admin_ids and callback.from_user.id not in manager_ids: return
    
    if not skip_answer:
        try: await callback.answer()
        except Exception: pass
        
    if not iiko_service.iiko_stock_cache:
        await callback.message.edit_text("⏳ <b>Запрашиваем остатки из iiko...</b>\n\nЭто займёт 2-3 секунды.")
        try:
            await iiko_service.fetch_fast_stock()
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
async def cb_iiko_refresh_stock(callback: CallbackQuery):
    if callback.from_user.id not in admin_ids and callback.from_user.id not in manager_ids: return
    
    try: await callback.answer("Обновляем...")
    except Exception: pass
    
    iiko_service.iiko_cache_time = None
    await cb_iiko_current_stock(callback, skip_answer=True)

@router.callback_query(F.data.startswith("iiko_cat_"))
async def cb_iiko_category(callback: CallbackQuery):
    if callback.from_user.id not in admin_ids and callback.from_user.id not in manager_ids: return
    
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
async def cb_iiko_movements(callback: CallbackQuery):
    if callback.from_user.id not in admin_ids and callback.from_user.id not in manager_ids: return
    
    try: await callback.answer()
    except Exception: pass
    
    await callback.message.edit_text("⏳ <b>Собираем движения за сегодня из iiko...</b>\n\nПожалуйста, подождите (обычно 5-15 секунд).")

    try:
        token = await asyncio.to_thread(iiko_service.sync_get_token)
        if not token:
            raise Exception("Не удалось получить токен iiko.")

        product_map = await asyncio.to_thread(iiko_service.sync_get_products, token)
        sales = await asyncio.to_thread(iiko_service.sync_get_documents, token, "sales_document")
        writeoffs = await asyncio.to_thread(iiko_service.sync_get_documents, token, "writeoff_document")
        incomings = await asyncio.to_thread(iiko_service.sync_get_documents, token, "incoming_invoice")
        transfers = await asyncio.to_thread(iiko_service.sync_get_documents, token, "internal_transfer")

        main_consumption = {}
        sold_dishes = {}
        direct_writeoffs = {}
        incoming_items = {}
        transfer_items = {}

        for doc in sales:
            for item in doc.get("items", []):
                dish_id = item.get("productId") or item.get("product") or item.get("product_id")
                sold_qty = float(item.get("amount", 0))
                if dish_id and sold_qty > 0:
                    dish_name = product_map.get(dish_id, {}).get("name", "Неизвестное блюдо")
                    sold_dishes[dish_name] = sold_dishes.get(dish_name, 0) + sold_qty

                    if dish_id in iiko_service.cached_tech_cards_map:
                        for ing_id, ing_qty in iiko_service.cached_tech_cards_map[dish_id].items():
                            ing_name = product_map.get(ing_id, {}).get("name", "Неизвестный ингредиент")
                            total_ing = ing_qty * sold_qty
                            main_consumption[ing_name] = main_consumption.get(ing_name, 0) + total_ing

        for doc in writeoffs:
            for item in doc.get("items", []):
                prod_id = item.get("productId") or item.get("product") or item.get("product_id")
                qty = float(item.get("amount", 0))
                if prod_id and qty > 0:
                    prod_name = product_map.get(prod_id, {}).get("name", "Неизвестный товар")
                    direct_writeoffs[prod_name] = direct_writeoffs.get(prod_name, 0) + qty

        for doc in incomings:
            for item in doc.get("items", []):
                prod_id = item.get("product") or item.get("productId")
                qty = float(item.get("amount", 0))
                if prod_id and qty > 0:
                    prod_name = product_map.get(prod_id, {}).get("name", "Неизвестный товар")
                    incoming_items[prod_name] = incoming_items.get(prod_name, 0) + qty

        for doc in transfers:
            for item in doc.get("items", []):
                prod_id = item.get("product") or item.get("productId")
                qty = float(item.get("amount", 0))
                if prod_id and qty > 0:
                    prod_name = product_map.get(prod_id, {}).get("name", "Неизвестный товар")
                    transfer_items[prod_name] = transfer_items.get(prod_name, 0) + qty

        today_str = datetime.now().strftime("%d.%m.%Y")
        update_time = datetime.now().strftime("%H:%M")
        text = f"🔄 <b>Движения за {today_str}</b>\n<i>Последнее обновление: {update_time}</i>\n\n"

        found_something = False

        main_lines = []
        for name, qty in main_consumption.items():
            if any(k in name.lower() for k in MAIN_KEYWORDS):
                qty_str = str(int(qty)) if qty.is_integer() else f"{qty:.3f}".rstrip('0').rstrip('.')
                main_lines.append(f"• {name}: <b>{qty_str}</b>")
        for name, qty in direct_writeoffs.items():
            if any(k in name.lower() for k in MAIN_KEYWORDS):
                qty_str = str(int(qty)) if qty.is_integer() else f"{qty:.3f}".rstrip('0').rstrip('.')
                main_lines.append(f"• {name} (списание): <b>{qty_str}</b>")

        if main_lines:
            text += "⭐ <b>ГЛАВНОЕ (Расход/Списание):</b>\n" + "\n".join(main_lines) + "\n\n"
            found_something = True

        if sold_dishes:
            text += "☕ <b>Продажи (Блюда):</b>\n"
            for name, qty in sorted(sold_dishes.items()):
                text += f"• {name}: <b>{qty:g}</b>\n"
            text += "\n"
            found_something = True

        if direct_writeoffs:
            text += "📉 <b>Списания (Товары):</b>\n"
            for name, qty in sorted(direct_writeoffs.items()):
                text += f"• {name}: <b>{qty:g}</b>\n"
            text += "\n"
            found_something = True

        if incoming_items:
            text += "📦 <b>Приходы (Поставки):</b>\n"
            for name, qty in sorted(incoming_items.items()):
                text += f"• {name}: <b>{qty:g}</b>\n"
            text += "\n"
            found_something = True

        if transfer_items:
            text += "🔁 <b>Перемещения между складами:</b>\n"
            for name, qty in sorted(transfer_items.items()):
                text += f"• {name}: <b>{qty:g}</b>\n"
            text += "\n"
            found_something = True

        if not found_something:
            text = f"🔄 <b>Движения за {today_str}</b> (обновлено в {update_time}):\n\n<i>Движений не найдено.</i>"

        if len(text) > 4000:
            text = text[:3900] + "...\n\n<i>(Слишком много позиций, список обрезан)</i>"

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