from aiogram.fsm.state import State, StatesGroup

class InventoryStates(StatesGroup):
    waiting_for_reg_name = State()
    wizard_qty = State()
    wizard_display_qty = State()
    waiting_for_new_qty = State()
    waiting_for_new_qty_display = State()
    waiting_for_broadcast_text = State()

class AdminEditStates(StatesGroup):
    waiting_for_new_item_name = State()
    waiting_for_new_item_qty = State()
    waiting_for_new_item_display = State()
    waiting_for_food_type = State()
    waiting_for_new_name = State()
    waiting_for_iiko_search = State()
    waiting_for_sales_period = State() # <-- НОВОЕ СОСТОЯНИЕ