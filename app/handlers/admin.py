from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from app.state import inventory, users_db, user_progress, admin_ids, manager_ids, log_service, save_state, ADMIN_ID, last_menu_messages
from app.states.states import InventoryStates
from app.keyboards.admin_kb import (
    get_admin_panel_keyboard, 
    get_admin_other_keyboard, 
    get_role_management_keyboard,
    get_users_to_promote_keyboard, 
    get_users_to_demote_keyboard
)

router = Router()

async def _render_role_menu(message: Message, role_type: str):
    is_admin_role = (role_type == "admin")
    role_name = "Администраторы" if is_admin_role else "Управляющие"
    target_set = admin_ids if is_admin_role else manager_ids
    
    current_users = []
    for uid in target_set:
        if uid == ADMIN_ID and is_admin_role:
            continue 
        current_users.append((uid, users_db.get(uid, "Сотрудник")))

    text = f"👑 <b>{role_name}</b>\n\n"
    if not current_users:
        text += "<i>Список пуст.</i>"
    else:
        text += "<b>Текущие:</b>\n"
        for uid, name in current_users:
            text += f"• {name}\n"
            
    await message.edit_text(
        text, 
        reply_markup=get_role_management_keyboard(role_type, current_users), 
        parse_mode="HTML"
    )

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, is_admin: bool, is_manager: bool):
    if not is_admin:
        await callback.message.delete()
        await callback.message.answer("⛔ У вас нет прав администратора! Нажмите /start")
        return
    
    is_full_access = is_manager
    text = "⚙️ <b>Панель Управляющего</b>\n\nЗдесь вы можете контролировать остатки и смотреть активность сотрудников."
    kb = get_admin_panel_keyboard(is_full_access)
    
    if callback.message.text and callback.message.text.startswith(("✅", "💾", "❌", "📝", "🔔")):
        try: await callback.message.delete()
        except Exception: pass
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_other_menu")
async def cb_admin_other_menu(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.message.answer("⛔ У вас нет прав! Нажмите /start")
        return
    
    await callback.message.edit_text(
        "⚙️ <b>Остальное</b>\n\nВыберите действие:", 
        reply_markup=get_admin_other_keyboard(), 
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.in_({"admin_manage_admins", "admin_manage_managers"}))
async def cb_manage_roles(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    role_type = "admin" if callback.data == "admin_manage_admins" else "manager"
    await _render_role_menu(callback.message, role_type)
    await callback.answer()

@router.callback_query(F.data.startswith("admin_add_role_"))
async def cb_admin_add_role(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    role_type = callback.data.replace("admin_add_role_", "")
    is_admin_role = (role_type == "admin")
    target_list = admin_ids if is_admin_role else manager_ids

    keyboard = get_users_to_promote_keyboard(users_db, target_list, role_type)
    
    if len(keyboard.inline_keyboard) == 1:
        await callback.answer("Все зарегистрированные пользователи уже имеют эту роль!", show_alert=True)
        return
        
    await callback.message.edit_text(
        f"👑 <b>Выберите пользователя, чтобы сделать его {'администратором' if is_admin_role else 'управляющим'}:</b>\n\n", 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("make_"))
async def cb_make_role(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    parts = callback.data.split("_")
    role_type = parts[1]
    target_id = int(parts[2])
    
    is_admin_role = (role_type == "admin")
    target_name = users_db.get(target_id, "Сотрудник")
    target_list = admin_ids if is_admin_role else manager_ids
    role_name = "Администратор" if is_admin_role else "Управляющий"

    if target_id not in target_list:
        target_list.add(target_id)
        
        log_service.add_log(
            callback.from_user.id, 
            users_db.get(callback.from_user.id, "Админ"), 
            f"назначил(а) {target_name} {role_name.lower()}ом"
        )
        save_state()
        
        try:
            # Удаляем старое меню пользователя, чтобы не висело
            if target_id in last_menu_messages:
                try: await callback.bot.delete_message(target_id, last_menu_messages[target_id])
                except Exception: pass
            
            # Отправляем уведомление и сохраняем его ID как текущее меню пользователя
            msg = await callback.bot.send_message(
                target_id, 
                f"👑 <b>Вам выданы права {role_name.lower()}а!</b>\n"
                "Нажмите /start, чтобы увидеть панель.", 
                parse_mode="HTML"
            )
            last_menu_messages[target_id] = msg.message_id
        except Exception: pass
    
    await _render_role_menu(callback.message, role_type)
    await callback.answer(f"✅ {target_name} теперь {role_name}!")

@router.callback_query(F.data.startswith("admin_del_role_"))
async def cb_admin_del_role(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    role_type = callback.data.replace("admin_del_role_", "")
    is_admin_role = (role_type == "admin")
    target_list = admin_ids if is_admin_role else manager_ids

    keyboard = get_users_to_demote_keyboard(users_db, target_list, role_type)
    
    await callback.message.edit_text(
        f"❌ <b>Выберите, кого лишить прав {'администратора' if is_admin_role else 'управляющего'}:</b>\n\n", 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("del_"))
async def cb_do_demote(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    parts = callback.data.split("_")
    role_type = parts[1]
    target_id = int(parts[2])
    
    is_admin_role = (role_type == "admin")
    target_list = admin_ids if is_admin_role else manager_ids
    target_name = users_db.get(target_id, "Сотрудник")
    role_name = "Администратора" if is_admin_role else "Управляющего"

    if target_id in target_list:
        target_list.remove(target_id)
        
        log_service.add_log(
            callback.from_user.id, 
            users_db.get(callback.from_user.id, "Админ"), 
            f"лишил(а) {target_name} прав {role_name.lower()}"
        )
        save_state()
        
        try:
            # Удаляем старое меню
            if target_id in last_menu_messages:
                try: await callback.bot.delete_message(target_id, last_menu_messages[target_id])
                except Exception: pass
            
            # Отправляем уведомление и сохраняем его ID
            msg = await callback.bot.send_message(
                target_id, 
                f"⚠️ <b>Ваши права {role_name.lower()}а были отозваны.</b>\n\nЕсли вы сейчас заполняете остатки, нажмите «Сохранить и выйти», чтобы не потерять данные.", 
                parse_mode="HTML"
            )
            last_menu_messages[target_id] = msg.message_id
        except Exception: pass
    
    await _render_role_menu(callback.message, role_type)
    await callback.answer(f"✅ {target_name} больше не {role_name}")

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    
    text = "👥 <b>Пользователи и история действий</b>\n\n"
    text += f"<b>Всего пользователей:</b> {len(users_db)}\n"
    text += "\n<b>📝 В процессе заполнения:</b>\n"
    if not user_progress:
        text += "• <i>Нет активных черновиков</i>\n"
    else:
        for uid, p_data in user_progress.items():
            uname = users_db.get(uid, str(uid))
            collected_count = len(p_data.get("collected_data", {}))
            text += f"• <b>{uname}</b> (заполнено {collected_count} из {len(inventory)})\n"
    text += "\n<b>📋 Последние действия:</b>\n"
    if not log_service.logs:
        text += "• <i>Пока нет действий</i>\n"
    else:
        for log in reversed(log_service.logs[-10:]):
            text += f"• [{log['time']}] <b>{log['user_name']}</b> — {log['action']}\n"
    buttons = []
    for log in reversed(log_service.logs[-10:]):
        if log.get("snapshot") is not None:
            label = "черновик" if "черновик" in log["action"] else "отправку" if "отправил" in log["action"] else "данные"
            buttons.append([InlineKeyboardButton(text=f"👁 Посмотреть {label} ({log['user_name']})", callback_data=f"view_log_{log['id']}")])
    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_users")])
    buttons.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e): pass
    await callback.answer()

@router.callback_query(F.data.startswith("view_log_"))
async def cb_view_log(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    log_id = int(callback.data.replace("view_log_", ""))
    log_entry = next((l for l in log_service.logs if l["id"] == log_id), None)
    if not log_entry or not log_entry["snapshot"]:
        await callback.answer("❌ Данные не найдены или устарели.", show_alert=True)
        return
    text = f"📄 <b>Детали действия</b>\n"
    text += f"Сотрудник: <b>{log_entry['user_name']}</b>\n"
    text += f"Действие: {log_entry['action']}\n"
    text += f"Время: {log_entry['time']}\n\n"
    text += "<b>Введенные данные:</b>\n"
    for name, val in log_entry["snapshot"].items():
        if isinstance(val, dict):
            text += f"• {name}: всего <b>{val.get('qty')}</b>, витрина <b>{val.get('display_qty')}</b>\n"
        else:
            text += f"• {name}: <b>{val}</b>\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в историю", callback_data="admin_users")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_notify")
async def cb_admin_notify(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    buttons = [[InlineKeyboardButton(text="📢 Всем сотрудникам", callback_data="notify_target_all")]]
    for uid, uname in users_db.items():
        if uid not in admin_ids:
            buttons.append([InlineKeyboardButton(text=f"👤 {uname}", callback_data=f"notify_target_{uid}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("📢 <b>Кому отправить уведомление?</b>\nВыберите сотрудника или отправьте всем сразу:", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("notify_target_"))
async def cb_notify_target(callback: CallbackQuery, state: FSMContext, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
    target = callback.data.replace("notify_target_", "")
    await state.update_data(notify_target=target, prompt_msg_id=callback.message.message_id)
    await state.set_state(InventoryStates.waiting_for_broadcast_text)
    target_name = "Всем сотрудникам" if target == "all" else users_db.get(int(target), "Сотруднику")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]])
    await callback.message.edit_text(f"✍️ Введите текст сообщения для <b>{target_name}</b>.\n\n<i>Вы можете использовать HTML-теги.</i>", reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.message(InventoryStates.waiting_for_broadcast_text)
async def process_broadcast(message: Message, state: FSMContext, is_manager: bool):
    if not is_manager: return
    if not message.text:
        await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение.")
        return
    data = await state.get_data()
    target = data.get("notify_target")
    prompt_msg_id = data.get("prompt_msg_id")
    text = message.text
    await state.clear()
    success_count = 0
    fail_count = 0
    notify_text = f"🔔 <b>Уведомление от управляющего:</b>\n\n{text}"
    try: await message.delete()
    except Exception: pass
    if prompt_msg_id:
        try: await message.bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception: pass
    if target == "all":
        for uid in users_db.keys():
            if uid in admin_ids: continue
            try:
                await message.bot.send_message(uid, notify_text, parse_mode="HTML")
                success_count += 1
            except TelegramBadRequest:
                try:
                    await message.bot.send_message(uid, notify_text)
                    success_count += 1
                except Exception:
                    fail_count += 1
            except Exception:
                fail_count += 1
    else:
        try:
            await message.bot.send_message(int(target), notify_text, parse_mode="HTML")
            success_count += 1
        except TelegramBadRequest:
            try:
                await message.bot.send_message(int(target), notify_text)
                success_count += 1
            except Exception:
                fail_count += 1
        except Exception:
            fail_count += 1
    result = f"✅ <b>Уведомление отправлено!</b>\nУспешно доставлено: <b>{success_count}</b>."
    if fail_count:
        result += f"\nНе доставлено: <b>{fail_count}</b> (заблокировали бота)."
    
    await message.answer(result, reply_markup=get_admin_panel_keyboard(True), parse_mode="HTML")