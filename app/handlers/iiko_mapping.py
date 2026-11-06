import logging
import difflib
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from app.state import iiko_async_service, inventory, iiko_mappings, save_state, find_item_by_hash
from app.states.states import AdminEditStates
from app.text_utils import make_item_hash

router = Router()

@router.callback_query(F.data.startswith("admin_mapping"))
async def cb_admin_mapping(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return
    await state.clear()

    try: page = int(callback.data.split("_")[-1])
    except (ValueError, IndexError): page = 0

    all_items = list(inventory.keys())
    items_per_page = 10
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_items = all_items[start_idx:end_idx]
    total_pages = max(1, (len(all_items) + items_per_page - 1) // items_per_page)

    buttons = []
    for name in page_items:
        icon = "✅" if name in iiko_mappings else "❌"
        buttons.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"map_local_{make_item_hash(name)}")])

    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_mapping_{page - 1}"))
    if end_idx < len(all_items): nav_row.append(InlineKeyboardButton(text="Далее ➡️", callback_data=f"admin_mapping_{page + 1}"))
    if nav_row: buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    text = "🔗 <b>Сопоставление позиций</b>\n\nЗдесь вы можете связать позиции из вашего бота с точными названиями (ID) из iiko.\n✅ — уже связано, ❌ — ищет по названию.\n\n"
    if total_pages > 1: text += f"<i>Страница {page + 1} из {total_pages}</i>\n\n"
    text += "Выберите позицию бота, которую хотите связать:"

    try: await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception: pass
    await callback.answer()

def find_best_iiko_matches(local_name: str, products: dict, limit: int = 3) -> list:
    local_clean = local_name.lower().replace("(шт)", "").replace("(кг)", "").replace("(л)", "").replace("(уп)", "").strip()
    if not local_clean: return []
    matches = []
    for pid, p in products.items():
        iiko_name = p["name"]
        iiko_clean = iiko_name.lower().split('_')[0].strip()
        if local_clean in iiko_clean or iiko_clean in local_clean: score = 1.0
        else: score = difflib.SequenceMatcher(None, local_clean, iiko_clean).ratio()
        if score >= 0.5: matches.append((score, pid, iiko_name))
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[:limit]

@router.callback_query(F.data.startswith("map_local_"))
async def cb_map_local(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager: return await callback.answer()
    
    item_hash = callback.data.replace("map_local_", "")
    local_name = find_item_by_hash(item_hash)
    if not local_name: return await callback.answer("Позиция не найдена.", show_alert=True)

    await state.update_data(map_local_name=local_name, prompt_msg_id=callback.message.message_id)
    await callback.message.edit_text(f"⏳ Ищу похожие позиции для <b>{local_name}</b> в базе iiko...", parse_mode="HTML")
    
    try:
        products = await iiko_async_service.get_nomenclature()
        matches = find_best_iiko_matches(local_name, products)
        buttons = []
        if local_name in iiko_mappings:
            buttons.append([InlineKeyboardButton(text="🗑 Убрать текущую связь", callback_data=f"map_unlink_{make_item_hash(local_name)}")])

        if not matches:
            await callback.message.edit_text(
                f"😔 Я не смог найти похожих названий для <b>{local_name}</b> в iiko.\n\nПопробуйте ввести запрос вручную:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Поискать вручную", callback_data=f"map_manual_{make_item_hash(local_name)}")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_mapping")]
                ] + buttons), parse_mode="HTML"
            )
            return await callback.answer()
            
        for score, pid, iiko_name in matches:
            buttons.append([InlineKeyboardButton(text=f"✅ Это оно ({int(score * 100)}%): {iiko_name}", callback_data=f"map_save_{pid}")])
        buttons.append([InlineKeyboardButton(text="🔍 Нет, поищу вручную", callback_data=f"map_manual_{make_item_hash(local_name)}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_mapping")])
        
        await callback.message.edit_text(
            f"🔎 Для позиции <b>{local_name}</b> я нашел вот такие варианты в iiko:\n\nЭто оно? Выберите правильный:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при поиске: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_mapping")]]))
    await callback.answer()

