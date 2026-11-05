import hashlib
import re

UNIT_CLEANUP_PATTERN = re.compile(
    r'\s*\((шт|кг|л|л/шт|мл|гр|уп|пач)\)\s*$',
    re.IGNORECASE,
)

def clean_item_name(name: str) -> str:
    return UNIT_CLEANUP_PATTERN.sub('', name).strip()

def make_item_hash(name: str) -> str:
    return hashlib.sha256(name.encode('utf-8')).hexdigest()[:16]

def find_item_by_hash(inventory: dict, item_hash_or_name: str) -> str | None:
    """Находит название позиции по её хэшу.
    Поддерживает старый формат (когда присылали само название).
    """
    # 1. Проверяем, может это старое название (для старых кнопок)
    if item_hash_or_name in inventory:
        return item_hash_or_name
        
    # 2. Ищем по хэшу
    for name in inventory:
        if make_item_hash(name) == item_hash_or_name:
            return name
    return None