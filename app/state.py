import os
import json
import re
from app.config import settings, DATA_DIR
from app.repositories.inventory_repo import InventoryRepository
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
    inventory_repo.save_inventory(inventory)
    users_repo.save_users(users_db)
    progress_repo.save_progress(user_progress)
    
    with open(os.path.join(DATA_DIR, "last_messages.json"), "w", encoding="utf-8") as f:
        json.dump(last_menu_messages, f)
        
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(admin_ids), f)
        
    with open(MANAGERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(manager_ids), f)

def load_state():
    global inventory, users_db, user_progress, last_menu_messages, admin_ids, manager_ids

    inv = inventory_repo.load_inventory()
    if inv:
        inventory.clear()
        
        # --- МАГИЯ ОЧИСТКИ НАЗВАНИЙ ---
        for k, v in inv.items():
            # Убираем (шт), (кг), (л/шт) и т.д. из конца названия
            clean_name = re.sub(r'\s*\((шт|кг|л|л/шт|мл|гр)\)$', '', k, flags=re.IGNORECASE).strip()
            
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