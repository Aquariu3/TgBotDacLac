import math
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.state import inventory, admin_ids, manager_ids, save_state, users_db, last_menu_messages, ADMIN_ID, iiko_async_service, log_service
from app.states.states import AdminEditStates
from app.keyboards.admin_kb import get_adm_categories_menu, get_adm_subcats_menu
from app.keyboards.main_kb import get_main_menu
from app.texts.messages import get_main_menu_text
from app.domain.constants import KEY_ITEMS

router = Router()

@router.callback_query(F.data == "cancel_adm_action")
async def cb_cancel_adm_action(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    await state.clear()
    try: await callback.message.delete()
    except Exception: pass
    
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
    await callback.message.edit_text("✏️ <b>Изменить позиции</b>\nВыберите категорию:", reply_markup=get_adm_categories_menu(), parse_mode="HTML")
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
    if cat == "supplies":
        await callback.message.edit_text("📦 <b>Расходники</b>\nВыберите подкатегорию:", reply_markup=get_adm_subcats_menu(), parse_mode="HTML")
    else:
        buttons = []
        for name, data in inventory.items():
            if data["category"] == cat:
                buttons.append([InlineKeyboardButton(text=f"⚙️ {name}", callback_data=f"adm_item_{name}")])
        buttons.append([InlineKeyboardButton(text="➕ Добавить новую позицию", callback_data=f"adm_add_{cat}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_edit_items")])
        await callback.message.edit_text(f"⚙️ <b>Управление позициями</b>\nВыберите позицию для редактирования или добавьте новую:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("adm_subcat_"))
async def cb_adm_subcat(callback: CallbackQuery, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    subcat = callback.data.replace("adm_subcat_", "")
    buttons = []
    for name, data in inventory.items():
        if data.get("subcategory") == subcat:
            buttons.append([InlineKeyboardButton(text=f"⚙️ {name}", callback_data=f"adm_item_{name}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить новую позицию", callback_data=f"adm_add_supplies_{subcat}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_cat_supplies")])
    title = "🥤 Стаканы" if subcat == "cups" else "🔘 Крышки"
    await callback.message.edit_text(f"⚙️ <b>{title}</b>\nВыберите позицию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("adm_item_"))
async def cb_adm_item_actions(callback: CallbackQuery, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    item_name = callback.data.replace("adm_item_", "")
    if item_name not in inventory:
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    cat = inventory[item_name]["category"]
    subcat = inventory[item_name].get("subcategory")
    back_cb = f"adm_subcat_{subcat}" if subcat else f"adm_cat_{cat}"
    
    buttons = [
        [InlineKeyboardButton(text="✏️ Изменить название", callback_data=f"adm_rename_{item_name}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm_delete_{item_name}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)]
    ]
    await callback.message.edit_text(f"⚙️ <b>Позиция: {item_name}</b>\n\nЧто вы хотите сделать?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("adm_delete_"))
async def cb_adm_delete(callback: CallbackQuery, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    item_name = callback.data.replace("adm_delete_", "")
    if item_name in KEY_ITEMS:
        await callback.answer("⛔ Эту позицию удалять нельзя, она используется в главном меню как ключевая!", show_alert=True)
        return
    if item_name in inventory:
        # Сохраняем данные позиции для возможного отката
        item_data = inventory[item_name]
        log_service.add_log(
            callback.from_user.id, 
            users_db.get(callback.from_user.id, "Админ"), 
            f"удалил(а) позицию «{item_name}»",
            snapshot={"undo_type": "delete", "name": item_name, "data": item_data}
        )
        del inventory[item_name]
        save_state()
        await callback.answer(f"🗑 Позиция {item_name} удалена!", show_alert=True)

@router.callback_query(F.data.startswith("adm_rename_"))
async def cb_adm_rename(callback: CallbackQuery, state: FSMContext, is_admin: bool):
    if not is_admin: 
        await callback.message.delete()
        await callback.answer()
        return
    item_name = callback.data.replace("adm_rename_", "")
    if item_name in KEY_ITEMS:
        await callback.answer("⛔ Ключевые позиции нельзя переименовывать! Иначе они пропадут из главного меню.", show_alert=True)
        return

    await state.update_data(old_name=item_name, prompt_msg_id=callback.message.message_id)
    await state.set_state(AdminEditStates.waiting_for_new_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
    await callback.message.edit_text(f"Текущее название: <b>{item_name}</b>\n\nВведите <b>новое название</b>:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(AdminEditStates.waiting_for_new_name)
async def process_adm_rename(message: Message, state: FSMContext, is_admin: bool):
    if not is_admin: return

    # П.2: защита от не-текстовых сообщений (фото, стикеры и т.п.)
    if not message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение с названием.", reply_markup=kb)
        return

    new_name = message.text.strip()

    # П.3: защита от пустого названия
    if not new_name:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Название не может быть пустым. Введите корректное название:", reply_markup=kb)
        return

    data = await state.get_data()
    old_name = data.get("old_name")
    prompt_msg_id = data.get("prompt_msg_id")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])

    if new_name == old_name:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=prompt_msg_id,
            text=f"❌ Вы ввели то же самое название.\n\nВведите <b>новое название</b>:",
            reply_markup=keyboard, parse_mode="HTML"
        )
        try: await message.delete()
        except Exception: pass
        return

    if new_name in inventory:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=prompt_msg_id,
            text=f"❌ Позиция с таким названием уже существует!\n\nВведите <b>другое название</b>:",
            reply_markup=keyboard, parse_mode="HTML"
        )
        try: await message.delete()
        except Exception: pass
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
    try: await message.delete()
    except Exception: pass

    user_id = message.from_user.id
    user_name = users_db.get(user_id, "Сотрудник")
    is_full = is_admin
    text = f"✅ Название изменено на <b>{new_name}</b>!\n\n" + get_main_menu_text(inventory, is_full, user_name)

    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
            return
        except Exception:
            pass

    msg = await message.answer(text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
    last_menu_messages[user_id] = msg.message_id

@router.callback_query(F.data.startswith("adm_add_"))
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
    await callback.message.edit_text("✍️ Введите <b>название</b> новой позиции:\n<i>(Например: Стакан 500 (шт))</i>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(AdminEditStates.waiting_for_new_item_name)
async def process_adm_add_name(message: Message, state: FSMContext, is_admin: bool):
    if not is_admin: return

    # П.2: защита от не-текстовых сообщений
    if not message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение с названием.", reply_markup=kb)
        return

    new_name = message.text.strip()

    # П.3: защита от пустого названия
    if not new_name:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Название не может быть пустым. Введите корректное название:", reply_markup=kb)
        return

    data = await state.get_data()
    prompt_msg_id = data.get("prompt_msg_id")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])

    if new_name in inventory:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=prompt_msg_id,
            text="❌ Позиция с таким названием уже существует!\n\nВведите <b>другое название</b>:",
            reply_markup=keyboard, parse_mode="HTML"
        )
        try: await message.delete()
        except Exception: pass
        return

    await state.update_data(new_name=new_name)
    await state.set_state(AdminEditStates.waiting_for_new_item_qty)

    try: await message.delete()
    except Exception: pass

    text = f"Позиция: <b>{new_name}</b>\n\nВведите <b>количество</b> (число):"

    if prompt_msg_id:
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            return
        except Exception:
            pass

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.message(AdminEditStates.waiting_for_new_item_qty)
async def process_adm_add_qty(message: Message, state: FSMContext, is_admin: bool):
    if not message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Пожалуйста, отправьте число.", reply_markup=kb)
        return
    try:
        qty = float(message.text.replace(",", "."))
        if not math.isfinite(qty) or qty < 0: raise ValueError
    except ValueError:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        await message.answer("⚠️ Введите корректное число (0 или больше):", reply_markup=kb)
        return
    
    data = await state.get_data()
    new_name = data["new_name"]
    cat = data["add_cat"]
    subcat = data.get("add_subcat")
    prompt_msg_id = data.get("prompt_msg_id")
    
    inventory[new_name] = {"qty": qty, "category": cat, "unit": "шт"}
    if subcat: inventory[new_name]["subcategory"] = subcat
    
    if cat == "food":
        inventory[new_name]["is_dessert"] = True
        inventory[new_name]["display_qty"] = 0.0
        await state.update_data(new_item_name=new_name)
        await state.set_state(AdminEditStates.waiting_for_new_item_display)
        
        try: await message.delete()
        except Exception: pass
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adm_action")]])
        text = "Введите <b>количество на витрине</b> (для десертов):"
        
        if prompt_msg_id:
            try:
                await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
                return
            except Exception:
                pass
                
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        save_state()
        await state.clear()
        
        try: await message.delete()
        except Exception: pass
        
        user_id = message.from_user.id
        user_name = users_db.get(user_id, "Сотрудник")
        is_full = is_admin
        text = f"✅ Позиция <b>{new_name}</b> успешно добавлена!\n\n" + get_main_menu_text(inventory, is_full, user_name)
        
        if prompt_msg_id:
            try:
                await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
                return
            except Exception:
                pass
                
        msg = await message.answer(text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
        last_menu_messages[user_id] = msg.message_id

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
        try:
            await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
            return
        except Exception:
            pass
            
    msg = await message.answer(text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
    last_menu_messages[user_id] = msg.message_id