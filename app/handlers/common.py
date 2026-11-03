from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# ВОТ ЗДЕСЬ МЫ ДОБАВИЛИ manager_ids
from app.state import inventory, users_db, admin_ids, manager_ids, log_service, save_state, last_menu_messages
from app.states.states import InventoryStates
from app.texts.messages import get_main_menu_text, build_inventory_text
from app.keyboards.main_kb import get_main_menu, get_edit_categories_menu

router = Router()

@router.callback_query(F.data == "dismiss_msg")
async def cb_dismiss_msg(callback: CallbackQuery):
    try: await callback.message.delete()
    except Exception: pass
    await callback.answer("Уведомление прочитано")

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    is_admin = user_id in admin_ids or user_id in manager_ids
    
    if user_id not in users_db:
        await state.set_state(InventoryStates.waiting_for_reg_name)
        await message.answer("👋 Привет! Добро пожаловать в систему учета остатков кофейни.\n\nПоскольку вы здесь впервые, пожалуйста, <b>укажите вашу Фамилию и Имя</b> ответным сообщением:", parse_mode="HTML")
        return
    await state.clear()
    user_name = users_db[user_id]
    role_text = "👑 <b>Роль: Управляющий</b>" if is_admin else "☕ <b>Роль: Бариста</b>"
    text = f"Рад видеть вас снова, <b>{user_name}</b>!\n\n{role_text}\n\n" + get_main_menu_text(inventory, is_admin, user_name)
    msg = await message.answer(text, reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    
    last_menu_messages[user_id] = msg.message_id
    save_state()

@router.message(InventoryStates.waiting_for_reg_name)
async def process_registration(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение с вашим именем.")
        return
    full_name = message.text.strip()
    if len(full_name.split()) < 2:
        await message.answer("⚠️ Пожалуйста, введите корректно Фамилию и Имя (например: <i>Иванов Иван</i>):", parse_mode="HTML")
        return
    user_id = message.from_user.id
    users_db[user_id] = full_name
    is_admin = user_id in admin_ids or user_id in manager_ids
    
    log_service.add_log(user_id, full_name, "зарегистрировался(ась) в боте")
    save_state()
    await state.clear()
    
    role_text = "👑 <b>Роль: Управляющий</b>" if is_admin else "☕ <b>Роль: Бариста</b>"
    text = f"✅ Регистрация успешно завершена!\nДобро пожаловать, <b>{full_name}</b>.\n\n{role_text}\n\n" + get_main_menu_text(inventory, is_admin, full_name)
    msg = await message.answer(text, reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    
    last_menu_messages[user_id] = msg.message_id
    save_state()

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    is_admin = callback.from_user.id in admin_ids or callback.from_user.id in manager_ids
    
    user_name = users_db.get(callback.from_user.id, "Сотрудник")
    text = get_main_menu_text(inventory, is_admin, user_name)
    msg = await callback.message.edit_text(text, reply_markup=get_main_menu(is_admin), parse_mode="HTML")
    
    last_menu_messages[callback.from_user.id] = msg.message_id
    save_state()
    await callback.answer()

@router.callback_query(F.data == "edit_categories_menu")
async def cb_edit_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("✏️ <b>Редактирование по категориям</b>\nВыберите нужный раздел:", reply_markup=get_edit_categories_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "view_all")
async def cb_view_all(callback: CallbackQuery):
    text = build_inventory_text(inventory, "📊 <b>Текущие остатки на складе:</b>\n")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()