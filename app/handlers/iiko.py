import asyncio
import logging
import math
import time
from datetime import datetime, timedelta, date
import difflib
from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from aiogram.fsm.context import FSMContext
# Стало:
from app.state import iiko_service, admin_ids, manager_ids, iiko_async_service, ADMIN_ID, inventory, iiko_mappings, save_state, find_item_by_hash
from app.states.states import AdminEditStates
from app.domain.constants import MAIN_KEYWORDS
from app.keyboards.admin_kb import get_iiko_menu
from app.text_utils import make_item_hash

router = Router()

# ФИКС #23: кэш продаж/списаний по дням, чтобы не дёргать iiko лишний раз
_sales_cache: dict[str, tuple[float, dict]] = {}
SALES_CACHE_TTL = 300  # 5 минут

def _cache_get(key: str):
    if key in _sales_cache:
        ts, data = _sales_cache[key]
        if time.time() - ts < SALES_CACHE_TTL:
            return data
        _sales_cache.pop(key, None)
    return None

def _cache_set(key: str, data):
    _sales_cache[key] = (time.time(), data)


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

# --- МЕНЮ ПРОДАЖ ---

@router.callback_query(F.data == "sales_menu")
async def cb_sales_menu(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return
    await state.clear()
    
    today = date.today()
    buttons = []
    
    for i in range(7):
        d = today - timedelta(days=i)
        if i == 0:
            label = "📅 Сегодня"
        elif i == 1:
            label = "📅 Вчера"
        else:
            label = d.strftime("%d.%m.%Y")
            
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"sales_fast_{d.strftime('%Y-%m-%d')}")])
        
    buttons.append([InlineKeyboardButton(text="🗓 Выбрать конкретный период", callback_data="sales_period_start")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="main_menu")])
    
    await callback.message.edit_text(
        "📊 <b>История продаж</b>\n\nВыберите день из последней недели или укажите свой период:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "sales_period_start")
async def cb_sales_period_start(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return
    await state.set_state(AdminEditStates.waiting_for_sales_period)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="sales_menu")]])
    await callback.message.edit_text(
        "🗓 <b>Ввод периода</b>\n\n"
        "Введите даты начала и конца периода через дефис или пробел.\n"
        "Формат: <code>ДД.ММ.ГГГГ-ДД.ММ.ГГГГ</code>\n"
        "Пример: <code>01.11.2026-05.11.2026</code>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminEditStates.waiting_for_sales_period)
async def process_sales_period(message: Message, state: FSMContext, is_manager: bool):
    if not is_manager: return
    
    if not message.text:
        try: await message.delete()
        except Exception: pass
        await message.answer("⚠️ Отправьте текст с датами.")
        return
        
    text = message.text.replace(" ", "")
    parts = text.split("-")
    
    if len(parts) != 2:
        try: await message.delete() # <-- УДАЛЯЕМ ошибочное сообщение
        except Exception: pass
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Хорошо", callback_data="sales_period_start")]])
        await message.answer("⚠️ Неверный формат. Введите две даты через дефис (например: <code>01.11.2026-05.11.2026</code>)", reply_markup=kb, parse_mode="HTML")
        return
        
    try:
        start_date = datetime.strptime(parts[0], "%d.%m.%Y").date()
        end_date = datetime.strptime(parts[1], "%d.%m.%Y").date()
    except ValueError:
        try: await message.delete() # <-- УДАЛЯЕМ ошибочное сообщение
        except Exception: pass
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Хорошо", callback_data="sales_period_start")]])
        await message.answer("⚠️ Не удалось распознать даты. Проверьте формат (ДД.ММ.ГГГГ).", reply_markup=kb)
        return
        
    if start_date > end_date:
        try: await message.delete() # <-- УДАЛЯЕМ ошибочное сообщение
        except Exception: pass
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Хорошо", callback_data="sales_period_start")]])
        await message.answer("⚠️ Дата начала не может быть позже даты конца.", reply_markup=kb)
        return
        
    await state.clear()
    
    try: await message.delete()
    except Exception: pass
    
    # Вызываем функцию отрисовки первой страницы
    await _render_sales_period_days(
        message=message,
        start_str=start_date.strftime("%Y-%m-%d"),
        end_str=end_date.strftime("%Y-%m-%d"),
        page=0
    )

async def _render_sales_period_days(message: Message, start_str: str, end_str: str, page: int):
    start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
    
    all_dates = []
    current_date = start_date
    while current_date <= end_date:
        all_dates.append(current_date)
        current_date += timedelta(days=1)
        
    page_size = 7
    start_idx = page * page_size
    end_idx = start_idx + page_size
    page_dates = all_dates[start_idx:end_idx]
    total_pages = (len(all_dates) + page_size - 1) // page_size

    buttons = []
    for d in page_dates:
        buttons.append([InlineKeyboardButton(
            text=f"📅 {d.strftime('%d.%m.%Y')}", 
            callback_data=f"sales_custom_{d.strftime('%Y-%m-%d')}_{start_str}_{end_str}_{page}"
        )])
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"sales_days_{start_str}_{end_str}_{page - 1}"))
    if end_idx < len(all_dates):
        nav_row.append(InlineKeyboardButton(text="Далее ➡️", callback_data=f"sales_days_{start_str}_{end_str}_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="⬅️ К выбору периода", callback_data="sales_menu")])

    text = (
        f"📊 <b>Выберите день из периода:</b>\n"
        f"<i>с {start_date.strftime('%d.%m.%Y')} по {end_date.strftime('%d.%m.%Y')}</i>\n\n"
        f"Страница {page + 1} из {total_pages}"
    )

    try:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    except Exception:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data.startswith("sales_days_"))
async def cb_sales_days_nav(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return
    
    parts = callback.data.split("_")
    start_str = parts[2]
    end_str = parts[3]
    page = int(parts[4])
    
    await callback.answer()
    await _render_sales_period_days(callback.message, start_str, end_str, page)

@router.callback_query(F.data.startswith("sales_fast_") | F.data.startswith("sales_custom_"))
async def cb_sales_show(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return
        
    cb_data = callback.data
    back_cb = "sales_menu"
    
    if cb_data.startswith("sales_fast_"):
        target_date_str = cb_data.replace("sales_fast_", "")
    else:
        parts = cb_data.replace("sales_custom_", "").split("_")
        target_date_str = parts[0]
        start_str = parts[1]
        end_str = parts[2]
        page = parts[3]
        back_cb = f"sales_days_{start_str}_{end_str}_{page}"
        
    display_date = datetime.strptime(target_date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    
    try: await callback.answer("Загружаем данные...")
    except Exception: pass
    
    await callback.message.edit_text(f"⏳ <b>Собираем данные за {display_date}...</b>\n\nПожалуйста, подождите.")

    # ФИКС #14: инициализируем до try, чтобы не было UnboundLocalError
    grouped_sales = {}
    direct_writeoffs = {}
    total_revenue = 0.0
    sorted_groups = []

    try:
        token = await asyncio.to_thread(iiko_service.sync_get_token)
        if not token:
            raise Exception("Не удалось получить токен iiko.")

        product_map = await asyncio.to_thread(iiko_service.sync_get_products, token)
        groups_map = await asyncio.to_thread(iiko_service.sync_get_groups, token)
        
        # ФИКС #23: кэш продаж/списаний по дням
        cache_key_sales = f"{target_date_str}_sales"
        cache_key_writeoffs = f"{target_date_str}_writeoffs"

        sales = _cache_get(cache_key_sales)
        if sales is None:
            sales = await asyncio.to_thread(iiko_service.sync_get_documents, token, "sales_document", from_date=target_date_str)
            _cache_set(cache_key_sales, sales)

        writeoffs = _cache_get(cache_key_writeoffs)
        if writeoffs is None:
            writeoffs = await asyncio.to_thread(iiko_service.sync_get_documents, token, "writeoff_document", from_date=target_date_str)
            _cache_set(cache_key_writeoffs, writeoffs)
        
        if isinstance(sales, dict): sales = sales.get("items", [])
        if isinstance(writeoffs, dict): writeoffs = writeoffs.get("items", [])

        exclude_keywords = ["молоко", "сироп", "арахис", "лимон", "шот", "на вынос", "доп", "пудра", "корица", "маршмеллоу"]

        for doc in sales:
            if not str(doc.get("date", "")).startswith(target_date_str):
                continue

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
            if not str(doc.get("date", "")).startswith(target_date_str):
                continue

            for item in doc.get("items", []):
                prod_id = item.get("productId") or item.get("product") or item.get("product_id")
                qty = float(item.get("amount", 0))
                if not prod_id or qty <= 0: continue
                p_info = product_map.get(prod_id)
                if not p_info or p_info.get("type") == "MODIFIER": continue
                
                prod_name = p_info.get("name", "Неизвестный товар")
                direct_writeoffs[prod_name] = direct_writeoffs.get(prod_name, 0) + qty

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

        text = f"📊 <b>Продажи за {display_date}</b>\n\n"
        text += f"💰 <b>Выручка:</b> <b>{total_revenue:,.2f} ₽</b>\n\n"

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
            text += "<i>Продаж и списаний за этот день не найдено.</i>"

        MAX_LEN = 3800
        if len(text) > MAX_LEN:
            lines = text.split("\n")
            truncated = []
            current_len = 0
            for line in lines:
                line_len = len(line) + 1
                if current_len + line_len > MAX_LEN:
                    break
                truncated.append(line)
                current_len += line_len
            text = "\n".join(truncated) + "\n\n<i>(Слишком много позиций, список обрезан)</i>"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить этот день", callback_data=cb_data)],
            [InlineKeyboardButton(text="⬅️ К выбору дней", callback_data=back_cb)]
        ])

        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logging.warning(f"Ошибка при обновлении сообщения продаж: {e}")
        except Exception as e:
            logging.warning(f"Ошибка при обновлении сообщения продаж: {e}")

    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К выбору дней", callback_data=back_cb)]
        ])
        try:
            await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            pass

