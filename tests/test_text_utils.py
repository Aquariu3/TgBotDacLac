import pytest

from app.text_utils import clean_item_name


@pytest.mark.parametrize("input_name, expected", [
    ("Молоко 3.2% (л)",              "Молоко 3.2%"),
    ("Кофе в зернах (кг)",           "Кофе в зернах"),
    ("Стакан 350 (шт)",              "Стакан 350"),
    ("Сироп (л/шт)",                 "Сироп"),
    ("Крышка (мл)",                  "Крышка"),
    ("Сахар (гр)",                   "Сахар"),
    ("Мука (уп)",                    "Мука"),
    ("Чай (пач)",                    "Чай"),
    ("Без скобок",                   "Без скобок"),
    ("Позиция  (шт)  ",              "Позиция"),
    ("Название (шт) с продолжением", "Название (шт) с продолжением"),
    ("(шт)",                         ""),
])
def test_clean_item_name(input_name, expected):
    assert clean_item_name(input_name) == expected