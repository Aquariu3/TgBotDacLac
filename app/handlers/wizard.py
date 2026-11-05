import copy
import logging
import math
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from app.state import inventory, users_db, user_progress, ADMIN_ID, admin_ids, manager_ids, log_service, notification_service, save_state
from app.states.states import InventoryStates
from app.domain.constants import CATEGORY_NAMES
from app.texts.messages import get_main_menu_text, build_inventory_text
from app.keyboards.main_kb import get_main_menu, get_notification_keyboard

router = Router()

def get_next_item(data):
    collected = data.get("collected_data", {})
    active_cat = data.get("active_category")
    all_keys = list(inventory.keys())
    if active_cat:
        for key in all_keys:
            if inventory[key]["category"] == active_cat and key not in collected:
                return key
        data["active_category"] = None
    for key in all_keys:
        if key not in collected:
            return key
    return None

async def _wizard_show_step(bot: Bot, state: FSMContext, chat_id: int):
    data = await state.get_data()
    if "current_item" not in data or data["current_item"] is None:
        data["current_item"] = get_next_item(data)
        await state.update_data(data)
    current_item = data.get("current_item")
    if current_item is None:
        await _wizard_finish(bot, state, chat_id)
        return

    # П.11: если позицию удалили во время мастера — пропускаем её и идём дальше,
    # иначе all_keys.index() ниже упадёт с ValueError.
    if current_item not in inventory:
        data["current_item"] = get_next_item(data)
        await state.update_data(data)
        if data["current_item"] is None:
            await _wizard_finish(bot, state, chat_id)
            return
        current_item = data["current_item"]

    all_keys = list(inventory.keys())
    total = len(all_keys)
    idx = all_keys.index(current_item) + 1
    item_data = inventory[current_item]
    is_dessert = item_data.get("is_dessert")
    unit = item_data.get("unit", "шт")

    # П.11 (доп.): .get(None) вернёт None — используем только если ключ есть
    cat_name = CATEGORY_NAMES.get(data.get("active_category")) if data.get("active_category") else None
    cat_text = f" | Блок: {cat_name}" if cat_name else ""

    if is_dessert:
        current_val_text = f"всего <i>{item_data['qty']}</i> {unit}, витрина <i>{item_data.get('display_qty', 0)}</i>"
        instruction = "✍️ Введите <b>общее количество</b> ответным сообщением"
    else:
        current_val_text = f"<i>{item_data['qty']}</i> {unit}"
        instruction = "✍️ Введите <b>новое число</b> ответным сообщением"
    text = (
        f"📋 <b>Сбор остатков ({idx} из {total})</b>{cat_text}\n\n"
        f"📌 Позиция: <b>{current_item}</b>\n"
        f"Текущее значение: {current_val_text}\n\n"
        f"{instruction}\nили выберите действие:"
    )
    keyboard_buttons = []
    row1 = []
    if data.get("history"):
        row1.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="wizard_back"))
    row1.append(InlineKeyboardButton(text="⏩ Пропустить", callback_data="wizard_skip"))
    keyboard_buttons.append(row1)
    keyboard_buttons.append([InlineKeyboardButton(text="📂 Выбрать блок", callback_data="wizard_choose_block")])
    keyboard_buttons.append([InlineKeyboardButton(text="💾 Сохранить и выйти", callback_data="wizard_save_exit")])
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Отменить сбор (удалить)", callback_data="wizard_cancel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    msg_id = data.get("wizard_message_id")
    if msg_id:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e): return
        except Exception: pass
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(wizard_message_id=sent.message_id)

