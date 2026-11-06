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
