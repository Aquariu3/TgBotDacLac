from aiogram import Dispatcher
from app.handlers import common, inventory, wizard, admin, admin_inventory, iiko

def setup_routers(dp: Dispatcher):
    dp.include_router(common.router)
    dp.include_router(inventory.router)
    dp.include_router(wizard.router)
    dp.include_router(admin.router)
    dp.include_router(admin_inventory.router) # <-- НОВЫЙ РОУТЕР
    dp.include_router(iiko.router)