@router.callback_query(F.data == "estimated_stock")
async def cb_estimated_stock(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return
        
    try: await callback.answer()
    except Exception: pass
    
    await callback.message.edit_text(
        "⏳ <b>Считаем остатки с учетом продаж из iiko...</b>\n\n"
        "Пожалуйста, подождите (обычно 5-15 секунд).",
        parse_mode="HTML"
    )

    try:
        token = await asyncio.to_thread(iiko_service.sync_get_token)
        if not token:
            raise Exception("Не удалось получить токен iiko.")

        product_map = await asyncio.to_thread(iiko_service.sync_get_products, token)
        sales = await asyncio.to_thread(iiko_service.sync_get_documents, token, "sales_document")
        
        if isinstance(sales, dict):
            sales = sales.get("items", [])

        sold_items_by_id = {}
        sold_items_by_name = {}
        for doc in sales:
            for item in doc.get("items", []):
                dish_id = item.get("productId") or item.get("product")
                sold_qty = float(item.get("amount", 0))
                if not dish_id or sold_qty <= 0: continue
                
                sold_items_by_id[dish_id] = sold_items_by_id.get(dish_id, 0) + sold_qty
                
                p_info = product_map.get(dish_id)
                if p_info:
                    clean_name = p_info.get("name", "").lower().strip().split('_')[0].strip()
                    if clean_name:
                        sold_items_by_name[clean_name] = sold_items_by_name.get(clean_name, 0) + sold_qty

        from app.state import inventory
        from app.domain.constants import CATEGORY_NAMES
        
        # ФИКС: считаем, сколько локальных позиций привязано к одному iiko_id.
        # Если > 1 — значит, в iiko они объединены, и точный вычет невозможен.
        mapped_count = {}
        for local_name, iiko_id in iiko_mappings.items():
            if local_name in inventory:
                mapped_count[iiko_id] = mapped_count.get(iiko_id, 0) + 1
        
        grouped = {}
        for name, data in inventory.items():
            cat = data.get("category", "other")
            if cat not in grouped: grouped[cat] = []
            grouped[cat].append((name, data))

        today_str = datetime.now().strftime("%d.%m.%Y")
        text = f"📉 <b>Остатки с учетом продаж за {today_str}</b>\n\n"
        
        found_any_match = False
        conflict_found = False

        for cat, items in grouped.items():
            cat_text = f"\n<b>{CATEGORY_NAMES.get(cat, cat)}</b>\n"
            cat_added = False
            
            for name, data in items:
                local_name_lower = name.lower().strip()
                current_qty = float(data.get('qty', 0))
                unit = data.get("unit", "шт")
                
                curr_str = str(int(current_qty)) if current_qty.is_integer() else f"{current_qty:g}"
                
                sold_qty = 0.0
                is_conflict = False
                
                mapped_id = iiko_mappings.get(name)
                if mapped_id and mapped_id in sold_items_by_id:
                    # Если к этому iiko_id привязано несколько локальных — не вычитаем
                    if mapped_count.get(mapped_id, 0) > 1:
                        is_conflict = True
                        conflict_found = True
                    else:
                        sold_qty = sold_items_by_id[mapped_id]
                elif local_name_lower in sold_items_by_name:
                    sold_qty = sold_items_by_name[local_name_lower]
                else:
                    # Ищем только если локальное название ЯВЛЯЕТСЯ частью iiko.
                    # Убрали обратную проверку, чтобы «Молоко» не вычиталось
                    # из всех «Молоко 3.2%», «Молоко Кокос» и т.д.
                    for iiko_name, qty in sold_items_by_name.items():
                        if local_name_lower in iiko_name:
                            sold_qty += qty
                            found_any_match = True
                            break
                            
                if is_conflict:
                    cat_text += f"• {name}: <b>{curr_str}</b> {unit} ⚠️ <i>(в iiko общая карточка — точный вычет невозможен)</i>\n"
                    cat_added = True
                elif sold_qty > 0:
                    found_any_match = True
                    remaining = current_qty - sold_qty
                    if remaining < 0: remaining = 0.0
                    
                    rem_str = str(int(remaining)) if remaining.is_integer() else f"{remaining:g}"
                    sold_str = str(int(sold_qty)) if sold_qty.is_integer() else f"{sold_qty:g}"
                    
                    cat_text += f"• {name}: было {curr_str} -> осталось <b>{rem_str}</b> {unit} (продано {sold_str})\n"
                    cat_added = True
                else:
                    cat_text += f"• {name}: <b>{curr_str}</b> {unit}\n"
                    cat_added = True
                    
            if cat_added:
                text += cat_text

        if conflict_found:
            text += (
                "\n⚠️ <b>Внимание:</b> некоторые позиции в вашем складе привязаны к одной общей позиции в iiko. "
                "Пока в iiko не разделены — точный расчёт для них невозможен, показан базовый остаток.\n"
            )
        elif not found_any_match:
            text += "\n<i>(Совпадений с продажами в iiko не найдено. Показаны базовые остатки)</i>\n"

        MAX_LEN = 3800
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN] + "\n\n<i>(Список обрезан)</i>"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить расчет", callback_data="estimated_stock")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]
        ])
        await callback.message.edit_text(f"❌ Ошибка при расчете: {e}", reply_markup=keyboard, parse_mode="HTML")


