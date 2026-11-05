import os
import json
import threading

from app.config import settings, DATA_DIR
from app.repositories.base import JsonRepository
from app.repositories.inventory_repo import InventoryRepository
from app.text_utils import clean_item_name
from app.repositories.users_repo import UsersRepository
from app.repositories.logs_repo import LogsRepository
from app.repositories.progress_repo import ProgressRepository
from app.services.iiko_service import IikoService
from app.services.iiko_async_service import IikoAsyncService
from app.services.log_service import LogService
from app.services.notification_service import NotificationService

ADMIN_ID = settings.ADMIN_ID
DATA_DIR = str(DATA_DIR)

TECH_CARDS_FILE = os.path.join(DATA_DIR, "iiko_tech_cards.json")
INVENTORY_FILE  = os.path.join(DATA_DIR, "inventory.json")
USERS_FILE      = os.path.join(DATA_DIR, "users.json")
LOGS_FILE       = os.path.join(DATA_DIR, "logs.json")
PROGRESS_FILE   = os.path.join(DATA_DIR, "progress.json")
ADMINS_FILE     = os.path.join(DATA_DIR, "admins.json")
MANAGERS_FILE   = os.path.join(DATA_DIR, "managers.json")

inventory_repo = InventoryRepository(INVENTORY_FILE)
users_repo = UsersRepository(USERS_FILE)
logs_repo = LogsRepository(LOGS_FILE)
progress_repo = ProgressRepository(PROGRESS_FILE)

# Репозитории для трёх «прямых» JSON-файлов — теперь тоже с атомарной записью
last_messages_repo = JsonRepository(os.path.join(DATA_DIR, "last_messages.json"))
admins_repo = JsonRepository(ADMINS_FILE)
managers_repo = JsonRepository(MANAGERS_FILE)

# Блокировка, чтобы save_state() целиком писал «снимок» всех файлов
_save_state_lock = threading.Lock()

iiko_service = IikoService(TECH_CARDS_FILE)
iiko_async_service = IikoAsyncService()
log_service = LogService(logs_repo)
notification_service = NotificationService()

# --- ГЛОБАЛЬНЫЕ ДАННЫЕ ---
inventory = {}
users_db = {}
user_progress = {}
last_menu_messages = {}
admin_ids = {ADMIN_ID}
manager_ids = set()

def save_state():
    """Сохраняет всё состояние в JSON-файлы атомарно.

    Блокировка нужна, чтобы два одновременных вызова не перемешали записи.
    Внутри каждого save() ещё есть своя per-file блокировка — это второй уровень защиты.
    """
    with _save_state_lock:
        inventory_repo.save_inventory(inventory)
        users_repo.save_users(users_db)
        progress_repo.save_progress(user_progress)
        last_messages_repo.save(last_menu_messages)
        admins_repo.save(list(admin_ids))
        managers_repo.save(list(manager_ids))

def load_state():
    global inventory, users_db, user_progress, last_menu_messages, admin_ids, manager_ids

    inv = inventory_repo.load_inventory()
    if inv:
        inventory.clear()
        
                # --- МАГИЯ ОЧИСТКИ НАЗВАНИЙ ---
        for k, v in inv.items():
            # Убираем (шт), (кг), (л/шт) и т.д. из конца названия
            clean_name = clean_item_name(k)
            
            # Если единицы измерения нет, ставим по умолчанию
            if "unit" not in v:
                if "(кг)" in k.lower() or "кг" in k.lower(): v["unit"] = "кг"
                elif "(л" in k.lower() or " л" in k.lower(): v["unit"] = "л"
                else: v["unit"] = "шт"
                
            inventory[clean_name] = v
        print(f"✅ Загружено {len(inventory)} позиций склада")
    else:
        inventory.update({
            "Кофе в зернах": {"qty": 4.0, "category": "coffee", "unit": "кг"},
            "Молоко 3.2%": {"qty": 20.0, "category": "milk", "unit": "л"},
            "Стакан 350": {"qty": 150.0, "category": "supplies", "subcategory": "cups", "unit": "шт"},
        })

    users = users_repo.load_users()
    if users:
        users_db = users
        print(f"✅ Загружено {len(users_db)} пользователей")

    prog = progress_repo.load_progress()
    if prog:
        user_progress = prog
        print(f"✅ Загружено {len(prog)} черновиков")

    msg_file = os.path.join(DATA_DIR, "last_messages.json")
    if os.path.exists(msg_file):
        try:
            with open(msg_file, "r", encoding="utf-8") as f:
                last_menu_messages = {int(k): v for k, v in json.load(f).items()}
        except Exception: pass
        
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, "r", encoding="utf-8") as f:
                admin_ids.update(json.load(f))
        except Exception: pass
        
    if os.path.exists(MANAGERS_FILE):
        try:
            with open(MANAGERS_FILE, "r", encoding="utf-8") as f:
                manager_ids.update(json.load(f))
        except Exception: pass

load_state()