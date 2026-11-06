import asyncio
import logging
import time
from datetime import datetime, timedelta, date
from aiogram.exceptions import TelegramBadRequest
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from app.state import iiko_service, iiko_mappings, inventory
from app.states.states import AdminEditStates
from app.domain.constants import CATEGORY_NAMES

router = Router()

_sales_cache: dict[str, tuple[float, dict]] = {}
SALES_CACHE_TTL = 300

def _cache_get(key: str):
    if key in _sales_cache:
        ts, data = _sales_cache[key]
        if time.time() - ts < SALES_CACHE_TTL:
            return data
        _sales_cache.pop(key, None)
    return None

def _cache_set(key: str, data):
    _sales_cache[key] = (time.time(), data)

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
        if i == 0: label = "📅 Сегодня"
        elif i == 1: label = "📅 Вчера"
        else: label = d.strftime("%d.%m.%Y")
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
        try: await message.delete()
        except Exception: pass
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Хорошо", callback_data="sales_period_start")]])
        await message.answer("⚠️ Неверный формат. Введите две даты через дефис (например: <code>01.11.2026-05.11.2026</code>)", reply_markup=kb, parse_mode="HTML")
        return
        
    try:
        start_date = datetime.strptime(parts[0], "%d.%m.%Y").date()
        end_date = datetime.strptime(parts[1], "%d.%m.%Y").date()
    except ValueError:
        try: await message.delete()
        except Exception: pass
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Хорошо", callback_data="sales_period_start")]])
        await message.answer("⚠️ Не удалось распознать даты. Проверьте формат (ДД.ММ.ГГГГ).", reply_markup=kb)
        return
        
    if start_date > end_date:
        try: await message.delete()
        except Exception: pass
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Хорошо", callback_data="sales_period_start")]])
        await message.answer("⚠️ Дата начала не может быть позже даты конца.", reply_markup=kb)
        return
        
    await state.clear()
    try: await message.delete()
    except Exception: pass
    
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

    grouped_sales = {}
    direct_writeoffs = {}
    total_revenue = 0.0
    sorted_groups = []

    try:
        token = await asyncio.to_thread(iiko_service.sync_get_token)
        if not token: raise Exception("Не удалось получить токен iiko.")

        product_map = await asyncio.to_thread(iiko_service.sync_get_products, token)
        groups_map = await asyncio.to_thread(iiko_service.sync_get_groups, token)
        
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
            if not str(doc.get("date", "")).startswith(target_date_str): continue
            total_revenue += float(doc.get("sum", 0))
            for item in doc.get("items", []):
                dish_id = item.get("productId") or item.get("product") or item.get("product_id")
                sold_qty = float(item.get("amount", 0))
                if not dish_id or sold_qty <= 0: continue
                p_info = product_map.get(dish_id)
                if not p_info: continue
                dish_name = p_info.get("name", "Неизвестное блюдо")
                if p_info.get("type") in ["MODIFIER", "GOODS"] and any(kw in dish_name.lower() for kw in exclude_keywords): continue
                clean_name = dish_name.split('_')[0].strip() 
                group_name = groups_map.get(p_info.get("group_id"), "Без категории")
                if group_name not in grouped_sales: grouped_sales[group_name] = {}
                grouped_sales[group_name][clean_name] = grouped_sales[group_name].get(clean_name, 0) + sold_qty

        for doc in writeoffs:
            if not str(doc.get("date", "")).startswith(target_date_str): continue
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

        kitchen_header, signature_header, other_header = False, False, False

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
            truncated, current_len = [], 0
            for line in lines:
                if current_len + len(line) + 1 > MAX_LEN: break
                truncated.append(line)
                current_len += len(line) + 1
            text = "\n".join(truncated) + "\n\n<i>(Слишком много позиций, список обрезан)</i>"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить этот день", callback_data=cb_data)],
            [InlineKeyboardButton(text="⬅️ К выбору дней", callback_data=back_cb)]
        ])

        try:
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e): logging.warning(f"Ошибка продаж: {e}")
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К выбору дней", callback_data=back_cb)]])
        try: await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=keyboard, parse_mode="HTML")
        except Exception: pass