# --- СОПОСТАВЛЕНИЕ (МАППИНГ) ---

@router.callback_query(F.data.startswith("admin_mapping"))
async def cb_admin_mapping(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return
    await state.clear()

    # ФИКС #27: убрал лишний if/else, просто try/except
    try:
        page = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        page = 0

    all_items = list(inventory.keys())
    items_per_page = 10
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = all_items[start_idx:end_idx]
    
    total_pages = max(1, (len(all_items) + items_per_page - 1) // items_per_page)

    buttons = []
    # ФИКС #1: используем хэш вместо сырого названия (лимит 64 байта на callback_data)
    for name in page_items:
        icon = "✅" if name in iiko_mappings else "❌"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {name}", 
            callback_data=f"map_local_{make_item_hash(name)}"
        )])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_mapping_{page - 1}"))
    if end_idx < len(all_items):
        nav_row.append(InlineKeyboardButton(text="Далее ➡️", callback_data=f"admin_mapping_{page + 1}"))
    
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = (
        "🔗 <b>Сопоставление позиций</b>\n\n"
        "Здесь вы можете связать позиции из вашего бота с точными названиями (ID) из iiko.\n"
        "✅ — уже связано, ❌ — ищет по названию.\n\n"
    )
    
    if total_pages > 1:
        text += f"<i>Страница {page + 1} из {total_pages}</i>\n\n"
        
    text += "Выберите позицию бота, которую хотите связать:"

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            logging.warning(f"Ошибка при обновлении меню сопоставления: {e}")
    except Exception as e:
        logging.warning(f"Ошибка при обновлении меню сопоставления: {e}")

    await callback.answer()

def find_best_iiko_matches(local_name: str, products: dict, limit: int = 3) -> list:
    local_clean = local_name.lower().replace("(шт)", "").replace("(кг)", "").replace("(л)", "").replace("(уп)", "").strip()
    # ФИКС #33: если после очистки пусто — сразу выходим (иначе пустая строка матчит всё)
    if not local_clean:
        return []
    matches = []
    
    for pid, p in products.items():
        iiko_name = p["name"]
        iiko_clean = iiko_name.lower().split('_')[0].strip()
        
        if local_clean in iiko_clean or iiko_clean in local_clean:
            score = 1.0
        else:
            score = difflib.SequenceMatcher(None, local_clean, iiko_clean).ratio()
            
        if score >= 0.5:
            matches.append((score, pid, iiko_name))
            
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[:limit]

@router.callback_query(F.data.startswith("map_local_"))
async def cb_map_local(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return
    
    item_hash = callback.data.replace("map_local_", "")
    local_name = find_item_by_hash(item_hash)
    if not local_name:
        await callback.answer("Позиция не найдена (возможно, удалена).", show_alert=True)
        return

    await state.update_data(map_local_name=local_name, prompt_msg_id=callback.message.message_id)
    
    await callback.message.edit_text(f"⏳ Ищу похожие позиции для <b>{local_name}</b> в базе iiko...", parse_mode="HTML")
    
    try:
        products = await iiko_async_service.get_nomenclature()
        matches = find_best_iiko_matches(local_name, products)
        
        buttons = []
        
        # ФИКС (Вариант 3): Кнопка "Убрать связь", если она есть
        if local_name in iiko_mappings:
            buttons.append([InlineKeyboardButton(text="🗑 Убрать текущую связь", callback_data=f"map_unlink_{make_item_hash(local_name)}")])

        if not matches:
            await callback.message.edit_text(
                f"😔 Я не смог найти похожих названий для <b>{local_name}</b> в iiko.\n\n"
                f"Попробуйте ввести запрос вручную:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Поискать вручную", callback_data=f"map_manual_{make_item_hash(local_name)}")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_mapping")]
                ] + buttons),
                parse_mode="HTML"
            )
            await callback.answer()
            return
            
        for score, pid, iiko_name in matches:
            percent = int(score * 100)
            buttons.append([InlineKeyboardButton(
                text=f"✅ Это оно ({percent}%): {iiko_name}", 
                callback_data=f"map_save_{pid}"
            )])
            
        buttons.append([InlineKeyboardButton(text="🔍 Нет, поищу вручную", callback_data=f"map_manual_{make_item_hash(local_name)}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_mapping")])
        
        await callback.message.edit_text(
            f"🔎 Для позиции <b>{local_name}</b> я нашел вот такие варианты в iiko:\n\n"
            f"Это оно? Выберите правильный:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при поиске: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_mapping")]]))
    
    await callback.answer()

