import math
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.state import inventory, admin_ids, manager_ids, save_state, users_db, last_menu_messages, ADMIN_ID, iiko_async_service, log_service
from app.states.states import AdminEditStates
from app.keyboards.admin_kb import get_adm_categories_menu, get_adm_subcats_menu
from app.keyboards.main_kb import get_main_menu
from app.texts.messages import get_main_menu_text
from app.text_utils import make_item_hash
from app.state import find_item_by_hash
from app.telegram_utils import safe_edit
from app.domain.constants import KEY_ITEMS

router = Router()

# --- Вспомогательная функция для отрисовки меню ---
async def _render_adm_cat_menu(message: Message, cat: str, subcat: str | None = None):
    if subcat:
        buttons = []
        for name, data in inventory.items():
            if data.get("subcategory") == subcat:
                buttons.append([InlineKeyboardButton(text=f"⚙️ {name}", callback_data=f"adm_item_{make_item_hash(name)}")])
        buttons.append([InlineKeyboardButton(text="➕ Добавить новую позицию", callback_data=f"adm_add_supplies_{subcat}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_cat_supplies")])
        title = "🥤 Стаканы" if subcat == "cups" else "🔘 Крышки"
        try:
            await message.edit_text(f"⚙️ <b>{title}</b>\nВыберите позицию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
        except Exception as e:
            logging.warning(f"_render_adm_cat_menu: {e}")
    elif cat == "supplies":
        try:
            await message.edit_text("📦 <b>Расходники</b>\nВыберите подкатегорию:", reply_markup=get_adm_subcats_menu(), parse_mode="HTML")
        except Exception as e:
            logging.warning(f"_render_adm_cat_menu: {e}")
    else:
        buttons = []
        for name, data in inventory.items():
            if data["category"] == cat:
                buttons.append([InlineKeyboardButton(text=f"⚙️ {name}", callback_data=f"adm_item_{make_item_hash(name)}")])
        buttons.append([InlineKeyboardButton(text="➕ Добавить новую позицию", callback_data=f"adm_add_{cat}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_edit_items")])
        try:
            await message.edit_text(f"⚙️ <b>Управление позициями</b>\nВыберите позицию для редактирования или добавьте новую:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
        except Exception as e:
            logging.warning(f"_render_adm_cat_menu: {e}")
# --------------------------------------------------

@router.callback_query(F.data == "cancel_adm_action")
async def cb_cancel_adm_action(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    await state.clear()
    try: await callback.message.delete()
    except Exception: pass
    if not is_admin:
        await callback.message.answer("⛔ У вас нет прав! Нажмите /start")
        await callback.answer()
        return
    text = "✏️ <b>Изменить позиции</b>\nВыберите категорию:"
    await callback.message.answer(text, reply_markup=get_adm_categories_menu(), parse_mode="HTML")
    await callback.answer("Отменено")

@router.callback_query(F.data == "admin_edit_items")
async def cb_admin_edit_items(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.message.answer("⛔ У вас нет прав! Нажмите /start")
        return
    await state.clear()
    await safe_edit(callback.message, "✏️ <b>Изменить позиции</b>\nВыберите категорию:", reply_markup=get_adm_categories_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "adm_sync_units")
async def cb_adm_sync_units(callback: CallbackQuery, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.message.answer("⛔ У вас нет прав! Нажмите /start")
        return
    
    await callback.message.edit_text("⏳ <b>Запрашиваем данные из iiko...</b>\nПожалуйста, подождите (это может занять пару секунд).", parse_mode="HTML")
    try:
        updated = await iiko_async_service.sync_inventory_units(inventory)
        save_state()
        await callback.message.edit_text(
            f"✅ <b>Синхронизация завершена!</b>\nОбновлено единиц измерения: <b>{updated}</b>\n\nНажмите /start для выхода.", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_edit_items")]]),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_edit_items")]]))
    await callback.answer()

@router.callback_query(F.data.startswith("adm_cat_"))
async def cb_adm_cat(callback: CallbackQuery, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    cat = callback.data.replace("adm_cat_", "")
    await _render_adm_cat_menu(callback.message, cat, None)
    await callback.answer()

@router.callback_query(F.data.startswith("adm_subcat_"))
async def cb_adm_subcat(callback: CallbackQuery, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    subcat = callback.data.replace("adm_subcat_", "")
    await _render_adm_cat_menu(callback.message, "supplies", subcat)
    await callback.answer()

@router.callback_query(F.data.startswith("adm_item_"))
async def cb_adm_item_actions(callback: CallbackQuery, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    item_hash = callback.data.replace("adm_item_", "")
    item_name =find_item_by_hash(item_hash)
    if not item_name or item_name not in inventory:
        await callback.answer("Позиция не найдена (возможно, уже удалена)", show_alert=True)
        return
    cat = inventory[item_name]["category"]
    subcat = inventory[item_name].get("subcategory")
    back_cb = f"adm_subcat_{subcat}" if subcat else f"adm_cat_{cat}"
    
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"adm_rename_{make_item_hash(item_name)}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_delete_{make_item_hash(item_name)}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)]
    ]
    await safe_edit(callback.message, f"⚙️ <b>Позиция: {item_name}</b>\n\nЧто вы хотите сделать?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("adm_delete_"))
async def cb_adm_delete(callback: CallbackQuery, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    item_hash = callback.data.replace("adm_delete_", "")
    item_name = find_item_by_hash(item_hash)
    if not item_name:
        await callback.answer("Позиция не найдена (возможно, уже удалена)", show_alert=True)
        return
    if item_name in KEY_ITEMS:
        await callback.answer("⛔ Эту позицию удалять нельзя, она используется в главном меню как ключевая!", show_alert=True)
        return
    if item_name in inventory:
        item_data = inventory[item_name]
        cat = item_data["category"]
        subcat = item_data.get("subcategory")
        
        log_service.add_log(
            callback.from_user.id, 
            users_db.get(callback.from_user.id, "Админ"), 
            f"удалил(а) позицию «{item_name}»",
            snapshot={"undo_type": "delete", "name": item_name, "data": item_data}
        )
        del inventory[item_name]
        save_state()
        
        await _render_adm_cat_menu(callback.message, cat, subcat)
        await callback.answer(f"🗑 Позиция {item_name} удалена!", show_alert=False)

@router.callback_query(F.data.startswith("adm_rename_"))
async def cb_adm_rename(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    item_hash = callback.data.replace("adm_rename_", "")
    item_name = find_item_by_hash(item_hash)
    if not item_name:
        await callback.answer("Позиция не найдена (возможно, уже удалена)", show_alert=True)
        return
    if item_name in KEY_ITEMS:
        await callback.answer("⛔ Ключевые позиции нельзя переименовывать! Иначе они пропадут из главного меню.", show_alert=True)
        return

    await state.update_data(old_name=item_name, prompt_msg_id=callback.message.message_id)
    await state.set_state(AdminEditStates.waiting_for_new_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
    await safe_edit(callback.message, f"Текущее название: <b>{item_name}</b>\n\nВведите <b>новое название</b>:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(AdminEditStates.waiting_for_new_name)
async def process_adm_rename(message: Message, state: FSMContext, is_admin: bool):
    if not is_admin: return

    if not message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение с названием.", reply_markup=kb)
        return

    new_name = message.text.strip()

    if not new_name or len(new_name) > 50:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Название не может быть пустым или длиннее 50 символов. Введите корректное название:", reply_markup=kb)
        return

    data = await state.get_data()
    old_name = data.get("old_name")
    prompt_msg_id = data.get("prompt_msg_id")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])

    try: await message.delete()
    except Exception: pass

    if new_name == old_name:
        text = f"❌ Вы ввели то же самое название.\n\nВведите <b>новое название</b>:"
        if prompt_msg_id:
            try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
            except Exception: pass
        msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id) # Запоминаем ID нового сообщения
        return

    if new_name in inventory:
        text = f"❌ Позиция с таким названием уже существует!\n\nВведите <b>другое название</b>:"
        if prompt_msg_id:
            try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
            except Exception: pass
        msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id) # Запоминаем ID нового сообщения
        return

    if old_name in inventory:
        log_service.add_log(
            message.from_user.id,
            users_db.get(message.from_user.id, "Админ"),
            f"переименовал(а) «{old_name}» → «{new_name}»",
            snapshot={"undo_type": "rename", "old_name": old_name, "new_name": new_name}
        )
        inventory[new_name] = inventory.pop(old_name)
        save_state()

    await state.clear()

    user_id = message.from_user.id
    user_name = users_db.get(user_id, "Сотрудник")
    is_full = is_admin
    text = f"✅ Название изменено на <b>{new_name}</b>!\n\n" + get_main_menu_text(inventory, is_full, user_name)

    if prompt_msg_id:
        try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception: pass

    msg = await message.answer(text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
    last_menu_messages[user_id] = msg.message_id

@router.callback_query(F.data.startswith("adm_add_") & ~F.data.startswith("adm_add_type_"))
async def cb_adm_add(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    parts = callback.data.split("_")
    cat = parts[2]
    subcat = parts[3] if len(parts) > 3 and parts[3] != "None" else None
    
    await state.update_data(add_cat=cat, add_subcat=subcat, prompt_msg_id=callback.message.message_id)
    await state.set_state(AdminEditStates.waiting_for_new_item_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
    await safe_edit(callback.message, "✍️ Введите <b>название</b> новой позиции:\n<i>(Например: Стакан 500 (шт))</i>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(AdminEditStates.waiting_for_new_item_name)
async def process_adm_add_name(message: Message, state: FSMContext, is_admin: bool):
    if not is_admin: return

    if not message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение с названием.", reply_markup=kb)
        return

    new_name = message.text.strip()

    if not new_name or len(new_name) > 50:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Название не может быть пустым или длиннее 50 символов. Введите корректное название:", reply_markup=kb)
        return

    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])

    try: await message.delete()
    except Exception: pass

    if new_name in inventory:
        text = "❌ Позиция с таким названием уже существует!\n\nВведите <b>другое название</b>:"
        if prompt_msg_id:
            try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
            except Exception: pass
        msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id) # Сохраняем ID нового сообщения!
        return

    await state.update_data(new_name=new_name)
    await state.set_state(AdminEditStates.waiting_for_new_item_qty)

    text = f"Позиция: <b>{new_name}</b>\n\nВведите <b>количество</b> (число):"

    if prompt_msg_id:
        try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception: pass

    msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(prompt_msg_id=msg.message_id) # Сохраняем ID сообщения с вопросом о количестве!

@router.message(AdminEditStates.waiting_for_new_item_qty)
async def process_adm_add_qty(message: Message, state: FSMContext, is_admin: bool):
    if not is_admin: return
    
    if not message.text:
        try: await message.delete()
        except Exception: pass
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Пожалуйста, отправьте число.", reply_markup=kb)
        return
        
    try:
        qty = float(message.text.replace(",", "."))
        if not math.isfinite(qty) or qty < 0: raise ValueError
    except ValueError:
        try: await message.delete()
        except Exception: pass
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Введите корректное число (0 или больше):", reply_markup=kb)
        return
    
    data = await state.get_data()
    new_name = data.get("new_name")
    cat = data.get("add_cat")
    subcat = data.get("add_subcat")
    prompt_msg_id = data.get("prompt_msg_id")
    
    try: await message.delete()
    except Exception: pass
    
    if cat == "food":
        await state.update_data(new_item_qty=qty)
        await state.set_state(AdminEditStates.waiting_for_food_type)
        
        if prompt_msg_id:
            try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
            except Exception: pass
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🍰 Десерт (есть витрина)", callback_data="adm_add_type_dessert")],
            [InlineKeyboardButton(text="🥪 Блюдо (без витрины)", callback_data="adm_add_type_dish")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]
        ])
        text = f"Позиция: <b>{new_name}</b>\nКоличество: <b>{qty}</b>\n\n<b>Что это за позиция?</b>\n• Десерт — учитывается витрина отдельно\n• Блюдо — обычная позиция"
        
        msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(prompt_msg_id=msg.message_id)
        return
    
    # Если это НЕ еда, создаем позицию здесь
    inventory[new_name] = {"qty": qty, "category": cat, "unit": "шт"}
    if subcat: inventory[new_name]["subcategory"] = subcat
    
    log_service.add_log(
        message.from_user.id,
        users_db.get(message.from_user.id, "Админ"),
        f"добавил(а) новую позицию «{new_name}»",
        snapshot={"undo_type": "add", "name": new_name}
    )
    save_state()
    await state.clear()
    
    user_id = message.from_user.id
    user_name = users_db.get(user_id, "Сотрудник")
    is_full = is_admin
    success_text = f"✅ Позиция <b>{new_name}</b> успешно добавлена!\n\n" + get_main_menu_text(inventory, is_full, user_name)
    
    if prompt_msg_id:
        try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception: pass
            
    msg = await message.answer(success_text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
    last_menu_messages[user_id] = msg.message_id

@router.callback_query(F.data == "adm_add_type_dessert", AdminEditStates.waiting_for_food_type)
async def cb_adm_add_type_dessert(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    if not is_admin:
        await callback.answer()
        return
    data = await state.get_data()
    new_name = data["new_name"]
    qty = data["new_item_qty"]
    cat = data["add_cat"]
    subcat = data.get("add_subcat")
    prompt_msg_id = data.get("prompt_msg_id")
    
    inventory[new_name] = {"qty": qty, "category": cat, "unit": "шт", "is_dessert": True, "display_qty": 0.0}
    if subcat: inventory[new_name]["subcategory"] = subcat
    
    await state.update_data(new_item_name=new_name)
    await state.set_state(AdminEditStates.waiting_for_new_item_display)
    
    try: await callback.message.delete()
    except Exception: pass
    
    if prompt_msg_id:
        try: await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=prompt_msg_id)
        except Exception: pass
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
    text = f"✅ Позиция <b>{new_name}</b> — десерт.\n\nВведите <b>количество на витрине</b>:"
    
    msg = await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(prompt_msg_id=msg.message_id)
    await callback.answer()

@router.callback_query(F.data == "adm_add_type_dish", AdminEditStates.waiting_for_food_type)
async def cb_adm_add_type_dish(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    if not is_admin:
        await callback.answer()
        return
    data = await state.get_data()
    new_name = data["new_name"]
    qty = data["new_item_qty"]
    cat = data["add_cat"]
    subcat = data.get("add_subcat")
    prompt_msg_id = data.get("prompt_msg_id")
    
    inventory[new_name] = {"qty": qty, "category": cat, "unit": "шт"}
    if subcat: inventory[new_name]["subcategory"] = subcat
    
    log_service.add_log(
        callback.from_user.id,
        users_db.get(callback.from_user.id, "Админ"),
        f"добавил(а) новую позицию «{new_name}»",
        snapshot={"undo_type": "add", "name": new_name}
    )
    save_state()
    await state.clear()
    
    try: await callback.message.delete()
    except Exception: pass
    
    if prompt_msg_id:
        try: await callback.bot.delete_message(chat_id=callback.message.chat.id, message_id=prompt_msg_id)
        except Exception: pass
        
    user_name = users_db.get(callback.from_user.id, "Сотрудник")
    text = f"✅ Позиция <b>{new_name}</b> успешно добавлена!\n\n" + get_main_menu_text(inventory, is_admin, user_name)
    
    msg = await callback.message.answer(text, reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    last_menu_messages[callback.from_user.id] = msg.message_id
    await callback.answer()

@router.message(AdminEditStates.waiting_for_new_item_display)
async def process_adm_add_display(message: Message, state: FSMContext, is_admin: bool):
    if not is_admin: return
    if not message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Пожалуйста, отправьте число.", reply_markup=kb)
        return
    try:
        val = float(message.text.replace(",", "."))
        if not math.isfinite(val) or val < 0: raise ValueError
    except ValueError:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Введите корректное число (0 или больше):", reply_markup=kb)
        return
    
    data = await state.get_data()
    new_name = data["new_item_name"]
    prompt_msg_id = data.get("prompt_msg_id")
    
    inventory[new_name]["display_qty"] = val
    log_service.add_log(
        message.from_user.id,
        users_db.get(message.from_user.id, "Админ"),
        f"добавил(а) новую позицию «{new_name}»",
        snapshot={"undo_type": "add", "name": new_name}
    )
    save_state()
    await state.clear()
    
    try: await message.delete()
    except Exception: pass
    
    user_id = message.from_user.id
    user_name = users_db.get(user_id, "Сотрудник")
    is_full = is_admin
    text = f"✅ Позиция <b>{new_name}</b> успешно добавлена!\n\n" + get_main_menu_text(inventory, is_full, user_name)
    
    if prompt_msg_id:
        try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception: pass
            
    msg = await message.answer(text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
    last_menu_messages[user_id] = msg.message_id