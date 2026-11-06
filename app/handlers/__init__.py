from aiogram import Dispatcher
from app.handlers import (
    common, inventory, wizard, admin, admin_inventory, health,
    iiko_stock, iiko_sales, iiko_mapping, iiko_tech_cards
)

def setup_routers(dp: Dispatcher):
    dp.include_router(common.router)
    dp.include_router(inventory.router)
    dp.include_router(wizard.router)
    dp.include_router(admin.router)
    dp.include_router(admin_inventory.router)
    dp.include_router(iiko_stock.router)
    dp.include_router(iiko_sales.router)
    dp.include_router(iiko_mapping.router)
    dp.include_router(iiko_tech_cards.router)
    dp.include_router(health.router)