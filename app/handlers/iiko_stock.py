import asyncio
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from app.state import iiko_service, iiko_async_service
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
        try:
            await callback.message.edit_text(
                "🍽 <b>Каталог остатков из iiko</b>\n\n"
                "⚠️ <b>Техкарты ещё не отсканированы.</b>\n"
                "Нажмите кнопку ниже, чтобы просканировать их.",
                reply_markup=keyboard, parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"Не удалось показать меню iiko: {e}")
        return

    try:
        await callback.message.edit_text(
            "🍽 <b>Каталог остатков из iiko</b>\n\n"
            "Выберите, что хотите посмотреть:\n"
            "• <b>📊 Текущие остатки</b> — что сейчас есть на складе\n"
            "• <b>🔄 Движения за сегодня</b> — что пришло, продалось или списалось",
            reply_markup=get_iiko_menu(), parse_mode="HTML"
        )
    except Exception as e:
        logging.warning(f"Не удалось открыть меню iiko: {e}")

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

    await callback.answer("Загружаем движения...")
    await callback.message.edit_text("⏳ <b>Запрашиваем движения за сегодня...</b>\n\nЭто может занять несколько секунд.")

    try:
        token = await asyncio.to_thread(iiko_service.sync_get_token)
        if not token: 
            # ФИКС: понятное сообщение вместо технического
            raise Exception("iiko сейчас не отвечает. Попробуйте позже (через 5-10 минут).")

        today_str = datetime.now().strftime("%Y-%m-%d")
        
        sales = await asyncio.to_thread(iiko_service.sync_get_documents, token, "sales_document", from_date=today_str)
        writeoffs = await asyncio.to_thread(iiko_service.sync_get_documents, token, "writeoff_document", from_date=today_str)
        incoming = await asyncio.to_thread(iiko_service.sync_get_documents, token, "incoming_invoice", from_date=today_str)

        if isinstance(sales, dict): sales = sales.get("items", [])
        if isinstance(writeoffs, dict): writeoffs = writeoffs.get("items", [])
        if isinstance(incoming, dict): incoming = incoming.get("items", [])

        product_map = await asyncio.to_thread(iiko_service.sync_get_products, token)

        movements = {}

        def add_movement(item, m_type):
            pid = item.get("productId") or item.get("product") or item.get("product_id")
            amount = float(item.get("amount", 0) or item.get("quantity", 0))
            if not pid or amount <= 0: return
            p_info = product_map.get(pid)
            if not p_info: return
            name = p_info.get("name", "Неизвестно")
            unit = p_info.get("unit", "шт")
            movements.setdefault(name, {"unit": unit, "in": 0, "out": 0, "sold": 0})
            movements[name][m_type] += amount

        for doc in incoming:
            for item in doc.get("items", []):
                add_movement(item, "in")

        for doc in writeoffs:
            for item in doc.get("items", []):
                add_movement(item, "out")

        for doc in sales:
            for item in doc.get("items", []):
                add_movement(item, "sold")

        if not movements:
            text = "📭 <b>Движений за сегодня не найдено.</b>"
        else:
            text = "🔄 <b>Движения за сегодня:</b>\n\n"
            for name, data in sorted(movements.items()):
                if data["in"] > 0 or data["out"] > 0 or data["sold"] > 0:
                    text += f"<b>{name}</b>\n"
                    if data["in"] > 0: text += f"  📥 Приход: {data['in']:g} {data['unit']}\n"
                    if data["out"] > 0: text += f"  📤 Списание: {data['out']:g} {data['unit']}\n"
                    if data["sold"] > 0: text += f"  💰 Продано: {data['sold']:g} {data['unit']}\n"
                    text += "\n"

        if len(text) > 3800:
            text = text[:3800] + "\n\n<i>(Список обрезан)</i>"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="iiko_view")]])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Повторить", callback_data="iiko_movements")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="iiko_view")]
        ])
        await callback.message.edit_text(
            f"❌ <b>Не удалось получить данные от iiko</b>\n\n{e}\n\n<i>Если ошибка повторяется — проверьте подключение к интернету и статус iiko.</i>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )