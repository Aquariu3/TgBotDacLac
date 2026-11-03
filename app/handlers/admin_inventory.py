from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.state import inventory, admin_ids, manager_ids, save_state, users_db, last_menu_messages, ADMIN_ID, iiko_async_service
from app.states.states import AdminEditStates
from app.keyboards.admin_kb import get_adm_categories_menu, get_adm_subcats_menu
from app.keyboards.main_kb import get_main_menu
from app.texts.messages import get_main_menu_text
from app.domain.constants import KEY_ITEMS

router = Router()

@router.callback_query(F.data == "admin_edit_items")
async def cb_admin_edit_items(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.from_user.id not in admin_ids and callback.from_user.id not in manager_ids and callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text("✏️ <b>Изменить позиции</b>\nВыберите категорию:", reply_markup=get_adm_categories_menu())
    await callback.answer()

# --- НОВЫЙ ОБРАБОТЧИК СИНХРОНИЗАЦИИ ---
@router.callback_query(F.data == "adm_sync_units")
async def cb_adm_sync_units(callback: CallbackQuery):
    if callback.from_user.id not in admin_ids and callback.from_user.id not in manager_ids and callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text("⏳ <b>Запрашиваем данные из iiko...</b>\nПожалуйста, подождите (это может занять пару секунд).")
    try:
        updated = await iiko_async_service.sync_inventory_units(inventory)
        save_state()
        await callback.message.edit_text(
            f"✅ <b>Синхронизация завершена!</b>\nОбновлено единиц измерения: <b>{updated}</b>\n\nНажмите /start для выхода.", 
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_edit_items")]])
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_edit_items")]]))
    await callback.answer()

@router.callback_query(F.data.startswith("adm_cat_"))
async def cb_adm_cat(callback: CallbackQuery):
    cat = callback.data.replace("adm_cat_", "")
    if cat == "supplies":
        await callback.message.edit_text("📦 <b>Расходники</b>\nВыберите подкатегорию:", reply_markup=get_adm_subcats_menu())
    else:
        buttons = []
        for name, data in inventory.items():
            if data["category"] == cat:
                buttons.append([InlineKeyboardButton(text=f"⚙️ {name}", callback_data=f"adm_item_{name}")])
        buttons.append([InlineKeyboardButton(text="➕ Добавить новую позицию", callback_data=f"adm_add_{cat}")])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_edit_items")])
        await callback.message.edit_text(f"⚙️ <b>Управление позициями</b>\nВыберите позицию для редактирования или добавьте новую:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("adm_subcat_"))
async def cb_adm_subcat(callback: CallbackQuery):
    subcat = callback.data.replace("adm_subcat_", "")
    buttons = []
    for name, data in inventory.items():
        if data.get("subcategory") == subcat:
            buttons.append([InlineKeyboardButton(text=f"⚙️ {name}", callback_data=f"adm_item_{name}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить новую позицию", callback_data=f"adm_add_supplies_{subcat}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_cat_supplies")])
    title = "🥤 Стаканы" if subcat == "cups" else "🔘 Крышки"
    await callback.message.edit_text(f"⚙️ <b>{title}</b>\nВыберите позицию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("adm_item_"))
async def cb_adm_item_actions(callback: CallbackQuery):
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
    await callback.message.edit_text(f"⚙️ <b>Позиция: {item_name}</b>\n\nЧто вы хотите сделать?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("adm_delete_"))
async def cb_adm_delete(callback: CallbackQuery):
    item_name = callback.data.replace("adm_delete_", "")
    if item_name in KEY_ITEMS:
        await callback.answer("⛔ Эту позицию удалять нельзя, она используется в главном меню как ключевая!", show_alert=True)
        return
    if item_name in inventory:
        del inventory[item_name]
        save_state()
        await callback.answer(f"🗑 Позиция {item_name} удалена!", show_alert=True)
    await callback.message.edit_text("✏️ <b>Изменить позиции</b>\nВыберите категорию:", reply_markup=get_adm_categories_menu())

@router.callback_query(F.data.startswith("adm_rename_"))
async def cb_adm_rename(callback: CallbackQuery, state: FSMContext):
    item_name = callback.data.replace("adm_rename_", "")
    if item_name in KEY_ITEMS:
        await callback.answer("⛔ Ключевые позиции нельзя переименовывать! Иначе они пропадут из главного меню.", show_alert=True)
        return

    await state.update_data(old_name=item_name)
    await state.set_state(AdminEditStates.waiting_for_new_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_edit_items")]])
    await callback.message.edit_text(f"Текущее название: <b>{item_name}</b>\n\nВведите <b>новое название</b>:", reply_markup=keyboard)
    await callback.answer()

@router.message(AdminEditStates.waiting_for_new_name)
async def process_adm_rename(message: Message, state: FSMContext):
    new_name = message.text.strip()
    data = await state.get_data()
    old_name = data.get("old_name")
    
    if new_name == old_name:
        await message.answer("❌ Вы ввели то же самое название. Введите другое или нажмите Отмена.")
        return
    if new_name in inventory:
        await message.answer("❌ Позиция с таким названием уже существует! Введите другое:")
        return
        
    if old_name in inventory:
        inventory[new_name] = inventory.pop(old_name)
        save_state()
    
    await state.clear()
    try: await message.delete()
    except Exception: pass
    
    user_id = message.from_user.id
    user_name = users_db.get(user_id, "Сотрудник")
    is_full = (user_id == ADMIN_ID or user_id in manager_ids or user_id in admin_ids)
    text = f"✅ Название изменено на <b>{new_name}</b>!\n\n" + get_main_menu_text(inventory, is_full, user_name)
    msg = await message.answer(text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
    last_menu_messages[user_id] = msg.message_id

@router.callback_query(F.data.startswith("adm_add_"))
async def cb_adm_add(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cat = parts[2]
    subcat = parts[3] if len(parts) > 3 and parts[3] != "None" else None
    
    await state.update_data(add_cat=cat, add_subcat=subcat)
    await state.set_state(AdminEditStates.waiting_for_new_item_name)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_edit_items")]])
    await callback.message.edit_text("✍️ Введите <b>название</b> новой позиции:\n<i>(Например: Стакан 500 (шт))</i>", reply_markup=keyboard)
    await callback.answer()

@router.message(AdminEditStates.waiting_for_new_item_name)
async def process_adm_add_name(message: Message, state: FSMContext):
    new_name = message.text.strip()
    if new_name in inventory:
        await message.answer("❌ Позиция с таким названием уже существует! Введите другое:")
        return
    await state.update_data(new_name=new_name)
    await state.set_state(AdminEditStates.waiting_for_new_item_qty)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_edit_items")]])
    await message.answer(f"Позиция: <b>{new_name}</b>\n\nВведите <b>количество</b> (число):", reply_markup=keyboard)

@router.message(AdminEditStates.waiting_for_new_item_qty)
async def process_adm_add_qty(message: Message, state: FSMContext):
    try:
        qty = float(message.text.replace(",", "."))
        if qty < 0: raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректное число (0 или больше):")
        return
    
    data = await state.get_data()
    new_name = data["new_name"]
    cat = data["add_cat"]
    subcat = data.get("add_subcat")
    
    inventory[new_name] = {"qty": qty, "category": cat, "unit": "шт"} # По умолчанию шт, потом синхронизируем
    if subcat: inventory[new_name]["subcategory"] = subcat
    
    if cat == "food":
        inventory[new_name]["is_dessert"] = True
        inventory[new_name]["display_qty"] = 0.0
        await state.update_data(new_item_name=new_name)
        await state.set_state(AdminEditStates.waiting_for_new_item_display)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_edit_items")]])
        await message.answer("Введите <b>количество на витрине</b> (для десертов):", reply_markup=keyboard)
    else:
        save_state()
        await state.clear()
        try: await message.delete()
        except Exception: pass
        user_id = message.from_user.id
        user_name = users_db.get(user_id, "Сотрудник")
        is_full = (user_id == ADMIN_ID or user_id in manager_ids or user_id in admin_ids)
        text = f"✅ Позиция <b>{new_name}</b> успешно добавлена!\n\n" + get_main_menu_text(inventory, is_full, user_name)
        msg = await message.answer(text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
        last_menu_messages[user_id] = msg.message_id

@router.message(AdminEditStates.waiting_for_new_item_display)
async def process_adm_add_display(message: Message, state: FSMContext):
    try:
        val = float(message.text.replace(",", "."))
        if val < 0: raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректное число (0 или больше):")
        return
    data = await state.get_data()
    new_name = data["new_item_name"]
    inventory[new_name]["display_qty"] = val
    save_state()
    await state.clear()
    try: await message.delete()
    except Exception: pass
    user_id = message.from_user.id
    user_name = users_db.get(user_id, "Сотрудник")
    is_full = (user_id == ADMIN_ID or user_id in manager_ids or user_id in admin_ids)
    text = f"✅ Позиция <b>{new_name}</b> успешно добавлена!\n\n" + get_main_menu_text(inventory, is_full, user_name)
    msg = await message.answer(text, reply_markup=get_main_menu(is_full), parse_mode="HTML")
    last_menu_messages[user_id] = msg.message_id