async def _wizard_finish(bot: Bot, state: FSMContext, chat_id: int):
    data = await state.get_data()
    collected = data.get("collected_data", {})
    msg_id = data.get("wizard_message_id")
    admin_msg_id = data.get("admin_msg_id")
    user_id = data.get("wizard_user_id", chat_id)
    await state.clear()
    if user_id in user_progress:
        del user_progress[user_id]
    for item_name, val in collected.items():
        if item_name in inventory:
            if isinstance(val, dict):
                inventory[item_name]["qty"] = val.get("qty", inventory[item_name]["qty"])
                inventory[item_name]["display_qty"] = val.get("display_qty", inventory[item_name].get("display_qty", 0))
            else:
                inventory[item_name]["qty"] = val
    if msg_id:
        try: await bot.delete_message(chat_id, msg_id)
        except Exception: pass
    user_name = users_db.get(user_id, "Сотрудник")
    is_admin = user_id in admin_ids or user_id in manager_ids
    log_service.add_log(user_id, user_name, "полностью отправил(а) остатки", snapshot=collected)
    save_state()
    if admin_msg_id:
        try: await bot.delete_message(ADMIN_ID, admin_msg_id)
        except Exception: pass
    await notification_service.update_admin_status(bot, ADMIN_ID, user_id, user_name, action="final")
    report_text = build_inventory_text(inventory, f"📦 <b>Итоговый отчет от: {user_name}</b>\n")
    try:
        await bot.send_message(ADMIN_ID, report_text, parse_mode="HTML", reply_markup=get_notification_keyboard())
    except Exception as e:
        logging.error(f"Не удалось отправить отчет управляющему: {e}")
    final_text = f"✅ <b>Все остатки успешно собраны и отправлены управляющему!</b>\n\nСпасибо за работу, {user_name}!\n\n" + get_main_menu_text(inventory, is_admin, user_name)
    await bot.send_message(chat_id=chat_id, text=final_text, reply_markup=get_main_menu(is_admin), parse_mode="HTML")