@router.callback_query(F.data == "estimated_stock")
async def cb_estimated_stock(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return
    try: await callback.answer()
    except Exception: pass
    
    await callback.message.edit_text("⏳ <b>Считаем остатки с учетом продаж из iiko...</b>\n\nПожалуйста, подождите (обычно 5-15 секунд).", parse_mode="HTML")

    try:
        token = await asyncio.to_thread(iiko_service.sync_get_token)
        if not token: raise Exception("Не удалось получить токен iiko.")

        product_map = await asyncio.to_thread(iiko_service.sync_get_products, token)
        sales = await asyncio.to_thread(iiko_service.sync_get_documents, token, "sales_document")
        if isinstance(sales, dict): sales = sales.get("items", [])

        sold_items_by_id, sold_items_by_name = {}, {}
        for doc in sales:
            for item in doc.get("items", []):
                dish_id = item.get("productId") or item.get("product")
                sold_qty = float(item.get("amount", 0))
                if not dish_id or sold_qty <= 0: continue
                sold_items_by_id[dish_id] = sold_items_by_id.get(dish_id, 0) + sold_qty
                p_info = product_map.get(dish_id)
                if p_info:
                    clean_name = p_info.get("name", "").lower().strip().split('_')[0].strip()
                    if clean_name: sold_items_by_name[clean_name] = sold_items_by_name.get(clean_name, 0) + sold_qty

        mapped_count = {}
        for local_name, iiko_id in iiko_mappings.items():
            if local_name in inventory: mapped_count[iiko_id] = mapped_count.get(iiko_id, 0) + 1

        grouped = {}
        for name, data in inventory.items():
            cat = data.get("category", "other")
            if cat not in grouped: grouped[cat] = []
            grouped[cat].append((name, data))

        today_str = datetime.now().strftime("%d.%m.%Y")
        text = f"📉 <b>Остатки с учетом продаж за {today_str}</b>\n\n"
        found_any_match, conflict_found = False, False

        for cat, items in grouped.items():
            cat_text = f"\n<b>{CATEGORY_NAMES.get(cat, cat)}</b>\n"
            cat_added = False
            
            for name, data in items:
                local_name_lower = name.lower().strip()
                current_qty = float(data.get('qty', 0))
                unit = data.get("unit", "шт")
                curr_str = str(int(current_qty)) if current_qty.is_integer() else f"{current_qty:g}"
                
                sold_qty, is_conflict = 0.0, False
                mapped_id = iiko_mappings.get(name)
                
                if mapped_id and mapped_id in sold_items_by_id:
                    if mapped_count.get(mapped_id, 0) > 1:
                        is_conflict, conflict_found = True, True
                    else:
                        sold_qty = sold_items_by_id[mapped_id]
                elif local_name_lower in sold_items_by_name:
                    sold_qty = sold_items_by_name[local_name_lower]
                else:
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
                    remaining = max(0.0, current_qty - sold_qty)
                    rem_str = str(int(remaining)) if remaining.is_integer() else f"{remaining:g}"
                    sold_str = str(int(sold_qty)) if sold_qty.is_integer() else f"{sold_qty:g}"
                    cat_text += f"• {name}: было {curr_str} -> осталось <b>{rem_str}</b> {unit} (продано {sold_str})\n"
                    cat_added = True
                else:
                    cat_text += f"• {name}: <b>{curr_str}</b> {unit}\n"
                    cat_added = True
            if cat_added: text += cat_text

        if conflict_found:
            text += "\n⚠️ <b>Внимание:</b> некоторые позиции привязаны к общей карточке в iiko. Точный расчёт невозможен.\n"
        elif not found_any_match:
            text += "\n<i>(Совпадений с продажами не найдено. Показаны базовые остатки)</i>\n"

        if len(text) > 3800: text = text[:3800] + "\n\n<i>(Список обрезан)</i>"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить расчет", callback_data="estimated_stock")], [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]])
        await callback.message.edit_text(f"❌ Ошибка при расчете: {e}", reply_markup=keyboard, parse_mode="HTML")