@router.callback_query(F.data.startswith("map_manual_"))
async def cb_map_manual(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager: return await callback.answer()
    item_hash = callback.data.replace("map_manual_", "")
    local_name = find_item_by_hash(item_hash)
    if not local_name: return await callback.answer("Позиция не найдена.", show_alert=True)

    await state.update_data(map_local_name=local_name, prompt_msg_id=callback.message.message_id)
    await state.set_state(AdminEditStates.waiting_for_iiko_search)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_mapping")]])
    await callback.message.edit_text(
        f"Вы выбрали: <b>{local_name}</b>\n\n✍️ Введите <b>часть названия</b> этой позиции так, как она называется в iiko (например: <i>малина</i>):",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminEditStates.waiting_for_iiko_search)
async def process_iiko_search(message: Message, state: FSMContext, is_manager: bool):
    if not is_manager: return
    if not message.text:
        try: await message.delete()
        except Exception: pass
        return await message.answer("⚠️ Пожалуйста, отправьте текст для поиска.")

    query = message.text.strip().lower()
    data = await state.get_data()
    local_name = data.get("map_local_name")
    prompt_msg_id = data.get("prompt_msg_id")
    
    try: await message.delete()
    except Exception: pass
    
    products = await iiko_async_service.get_nomenclature()
    matches = [(pid, p["name"]) for pid, p in products.items() if query in p["name"].lower()][:10]
    
    keyboard = None
    text = ""
    
    if not matches:
        text = f"❌ По запросу «{query}» ничего не найдено в iiko.\nПопробуйте другое слово или вернитесь назад."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_mapping")]])
    else:
        text = f"Связываем <b>{local_name}</b> с:\n\nВыберите правильный вариант из iiko:"
        buttons = [[InlineKeyboardButton(text=p_name, callback_data=f"map_save_{pid}")] for pid, p_name in matches]
        buttons.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_mapping")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    # Пытаемся отредактировать старое сообщение
    edited = False
    if prompt_msg_id:
        try: 
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            edited = True
        except Exception: 
            pass # Если не удалось (например, сообщение удалено middleware), переходим к отправке нового
    
    # Если отредактировать не вышло — ЖЕЛЕЗНО отправляем новое
    if not edited:
        msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id)

async def _save_mapping_and_show(callback: CallbackQuery, state: FSMContext, iiko_id: str):
    data = await state.get_data()
    local_name = data.get("map_local_name")
    if not local_name: 
        return await callback.answer("❌ Сессия устарела.", show_alert=True)
    
    iiko_mappings[local_name] = iiko_id
    save_state()
    
    products = await iiko_async_service.get_nomenclature()
    iiko_name = products.get(iiko_id, {}).get("name", "Неизвестно")
    await state.clear()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Хорошо", callback_data="admin_mapping")]])
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
    if not is_manager: return await callback.answer()
    iiko_id = callback.data.replace("map_save_", "")
    data = await state.get_data()
    local_name = data.get("map_local_name")
    if not local_name: return await callback.answer("❌ Сессия устарела.", show_alert=True)

    conflict_name = next((ol for ol, mi in iiko_mappings.items() if mi == iiko_id and ol != local_name), None)
    if conflict_name:
        buttons = [[InlineKeyboardButton(text="⚠️ Да, я уверен", callback_data=f"map_force_{iiko_id}")], [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_mapping")]]
        await callback.message.edit_text(
            f"⚠️ <b>Внимание!</b>\n\nПозиция iiko с ID <code>{iiko_id}</code> уже привязана к вашему складу как <b>{conflict_name}</b>.\n\n"
            f"Если вы привяжете <b>{local_name}</b> к этому же ID, то бот не сможет точно рассчитать остатки.\n\nВы уверены?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
        )
        return await callback.answer()
    await _save_mapping_and_show(callback, state, iiko_id)

@router.callback_query(F.data.startswith("map_force_"))
async def cb_map_force(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager: return await callback.answer()
    await _save_mapping_and_show(callback, state, callback.data.replace("map_force_", ""))

@router.callback_query(F.data.startswith("map_unlink_"))
async def cb_map_unlink(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager: return await callback.answer()
    local_name = find_item_by_hash(callback.data.replace("map_unlink_", ""))
    if local_name and local_name in iiko_mappings:
        del iiko_mappings[local_name]
        save_state()
        await callback.answer("✅ Связь успешно удалена!", show_alert=True)
        await cb_admin_mapping(callback, state, is_manager)
    else: await callback.answer("Связь не найдена.", show_alert=True)