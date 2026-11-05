import math
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.state import inventory, users_db, ADMIN_ID, log_service, save_state, manager_ids, admin_ids
from app.states.states import InventoryStates
from app.keyboards.main_kb import get_main_menu
from app.keyboards.inventory_kb import (
    build_coffee_keyboard, build_milk_keyboard, build_drinks_keyboard, 
    build_supplies_keyboard, build_subcat_keyboard, build_food_keyboard
)

router = Router()

@router.callback_query(F.data == "category_coffee")
async def cb_coffee(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("☕ <b>Категория: Кофе</b>\nНажмите на позицию для редактирования:", reply_markup=build_coffee_keyboard(inventory), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "category_milk")
async def cb_milk(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🥛 <b>Категория: Молочка</b>\nНажмите на позицию для редактирования:", reply_markup=build_milk_keyboard(inventory), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "category_drinks")
async def cb_drinks(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🥤 <b>Категория: Напитки в банке</b>\nНажмите на позицию для редактирования:", reply_markup=build_drinks_keyboard(inventory), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "category_supplies")
async def cb_supplies(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("📦 <b>Категория: Расходники</b>\nВыберите подкатегорию:", reply_markup=build_supplies_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("subcat_"))
async def cb_subcat(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    subcat = callback.data.replace("subcat_", "")
    title = "🥤 Стаканы" if subcat == "cups" else "🔘 Крышки"
    await callback.message.edit_text(f"<b>{title}</b>\nНажмите на позицию для редактирования:", reply_markup=build_subcat_keyboard(inventory, subcat), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "category_food")
async def cb_food(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🍰 <b>Категория: Десерты и Еда</b>\nВыберите позицию:", reply_markup=build_food_keyboard(inventory), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("set_"))
async def cb_set_item_qty(callback: CallbackQuery, state: FSMContext):
    item_name = callback.data[len("set_"):]
    if item_name not in inventory:
        await callback.answer("❌ Позиция не найдена!", show_alert=True)
        return
    data_item = inventory[item_name]
    is_dessert = data_item.get("is_dessert")
    unit = data_item.get("unit", "шт")
    
    await state.update_data(item_name=item_name, is_dessert=is_dessert, prompt_msg_id=callback.message.message_id)
    await state.set_state(InventoryStates.waiting_for_new_qty)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="edit_categories_menu")]])
    
    if is_dessert:
        text = (f"✍️ Позиция: <b>{item_name}</b>\nТекущие значения: всего <b>{data_item['qty']}</b> {unit}, витрина <b>{data_item['display_qty']}</b>\n\nВведите <b>общее количество</b> ответным сообщением:")
    else:
        text = (f"✍️ Позиция: <b>{item_name}</b>\nТекущий остаток: <b>{data_item['qty']}</b> {unit}\n\nВведите <b>новое точное число</b> ответным сообщением:")
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(InventoryStates.waiting_for_new_qty)
async def process_new_qty(message: Message, state: FSMContext):
    if not message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="edit_categories_menu")]])
        await message.answer("⚠️ Пожалуйста, отправьте число.", reply_markup=kb)
        return
    try:
        val = float(message.text.replace(",", "."))
        if not math.isfinite(val) or val < 0: raise ValueError
    except ValueError:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="edit_categories_menu")]])
        await message.answer("⚠️ Пожалуйста, введите корректное число (0 или больше):", reply_markup=kb)
        return
    data = await state.get_data()
    item_name = data.get("item_name")
    is_dessert = data.get("is_dessert")
    prompt_msg_id = data.get("prompt_msg_id")
    
    try: await message.delete()
    except Exception: pass
    
    if is_dessert:
        await state.update_data(temp_total_qty=round(val, 2))
        await state.set_state(InventoryStates.waiting_for_new_qty_display)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="edit_categories_menu")]])
        unit = inventory[item_name].get("unit", "шт")
        text = f"✅ Общее количество: <b>{round(val, 2)}</b> {unit}\n\nТеперь введите <b>количество на витрине</b>:"
        if prompt_msg_id:
            try: await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
            except Exception: await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return
    
    await state.clear()
    if not item_name or item_name not in inventory:
        await message.answer("❌ Ошибка: позиция не найдена.", reply_markup=get_main_menu(message.from_user.id == ADMIN_ID))
        return
    
    inventory[item_name]["qty"] = round(val, 2)
    new_val = inventory[item_name]["qty"]
    unit = inventory[item_name].get("unit", "шт")
    
    log_service.add_log(message.from_user.id, users_db.get(message.from_user.id, "Неизвестный"), f"точечно изменил(а) «{item_name}» → {new_val} {unit}")
    save_state()
    
    cat = inventory[item_name]["category"]
    if cat == "coffee": text, kb = "☕ <b>Категория: Кофе</b>", build_coffee_keyboard(inventory)
    elif cat == "milk": text, kb = "🥛 <b>Категория: Молочка</b>", build_milk_keyboard(inventory)
    elif cat == "drinks": text, kb = "🥤 <b>Напитки в банке</b>", build_drinks_keyboard(inventory)
    elif cat == "supplies":
        sub = inventory[item_name].get("subcategory")
        text, kb = f"<b>{'🥤 Стаканы' if sub == 'cups' else '🔘 Крышки'}</b>", build_subcat_keyboard(inventory, sub)
    else: text, kb = "🍰 <b>Десерты и Еда</b>", build_food_keyboard(inventory)
    
    text = f"✅ «{item_name}» → <b>{new_val}</b> {unit}\n\n{text}"
    if prompt_msg_id:
        try: await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=kb, parse_mode="HTML")
        except Exception: await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(InventoryStates.waiting_for_new_qty_display)
async def process_new_qty_display(message: Message, state: FSMContext):
    if not message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="edit_categories_menu")]])
        await message.answer("⚠️ Пожалуйста, отправьте число.", reply_markup=kb)
        return
    try:
        val = float(message.text.replace(",", "."))
        if not math.isfinite(val) or val < 0: raise ValueError
    except ValueError:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="edit_categories_menu")]])
        await message.answer("⚠️ Пожалуйста, введите корректное число (0 или больше):", reply_markup=kb)
        return
    data = await state.get_data()
    item_name = data.get("item_name")
    total_qty = data.get("temp_total_qty")
    prompt_msg_id = data.get("prompt_msg_id")
    await state.clear()
    
    try: await message.delete()
    except Exception: pass
    
    inventory[item_name]["qty"] = total_qty
    inventory[item_name]["display_qty"] = round(val, 2)
    unit = inventory[item_name].get("unit", "шт")
    
    log_service.add_log(message.from_user.id, users_db.get(message.from_user.id, "Неизвестный"), f"точечно изменил(а) «{item_name}»: всего {total_qty} {unit}, витрина {round(val, 2)}")
    save_state()
    
    text = f"✅ «{item_name}» обновлено:\n• Всего: <b>{total_qty}</b> {unit}\n• Витрина: <b>{round(val, 2)}</b>"
    if prompt_msg_id:
        try: await message.bot.edit_message_text(chat_id=message.chat.id, message_id=prompt_msg_id, text=text, reply_markup=build_food_keyboard(inventory), parse_mode="HTML")
        except Exception: await message.answer(text, reply_markup=build_food_keyboard(inventory), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=build_food_keyboard(inventory), parse_mode="HTML")