@router.callback_query(F.data == "start_wizard")
async def start_inventory_wizard(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in user_progress:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Продолжить", callback_data="wizard_resume")],
            [InlineKeyboardButton(text="🔄 Начать заново", callback_data="wizard_restart")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
        ])
        await callback.message.edit_text("У вас есть <b>незавершенный сбор остатков</b>.\n\nХотите продолжить с того же места или начать заново?", reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        return
    if not inventory:
        await callback.answer("❌ Список позиций пуст!", show_alert=True)
        return
    try: await callback.message.delete()
    except Exception: pass
    data = {
        "collected_data": {}, "history": [], "active_category": None,
        "current_item": None, "wizard_message_id": None, "wizard_user_id": user_id, "admin_msg_id": None
    }
    await state.update_data(data)
    await state.set_state(InventoryStates.wizard_qty)
    log_service.add_log(user_id, users_db.get(user_id, "Неизвестный"), "начал(а) составление остатков")
    save_state()
    await notification_service.update_admin_status(callback.bot, ADMIN_ID, user_id, users_db.get(user_id, "Сотрудник"), "Начал(а) делать остатки")
    new_admin_msg_id = await notification_service.update_admin_progress(callback.bot, ADMIN_ID, users_db.get(user_id, "Сотрудник"), data.get("collected_data", {}), inventory, data.get("admin_msg_id"))
    await state.update_data(admin_msg_id=new_admin_msg_id)
    await _wizard_show_step(callback.bot, state, callback.message.chat.id)
    await callback.answer()

@router.callback_query(F.data == "wizard_resume")
async def wizard_resume(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in user_progress:
        saved_data = user_progress.pop(user_id)
        await state.update_data(saved_data)
        await state.set_state(InventoryStates.wizard_qty)
        try: await callback.message.delete()
        except Exception: pass
        log_service.add_log(user_id, users_db.get(user_id, "Неизвестный"), "продолжил(а) сбор остатков из черновика")
        save_state()
        await notification_service.update_admin_status(callback.bot, ADMIN_ID, user_id, users_db.get(user_id, "Сотрудник"), "Продолжил(а) делать остатки")
        new_admin_msg_id = await notification_service.update_admin_progress(callback.bot, ADMIN_ID, users_db.get(user_id, "Сотрудник"), saved_data.get("collected_data", {}), inventory, saved_data.get("admin_msg_id"))
        await state.update_data(admin_msg_id=new_admin_msg_id)
        await _wizard_show_step(callback.bot, state, callback.message.chat.id)
    await callback.answer("▶️ Продолжаем сбор")

@router.callback_query(F.data == "wizard_restart")
async def wizard_restart(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сохранить", callback_data="wizard_restart_save")],
        [InlineKeyboardButton(text="❌ Нет, стереть", callback_data="wizard_restart_drop")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="start_wizard")]
    ])
    await callback.message.edit_text("Вы уверены, что хотите начать заново?\n\n<b>Сохранить ли введенные ранее данные в базу остатков?</b>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "wizard_restart_save")
async def wizard_restart_save(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in user_progress:
        user_progress.pop(user_id) # Просто удаляем черновик, ничего не откатываем
        
    try: await callback.message.delete()
    except Exception: pass
    
    new_data = {
        "collected_data": {}, "history": [], "active_category": None,
        "current_item": None, "wizard_message_id": None, "wizard_user_id": user_id, "admin_msg_id": None
    }
    await state.update_data(new_data)
    await state.set_state(InventoryStates.wizard_qty)
    log_service.add_log(user_id, users_db.get(user_id, "Неизвестный"), "сбросил(а) черновик и начал(а) заново")
    save_state()
    await notification_service.update_admin_status(callback.bot, ADMIN_ID, user_id, users_db.get(user_id, "Сотрудник"), "Сбросил(а) черновик и начал(а) заново")
    new_admin_msg_id = await notification_service.update_admin_progress(callback.bot, ADMIN_ID, users_db.get(user_id, "Сотрудник"), new_data.get("collected_data", {}), inventory, new_data.get("admin_msg_id"))
    await state.update_data(admin_msg_id=new_admin_msg_id)
    await _wizard_show_step(callback.bot, state, callback.message.chat.id)
    await callback.answer("Черновик удален. Начинаем заново.")

@router.callback_query(F.data == "wizard_restart_drop")
async def wizard_restart_drop(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in user_progress:
        user_progress.pop(user_id)
        
    try: await callback.message.delete()
    except Exception: pass
    
    new_data = {
        "collected_data": {}, "history": [], "active_category": None,
        "current_item": None, "wizard_message_id": None, "wizard_user_id": user_id, "admin_msg_id": None
    }
    await state.update_data(new_data)
    await state.set_state(InventoryStates.wizard_qty)
    log_service.add_log(user_id, users_db.get(user_id, "Неизвестный"), "стёр черновик и начал(а) заново")
    save_state()
    await notification_service.update_admin_status(callback.bot, ADMIN_ID, user_id, users_db.get(user_id, "Сотрудник"), "Стёр(ла) черновик и начал(а) заново")
    new_admin_msg_id = await notification_service.update_admin_progress(callback.bot, ADMIN_ID, users_db.get(user_id, "Сотрудник"), new_data.get("collected_data", {}), inventory, new_data.get("admin_msg_id"))
    await state.update_data(admin_msg_id=new_admin_msg_id)
    await _wizard_show_step(callback.bot, state, callback.message.chat.id)
    await callback.answer("Данные удалены. Начинаем заново.")

@router.callback_query(F.data == "wizard_save_exit", InventoryStates.wizard_qty)
async def wizard_save_exit(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    collected = data.get("collected_data", {})
    msg_id = data.get("wizard_message_id")
    admin_msg_id = data.get("admin_msg_id")
    
    # Данные НЕ применяем к inventory. Просто сохраняем как черновик.
    user_progress[user_id] = data
    await state.clear()
    
    if msg_id:
        try: await callback.bot.delete_message(callback.message.chat.id, msg_id)
        except Exception: pass
        
    log_service.add_log(user_id, users_db.get(user_id, "Неизвестный"), "сохранил(а) черновик остатков", snapshot=collected)
    save_state()
    
    if admin_msg_id:
        try: await callback.bot.delete_message(ADMIN_ID, admin_msg_id)
        except Exception: pass
        
    await notification_service.update_admin_status(callback.bot, ADMIN_ID, user_id, users_db.get(user_id, "Сотрудник"), "Сохранил(а) черновик")
    is_admin = user_id in admin_ids or user_id in manager_ids
    user_name = users_db.get(user_id, "Сотрудник")
    text = f"💾 <b>Прогресс сохранен!</b>\n\nВведенные цифры записаны в память. Вы можете вернуться и завершить сбор в любое время.\n\n" + get_main_menu_text(inventory, is_admin, user_name)
    await callback.message.answer(text, reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    await callback.answer("Сохранено")

@router.callback_query(F.data == "wizard_skip", InventoryStates.wizard_qty)
async def wizard_skip_item(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_item = data.get("current_item")
    if current_item:
        if inventory[current_item].get("is_dessert"):
            data.setdefault("collected_data", {})[current_item] = {"qty": inventory[current_item]["qty"], "display_qty": inventory[current_item]["display_qty"]}
        else:
            data.setdefault("collected_data", {})[current_item] = inventory[current_item]["qty"]
        data.setdefault("history", []).append(current_item)
        data["current_item"] = get_next_item(data)
        new_admin_msg_id = await notification_service.update_admin_progress(callback.bot, ADMIN_ID, users_db.get(callback.from_user.id, "Сотрудник"), data.get("collected_data", {}), inventory, data.get("admin_msg_id"))
        data["admin_msg_id"] = new_admin_msg_id
        await state.update_data(data)
    await _wizard_show_step(callback.bot, state, callback.message.chat.id)
    await callback.answer("⏩ Пропущено")

@router.callback_query(F.data == "wizard_back", InventoryStates.wizard_qty)
async def wizard_back_item(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", [])
    if history:
        prev_item = history.pop()
        data["current_item"] = prev_item
        data["active_category"] = None
        if prev_item in data.get("collected_data", {}): del data["collected_data"][prev_item]
        new_admin_msg_id = await notification_service.update_admin_progress(callback.bot, ADMIN_ID, users_db.get(callback.from_user.id, "Сотрудник"), data.get("collected_data", {}), inventory, data.get("admin_msg_id"))
        data["admin_msg_id"] = new_admin_msg_id
        await state.update_data(data)
        await _wizard_show_step(callback.bot, state, callback.message.chat.id)
        await callback.answer("⬅️ Возврат к предыдущей позиции")
    else:
        await callback.answer("Это самая первая позиция")

@router.callback_query(F.data == "wizard_choose_block", InventoryStates.wizard_qty)
async def wizard_choose_block(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☕ Кофе", callback_data="wizard_cat_coffee")],
        [InlineKeyboardButton(text="🥛 Молочка", callback_data="wizard_cat_milk")],
        [InlineKeyboardButton(text="🥤 Напитки", callback_data="wizard_cat_drinks")],
        [InlineKeyboardButton(text="📦 Расходники", callback_data="wizard_cat_supplies")],
        [InlineKeyboardButton(text="🍰 Еда", callback_data="wizard_cat_food")],
        [InlineKeyboardButton(text="⬅️ Назад к позиции", callback_data="wizard_back_to_step")]
    ])
    await callback.message.edit_text("📂 <b>Выберите блок для заполнения:</b>\n\nПосле завершения блока мастер автоматически вернется к общему списку.", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "wizard_back_to_step", InventoryStates.wizard_qty)
async def wizard_back_to_step(callback: CallbackQuery, state: FSMContext):
    await _wizard_show_step(callback.bot, state, callback.message.chat.id)
    await callback.answer()

@router.callback_query(F.data.startswith("wizard_cat_"), InventoryStates.wizard_qty)
async def wizard_select_cat(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.replace("wizard_cat_", "")
    if cat not in CATEGORY_NAMES:
        await callback.answer("Неизвестная категория")
        return
    data = await state.get_data()
    collected = data.get("collected_data", {})
    has_items = any(inventory[k]["category"] == cat and k not in collected for k in inventory)
    if not has_items:
        await callback.answer("В этом блоке все остатки уже заполнены!", show_alert=True)
        return
    data["active_category"] = cat
    current = data.get("current_item")
    if current: data.setdefault("history", []).append(current)
    data["current_item"] = get_next_item(data)
    await state.update_data(data)
    await _wizard_show_step(callback.bot, state, callback.message.chat.id)
    await callback.answer(f"Переход к блоку: {CATEGORY_NAMES[cat]}")

@router.callback_query(F.data == "wizard_cancel")
async def wizard_cancel(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    msg_id = data.get("wizard_message_id")
    admin_msg_id = data.get("admin_msg_id")
    
    if user_id in user_progress:
        user_progress.pop(user_id)
        
    await state.clear()
    
    if msg_id:
        try: await callback.bot.delete_message(callback.message.chat.id, msg_id)
        except Exception: pass
        
    log_service.add_log(user_id, users_db.get(user_id, "Неизвестный"), "отменил(а) составление остатков")
    save_state()
    
    if admin_msg_id:
        try: await callback.bot.delete_message(ADMIN_ID, admin_msg_id)
        except Exception: pass
        
    await notification_service.update_admin_status(callback.bot, ADMIN_ID, user_id, users_db.get(user_id, "Сотрудник"), action="cancel")
    is_admin = user_id in admin_ids or user_id in manager_ids
    user_name = users_db.get(user_id, "Сотрудник")
    text = f"❌ Сбор остатков отменён (черновик удален, склад не тронут).\n\n" + get_main_menu_text(inventory, is_admin, user_name)
    await callback.message.answer(text, reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    await callback.answer()

@router.message(InventoryStates.wizard_qty)
async def process_wizard_qty(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Пожалуйста, отправьте число.")
        return
    try:
        val = float(message.text.replace(",", "."))
        if not math.isfinite(val) or val < 0: raise ValueError
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректное число (0 или больше):")
        return
    data = await state.get_data()
    current_item = data.get("current_item")
    if not current_item: return
    try: await message.delete()
    except Exception: pass
    if inventory[current_item].get("is_dessert"):
        await state.update_data(temp_total_qty=round(val, 2))
        await state.set_state(InventoryStates.wizard_display_qty)
        text = f"📋 <b>Сбор остатков</b>\n\n📌 Позиция: <b>{current_item}</b>\n✅ Общее количество: <b>{round(val, 2)}</b>\n\n✍️ Теперь введите <b>количество на витрине</b>:"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить сбор", callback_data="wizard_cancel")]])
        msg_id = data.get("wizard_message_id")
        if msg_id:
            try: await message.bot.edit_message_text(chat_id=message.chat.id, message_id=msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            except Exception: pass
        return
    data.setdefault("collected_data", {})[current_item] = round(val, 2)
    data.setdefault("history", []).append(current_item)
    data["current_item"] = get_next_item(data)
    new_admin_msg_id = await notification_service.update_admin_progress(message.bot, ADMIN_ID, users_db.get(message.from_user.id, "Сотрудник"), data.get("collected_data", {}), inventory, data.get("admin_msg_id"))
    data["admin_msg_id"] = new_admin_msg_id
    await state.update_data(data)
    await _wizard_show_step(message.bot, state, message.chat.id)

@router.message(InventoryStates.wizard_display_qty)
async def process_wizard_display_qty(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Пожалуйста, отправьте число.")
        return
    try:
        val = float(message.text.replace(",", "."))
        if not math.isfinite(val) or val < 0: raise ValueError
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректное число (0 или больше):")
        return
    data = await state.get_data()
    current_item = data.get("current_item")
    total_qty = data.get("temp_total_qty")
    try: await message.delete()
    except Exception: pass
    data.setdefault("collected_data", {})[current_item] = {"qty": total_qty, "display_qty": round(val, 2)}
    data.setdefault("history", []).append(current_item)
    data["current_item"] = get_next_item(data)
    new_admin_msg_id = await notification_service.update_admin_progress(message.bot, ADMIN_ID, users_db.get(message.from_user.id, "Сотрудник"), data.get("collected_data", {}), inventory, data.get("admin_msg_id"))
    data["admin_msg_id"] = new_admin_msg_id
    await state.set_state(InventoryStates.wizard_qty)
    await state.update_data(data)
    await _wizard_show_step(message.bot, state, message.chat.id)