@router.callback_query(F.data.startswith("map_manual_"))
async def cb_map_manual(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return
    
    # ФИКС #1: восстанавливаем имя из хэша
    item_hash = callback.data.replace("map_manual_", "")
    local_name = find_item_by_hash(inventory, item_hash)
    if not local_name:
        await callback.answer("Позиция не найдена.", show_alert=True)
        return

    await state.update_data(map_local_name=local_name, prompt_msg_id=callback.message.message_id)
    await state.set_state(AdminEditStates.waiting_for_iiko_search)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_mapping")]])
    await callback.message.edit_text(
        f"Вы выбрали: <b>{local_name}</b>\n\n"
        f"✍️ Введите <b>часть названия</b> этой позиции так, как она называется в iiko (например: <i>малина</i>):",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminEditStates.waiting_for_iiko_search)
async def process_iiko_search(message: Message, state: FSMContext, is_manager: bool):
    if not is_manager: return
    
    if not message.text:
        try: await message.delete()
        except Exception: pass
        await message.answer("⚠️ Пожалуйста, отправьте текст для поиска.")
        return

    query = message.text.strip().lower()
    data = await state.get_data()
    local_name = data.get("map_local_name")
    prompt_msg_id = data.get("prompt_msg_id")
    
    try: await message.delete()
    except Exception: pass
    
    products = await iiko_async_service.get_nomenclature()
    
    matches = []
    for pid, p in products.items():
        if query in p["name"].lower():
            matches.append((pid, p["name"]))
            if len(matches) >= 10:
                break
                
    if not matches:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_mapping")]])
        if prompt_msg_id:
            try: await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=f"❌ По запросу «{query}» ничего не найдено в iiko.\nПопробуйте другое слово или вернитесь назад.", reply_markup=keyboard)
            except Exception: pass
        return
        
    buttons = []
    for pid, p_name in matches:
        buttons.append([InlineKeyboardButton(text=p_name, callback_data=f"map_save_{pid}")])
        
    buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_mapping")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    text = f"Связываем <b>{local_name}</b> с:\n\nВыберите правильный вариант из iiko:"
    
    if prompt_msg_id:
        try: await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
        except Exception: 
            msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            await state.update_data(prompt_msg_id=msg.message_id)
    else:
        msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id)
        
