import os
import json
import threading
import asyncio

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
IIKO_MAPPINGS_FILE = os.path.join(DATA_DIR, "iiko_mappings.json") # НОВОЕ

inventory_repo = InventoryRepository(INVENTORY_FILE)
users_repo = UsersRepository(USERS_FILE)
logs_repo = LogsRepository(LOGS_FILE)
progress_repo = ProgressRepository(PROGRESS_FILE)

last_messages_repo = JsonRepository(os.path.join(DATA_DIR, "last_messages.json"))
admins_repo = JsonRepository(ADMINS_FILE)
managers_repo = JsonRepository(MANAGERS_FILE)
iiko_mappings_repo = JsonRepository(IIKO_MAPPINGS_FILE) # НОВОЕ

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
iiko_mappings = {} # НОВОЕ

def _save_state_sync():
    """Синхронная запись на диск (выполняется в фоновом потоке)."""
    with _save_state_lock:
        inventory_repo.save_inventory(inventory)
        users_repo.save_users(users_db)
        progress_repo.save_progress(user_progress)
        last_messages_repo.save(last_menu_messages)
        admins_repo.save(list(admin_ids))
        managers_repo.save(list(manager_ids))
        iiko_mappings_repo.save(iiko_mappings) # НОВОЕ

def save_state():
    """Неблокирующее сохранение в фоновом потоке."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(_save_state_sync))
    except RuntimeError:
        _save_state_sync()

def load_state():
    global inventory, users_db, user_progress, last_menu_messages, admin_ids, manager_ids, iiko_mappings

    # 1. Загрузка склада
    inv = inventory_repo.load_inventory()
    if inv:
        inventory.clear()
        for k, v in inv.items():
            clean_name = clean_item_name(k)
            
            if "unit" not in v:
                name_lower = k.lower()
                if "кг" in name_lower: v["unit"] = "кг"
                elif "мл" in name_lower: v["unit"] = "мл"
                elif "гр" in name_lower or " г" in name_lower: v["unit"] = "гр"
                elif "уп" in name_lower: v["unit"] = "уп"
                elif "л" in name_lower: v["unit"] = "л"
                else: v["unit"] = "шт"
                
            inventory[clean_name] = v
        print(f"✅ Загружено {len(inventory)} позиций склада")
    else:
        inventory.update({
            "Кофе в зернах": {"qty": 4.0, "category": "coffee", "unit": "кг"},
            "Молоко 3.2%": {"qty": 20.0, "category": "milk", "unit": "л"},
            "Стакан 350": {"qty": 150.0, "category": "supplies", "subcategory": "cups", "unit": "шт"},
        })

    # 2. Загрузка пользователей (через clear/update, чтобы не ломать импорты)
    users = users_repo.load_users()
    if users:
        users_db.clear()
        users_db.update(users)
        print(f"✅ Загружено {len(users_db)} пользователей")

    # 3. Загрузка черновиков
    prog = progress_repo.load_progress()
    if prog:
        user_progress.clear()
        user_progress.update(prog)
        print(f"✅ Загружено {len(prog)} черновиков")

    # 4. Загрузка сообщений меню
    msg_file = os.path.join(DATA_DIR, "last_messages.json")
    if os.path.exists(msg_file):
        try:
            with open(msg_file, "r", encoding="utf-8") as f:
                last_menu_messages.clear()
                last_menu_messages.update({int(k): v for k, v in json.load(f).items()})
        except Exception: pass
        
    # 5. Загрузка ролей
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, "r", encoding="utf-8") as f:
                for a_id in json.load(f):
                    try: admin_ids.add(int(a_id))
                    except (ValueError, TypeError): pass
        except Exception: pass
        
    if os.path.exists(MANAGERS_FILE):
        try:
            with open(MANAGERS_FILE, "r", encoding="utf-8") as f:
                for m_id in json.load(f):
                    try: manager_ids.add(int(m_id))
                    except (ValueError, TypeError): pass
        except Exception: pass

    # 6. Загрузка связей с iiko (НОВОЕ)
    maps = iiko_mappings_repo.load(default={})
    if maps:
        iiko_mappings.clear()
        iiko_mappings.update(maps)
        print(f"✅ Загружено {len(maps)} связей с iiko")