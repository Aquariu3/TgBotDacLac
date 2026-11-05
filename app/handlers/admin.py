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

    # Группируем действия по пользователям для кнопок
    buttons = []
    recent_logs = list(reversed(log_service.logs[-20:])) # берем последние 20 действий для кнопок
    user_actions = {}
    for log in recent_logs:
        uid = log.get("user_id")
        if uid not in user_actions:
            user_actions[uid] = {"name": log.get("user_name", "Сотрудник"), "count": 0}
        user_actions[uid]["count"] += 1

    for uid, data in user_actions.items():
        buttons.append([InlineKeyboardButton(
            text=f"👤 {data['name']} ({data['count']} действ.)", 
            callback_data=f"history_user_{uid}"
        )])

    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_users")])
    buttons.append([InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e): pass
    await callback.answer()

@router.callback_query(F.data.startswith("history_user_"))
async def cb_history_user(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
        
    uid = int(callback.data.replace("history_user_", ""))
    
    # Берем все логи этого пользователя
    user_logs = [l for l in log_service.logs if l.get("user_id") == uid]
    
    if not user_logs:
        await callback.answer("У этого пользователя нет истории.", show_alert=True)
        return
        
    user_name = user_logs[-1].get("user_name", "Сотрудник")
    text = f"👤 <b>История действий: {user_name}</b>\n\n"
    
    buttons = []
    for log in reversed(user_logs):
        text += f"• [{log['time']}] {log['action']}\n"
        if log.get("snapshot") is not None:
            label = "черновик" if "черновик" in log["action"] else "отправил" if "отправил" in log["action"] else "данные"
            buttons.append([InlineKeyboardButton(
                text=f"👁 Посмотреть {label} ({log['time']})", 
                callback_data=f"view_log_{log['id']}_{uid}"
            )])
            
    buttons.append([InlineKeyboardButton(text="⬅️ Назад к пользователям", callback_data="admin_users")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("view_log_"))
async def cb_view_log(callback: CallbackQuery, is_manager: bool):
    if not is_manager: 
        await callback.message.delete()
        await callback.answer()
        return
        
    parts = callback.data.split("_")
    log_id = int(parts[2])
    user_id_back = int(parts[3]) if len(parts) > 3 else None # ID пользователя для кнопки "Назад"

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
        if name == "undo_type": continue # скрываем служебную инфу
        if isinstance(val, dict) and "qty" in val:
            text += f"• {name}: всего <b>{val.get('qty')}</b>, витрина <b>{val.get('display_qty')}</b>\n"
        elif isinstance(val, dict):
            text += f"• {name}: <i>(сложные данные)</i>\n"
        else:
            text += f"• {name}: <b>{val}</b>\n"
            
    buttons = []
    if isinstance(log_entry.get("snapshot"), dict) and log_entry["snapshot"].get("undo_type"):
        buttons.append([InlineKeyboardButton(text="↩️ Отменить это действие", callback_data=f"undo_{log_id}")])
    
    back_cb = f"history_user_{user_id_back}" if user_id_back else "admin_users"
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_cb)])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("undo_"))
async def cb_undo_action(callback: CallbackQuery, is_manager: bool):
    if not is_manager:
        await callback.message.delete()
        await callback.answer()
        return

    log_id = int(callback.data.replace("undo_", ""))
    log_entry = next((l for l in log_service.logs if l["id"] == log_id), None)
    
    if not log_entry or not log_entry.get("snapshot") or not isinstance(log_entry["snapshot"], dict):
        await callback.answer("❌ Данные для отката не найдены.", show_alert=True)
        return

    snap = log_entry["snapshot"]
    undo_type = snap.get("undo_type")

    if not undo_type:
        await callback.answer("❌ Это действие нельзя отменить.", show_alert=True)
        return

    try:
        if undo_type == "delete":
            item_name = snap["name"]
            item_data = snap["data"]
            if item_name in inventory:
                await callback.answer("❌ Позиция с таким названием уже существует.", show_alert=True)
                return
            inventory[item_name] = item_data
            
        elif undo_type == "rename":
            old_name = snap["old_name"]
            new_name = snap["new_name"]
            if new_name not in inventory:
                await callback.answer("❌ Позиция уже удалена, откат невозможен.", show_alert=True)
                return
            if old_name in inventory:
                await callback.answer("❌ Позиция со старым названием уже существует.", show_alert=True)
                return
            inventory[old_name] = inventory.pop(new_name)
            
        elif undo_type == "add":
            item_name = snap["name"]
            if item_name in inventory:
                del inventory[item_name]
            else:
                await callback.answer("❌ Позиция уже удалена.", show_alert=True)
                return
        
        save_state()
        
        # Защищаем от повторного отката, удаляя метку undo_type из лога
        snap["undo_type"] = None
        log_service.repo.save_logs(log_service.logs)
        
        await callback.answer("✅ Действие успешно отменено!", show_alert=True)
        await cb_admin_users(callback, is_manager=is_manager) # Возвращаем в историю
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка при откате: {e}", show_alert=True)

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