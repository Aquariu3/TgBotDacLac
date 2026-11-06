import logging
from html import escape
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from app.state import inventory, users_db, admin_ids, manager_ids, log_service, save_state, last_menu_messages, ADMIN_ID
from app.states.states import InventoryStates
from app.texts.messages import get_main_menu_text, build_inventory_text
from app.keyboards.main_kb import get_main_menu, get_edit_categories_menu

router = Router()

@router.callback_query(F.data == "dismiss_msg")
async def cb_dismiss_msg(callback: CallbackQuery):
    try: await callback.message.delete()
    except Exception as e: logging.warning(f"Не удалось удалить уведомление: {e}")
    await callback.answer("Уведомление прочитано")

def get_user_role(is_super: bool, is_manager: bool, is_admin: bool):
    if is_super: return "👑 <b>Роль: Главный администратор</b>", True
    if is_manager: return "💼 <b>Роль: Управляющий</b>", True
    if is_admin: return "🔑 <b>Роль: Администратор</b>", True
    return "☕ <b>Роль: Бариста</b>", False

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, is_super: bool, is_manager: bool, is_admin: bool):
    user_id = message.from_user.id
    
    try: await message.delete()
    except Exception as e: logging.warning(f"Не удалось удалить /start: {e}")
    
    if user_id in last_menu_messages:
        try: await message.bot.delete_message(user_id, last_menu_messages[user_id])
        except Exception as e: logging.warning(f"Не удалось удалить старое меню при /start: {e}")
    
    if user_id not in users_db:
        await state.set_state(InventoryStates.waiting_for_reg_name)
        await message.answer("👋 Привет! Добро пожаловать в систему учета остатков кофейни.\n\nПоскольку вы здесь впервые, пожалуйста, <b>укажите вашу Фамилию и Имя</b> ответным сообщением:", parse_mode="HTML")
        return
    await state.clear()
    user_name = users_db[user_id]
    role_text, has_access = get_user_role(is_super, is_manager, is_admin)
    
    text = f"Рад видеть вас снова, <b>{user_name}</b>!\n\n{role_text}\n\n" + get_main_menu_text(inventory, has_access, user_name)
    msg = await message.answer(text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
    
    last_menu_messages[user_id] = msg.message_id
    save_state()

@router.message(InventoryStates.waiting_for_reg_name)
async def process_registration(message: Message, state: FSMContext, is_super: bool, is_manager: bool, is_admin: bool):
    # ФИКС #31: если пользователь уже зарегистрирован — не перезаписываем имя молча
    if message.from_user.id in users_db:
        await state.clear()
        await message.answer("Вы уже зарегистрированы. Нажмите /start, чтобы открыть меню.")
        return

    if not message.text:
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение с вашим именем.")
        return
    full_name_raw = message.text.strip()
    if len(full_name_raw.split()) < 2:
        await message.answer("⚠️ Пожалуйста, введите корректно Фамилию и Имя (например: <i>Иванов Иван</i>):", parse_mode="HTML")
        return
    if len(full_name_raw) > 60:
        await message.answer("⚠️ Имя слишком длинное. Максимум 60 символов.")
        return

    # ФИКС #12: экранируем HTML — чтобы имя не сломало меню с parse_mode="HTML"
    full_name = escape(full_name_raw)

    user_id = message.from_user.id
    users_db[user_id] = full_name
    
    role_text, has_access = get_user_role(is_super, is_manager, is_admin)
    
    log_service.add_log(user_id, full_name, "зарегистрировался(ась) в боте")
    await state.clear()
    
    try: await message.delete()
    except Exception as e: logging.warning(f"Не удалось удалить сообщение с именем: {e}")
    
    text = f"✅ Регистрация успешно завершена!\nДобро пожаловать, <b>{full_name}</b>.\n\n{role_text}\n\n" + get_main_menu_text(inventory, has_access, full_name)
    msg = await message.answer(text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
    
    last_menu_messages[user_id] = msg.message_id
    save_state()

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext, is_super: bool, is_manager: bool, is_admin: bool):
    await state.clear()
    user_name = users_db.get(callback.from_user.id, "Сотрудник")
    role_text, has_access = get_user_role(is_super, is_manager, is_admin)
    
    text = f"Рад видеть вас снова, <b>{user_name}</b>!\n\n{role_text}\n\n" + get_main_menu_text(inventory, has_access, user_name)
    
    # ФИКС #2: если меню уже такое — используем текущее сообщение,
    # иначе msg оставался неинициализированным → UnboundLocalError
    msg = callback.message
    try:
        msg = await callback.message.edit_text(text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            msg = await callback.message.answer(text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
        # если "not modified" — msg остаётся callback.message, всё ок
    except Exception as e:
        logging.warning(f"Не удалось отредактировать главное меню, отправляем новое: {e}")
        msg = await callback.message.answer(text, reply_markup=get_main_menu(has_access), parse_mode="HTML")
    
    last_menu_messages[callback.from_user.id] = msg.message_id
    save_state()
    await callback.answer()

@router.callback_query(F.data == "edit_categories_menu")
async def cb_edit_categories(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("✏️ <b>Редактирование по категориям</b>\nВыберите нужный раздел:", reply_markup=get_edit_categories_menu(), parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await callback.message.answer("✏️ <b>Редактирование по категориям</b>\nВыберите нужный раздел:", reply_markup=get_edit_categories_menu(), parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Не удалось открыть меню редактирования: {e}")
        await callback.message.answer("✏️ <b>Редактирование по категориям</b>\nВыберите нужный раздел:", reply_markup=get_edit_categories_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "view_all")
async def cb_view_all(callback: CallbackQuery):
    text = build_inventory_text(inventory, "📊 <b>Текущие остатки на складе:</b>\n")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu")]])
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Не удалось показать все остатки: {e}")
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()