async def _save_mapping_and_show(callback: CallbackQuery, state: FSMContext, iiko_id: str):
    data = await state.get_data()
    local_name = data.get("map_local_name")
    
    if not local_name:
        await callback.answer("❌ Сессия устарела. Откройте сопоставление заново.", show_alert=True)
        return
    
    iiko_mappings[local_name] = iiko_id
    save_state()
    
    products = await iiko_async_service.get_nomenclature()
    iiko_name = products.get(iiko_id, {}).get("name", "Неизвестно")
    
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Хорошо", callback_data="admin_mapping")]
    ])
    
    try:
        await callback.message.edit_text(
            f"✅ Успешно!\nПозиция <b>{local_name}</b> теперь связана с iiko <b>{iiko_name}</b>.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            f"✅ Успешно!\nПозиция <b>{local_name}</b> теперь связана с iiko <b>{iiko_name}</b>.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    await callback.answer()

@router.callback_query(F.data.startswith("map_save_"))
async def cb_map_save(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return
        
    iiko_id = callback.data.replace("map_save_", "")
    data = await state.get_data()
    local_name = data.get("map_local_name")
    
    if not local_name:
        await callback.answer("❌ Сессия устарела.", show_alert=True)
        return

    # ФИКС (Вариант 3): Проверяем, не занят ли этот iiko_id другой позицией
    conflict_name = None
    for other_local, mapped_id in iiko_mappings.items():
        if mapped_id == iiko_id and other_local != local_name:
            conflict_name = other_local
            break
            
    if conflict_name:
        # Нашли конфликт — показываем предупреждение
        buttons = [
            [InlineKeyboardButton(text="⚠️ Да, я уверен", callback_data=f"map_force_{iiko_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_mapping")]
        ]
        await callback.message.edit_text(
            f"⚠️ <b>Внимание!</b>\n\n"
            f"Позиция iiko с ID <code>{iiko_id}</code> уже привязана к вашему складу как <b>{conflict_name}</b>.\n\n"
            f"Если вы привяжете <b>{local_name}</b> к этому же ID, то бот не сможет точно рассчитать остатки (продажи будут списываться с обеих позиций одновременно).\n\n"
            f"Вы уверены, что хотите этого?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    await _save_mapping_and_show(callback, state, iiko_id)

@router.callback_query(F.data.startswith("map_force_"))
async def cb_map_force(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return
    iiko_id = callback.data.replace("map_force_", "")
    await _save_mapping_and_show(callback, state, iiko_id)

# ФИКС (Вариант 3): Функция отвязки
@router.callback_query(F.data.startswith("map_unlink_"))
async def cb_map_unlink(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return
        
    item_hash = callback.data.replace("map_unlink_", "")
    local_name = find_item_by_hash(item_hash)
    
    if local_name and local_name in iiko_mappings:
        del iiko_mappings[local_name]
        save_state()
        await callback.answer("✅ Связь успешно удалена!", show_alert=True)
        # Возвращаемся в меню маппинга
        await cb_admin_mapping(callback, state, is_manager)
    else:
        await callback.answer("Связь не найдена.", show_alert=True)

@router.callback_query(F.data.in_({"admin_tech_cards", "tech_cards_refresh"}))
async def cb_admin_tech_cards(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return

    if not iiko_service.cached_tech_cards_map:
        await callback.message.edit_text(
            "🍽 <b>Текущие техкарты</b>\n\n"
            "⚠️ <b>Техкарты ещё не отсканированы.</b>\n"
            "Зайдите в «Остатки по iiko» и нажмите «Сканировать техкарты».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]]),
            parse_mode="HTML"
        )
        await callback.answer()
        return

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
        if not token:
            raise Exception("Не удалось получить токен iiko.")
        
        groups_map = await asyncio.to_thread(iiko_service.sync_get_groups, token)
        products = await iiko_async_service.get_nomenclature()

        group_counts = {}
        for dish_id in iiko_service.cached_tech_cards_map.keys():
            p_info = products.get(dish_id)
            if not p_info or p_info.get("isDeleted"): continue
            if p_info.get("type") not in ["DISH", "PREPARATION"]: continue
            
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
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]]))

@router.callback_query(F.data.startswith("tech_cat_"))
async def cb_tech_cat(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return

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
            if not p_info or p_info.get("isDeleted"): continue
            if p_info.get("type") not in ["DISH", "PREPARATION"]: continue
            
            if group_id == "all" or (p_info.get("group_id") or "other") == group_id:
                dishes.append((dish_id, p_info["name"]))
                
        dishes.sort(key=lambda x: x[1])
        
        if not dishes:
            await callback.message.edit_text(
                f"В категории «{group_name}» пока нет активных блюд с техкартами.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_tech_cards")]]),
                parse_mode="HTML"
            )
            return

        page_size = 10
        start = page * page_size
        end = start + page_size
        page_items = dishes[start:end]
        total_pages = max(1, (len(dishes) + page_size - 1) // page_size)

        text = f"🍽 <b>Категория: {group_name}</b>\n<i>Страница {page + 1} из {total_pages}</i>\n\nВыберите блюдо для просмотра состава:"

        buttons = []
        for d_id, d_name in page_items:
            if len(d_name) > 35:
                d_name = d_name[:32] + "..."
            buttons.append([InlineKeyboardButton(text=f"👁 {d_name}", callback_data=f"tech_view_{d_id}")])

        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"tech_cat_{group_id}_{page - 1}"))
        if end < len(dishes):
            nav_row.append(InlineKeyboardButton(text="Далее ➡️", callback_data=f"tech_cat_{group_id}_{page + 1}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton(text="⬅️ К категориям", callback_data="admin_tech_cards")])
        
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при загрузке блюд: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_tech_cards")]]))

@router.callback_query(F.data.startswith("tech_view_"))
async def cb_tech_view(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.answer()
        return

    dish_id = callback.data[len("tech_view_"):]

    await callback.answer("Загружаем состав...")

    try:
        products = await iiko_async_service.get_nomenclature()
        dish_name = products.get(dish_id, {}).get("name", "Неизвестное блюдо")
        ingredients = iiko_service.cached_tech_cards_map.get(dish_id, {})

        text = f"🍽 <b>{dish_name}</b>\n\n<b>Состав по техкарте:</b>\n"
        
        sorted_ings = sorted(ingredients.items(), key=lambda x: products.get(x[0], {}).get("name", ""))
        
        if not sorted_ings:
            text += "<i>(Техкарта пуста)</i>"
        else:
            for ing_id, amount in sorted_ings:
                ing_info = products.get(ing_id, {})
                ing_name = ing_info.get("name", "Неизвестный ингредиент")
                ing_unit = ing_info.get("unit", "шт")
                
                amt_str = f"{amount:g}" if amount % 1 != 0 else str(int(amount))
                text += f"• {ing_name}: <b>{amt_str}</b> {ing_unit}\n"

        if len(text) > 3800:
            text = text[:3800] + "\n\n<i>(Список обрезан)</i>"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К категориям", callback_data="admin_tech_cards")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при получении состава: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_tech_cards")]]))