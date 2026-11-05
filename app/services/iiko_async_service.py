import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from iikocloudapi import AppAuth, IikoCloud
from app.config import settings

class IikoAsyncService:
    def __init__(self):
        self.auth = AppAuth(
            api_key=settings.IIKO_API_KEY,
            app_id=settings.IIKO_APP_ID,
            client_secret=settings.IIKO_CLIENT_SECRET,
        )
        self._products_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._products_cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=settings.PRODUCTS_CACHE_TTL)

    def _get_client(self) -> IikoCloud:
        return IikoCloud(auth=self.auth)

    async def get_nomenclature(self) -> Dict[str, Dict[str, Any]]:
        now = datetime.now()
        if self._products_cache:
            return self._products_cache

        result = {}
        offset = 0
        limit = 1000

        async with self._get_client() as iiko:
            while True:
                response = await iiko.nomenclature.product.list(limit=limit, offset=offset)
                products = getattr(response, "items", []) or getattr(response, "products", [])

                if not products:
                    break

                for p in products:
                    p_dict = p.model_dump() if hasattr(p, 'model_dump') else p
                    p_id = p_dict.get('id') or p_dict.get('productId')
                    p_name = p_dict.get('name', 'Без названия')
                    
                    unit = "шт"
                    if p_dict.get('measureUnit'):
                        unit = p_dict['measureUnit'].get('name', 'шт') if isinstance(p_dict['measureUnit'], dict) else str(p_dict['measureUnit'])
                    
                    p_type = p_dict.get('type', 'UNKNOWN')
                    is_deleted = p_dict.get('isDeleted', False)
                    p_group_id = p_dict.get('parentGroupId') # <-- Берем ID папки (группы)

                    if p_id:
                        result[p_id] = {"name": p_name, "unit": unit, "type": p_type, "isDeleted": is_deleted, "group_id": p_group_id}

                if len(products) < limit:
                    break
                offset += limit

        self._products_cache = result
        self._products_cache_time = now
        return result

    async def get_stock_balance(self) -> List[Dict[str, Any]]:
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        result = []

        async with self._get_client() as iiko:
            products = await self.get_nomenclature()

            offset = 0
            limit = 1000
            while True:
                response = await iiko.inventory.stock_balance.list(
                    balance_at=now_str,
                    organization_id=settings.IIKO_ORG_ID,
                    store_ids=[settings.IIKO_STORE_ID],
                    limit=limit,
                    offset=offset,
                )

                items = getattr(response, "items", []) or []
                if not items:
                    break

                for item in items:
                    item_dict = item.model_dump() if hasattr(item, 'model_dump') else item
                    item_id = item_dict.get('productId')
                    qty = float(item_dict.get('quantity', 0))

                    if item_id in products and qty != 0:
                        p = products[item_id]
                        result.append({"name": p["name"], "qty": qty, "unit": p["unit"]})

                if len(items) < limit:
                    break
                offset += limit

        return result

    async def sync_inventory_units(self, inventory_dict: dict) -> int:
        """Синхронизирует единицы измерения из iiko с локальной базой."""
        products = await self.get_nomenclature()
        
        # Создаем словарь для поиска: очищенное название -> единица измерения
        iiko_names = {}
        for pid, p in products.items():
            clean_name = p["name"].lower().strip()
            iiko_names[clean_name] = p["unit"]
        
        updated_count = 0
        for item_name, data in inventory_dict.items():
            # Очищаем локальное название от скобок для поиска
            clean_local_name = item_name.split('(')[0].strip().lower()
            
            found_unit = None
            # 1. Пытаемся найти точное совпадение
            if clean_local_name in iiko_names:
                found_unit = iiko_names[clean_local_name]
            else:
                # 2. Ищем частичное совпадение (например, "молоко 3.2" в "молоко 3.2% пастеризованное")
                for iiko_name, unit in iiko_names.items():
                    if clean_local_name in iiko_name:
                        found_unit = unit
                        break
            
            if found_unit:
                data["unit"] = found_unit
                updated_count += 1
                
        return updated_count
    async def get_menu_product_ids(self) -> set[str]:
        """Возвращает set ID продуктов, которые входят в меню точки."""
        async with self._get_client() as iiko:
            try:
                menu = await iiko.menu(organization_ids=[settings.IIKO_ORG_ID])
                # Выводим структуру ответа в консоль для отладки
                logging.info(f"Структура меню из iiko: {menu.model_dump() if hasattr(menu, 'model_dump') else menu}")
                
                product_ids = set()
                # Пытаемся найти продукты в разных возможных местах структуры
                if hasattr(menu, 'menus'):
                    for m in menu.menus:
                        for product in m.products:
                            product_ids.add(product.id)
                elif hasattr(menu, 'products'):
                    for product in menu.products:
                        product_ids.add(product.id)
                return product_ids
            except Exception as e:
                logging.error(f"Ошибка при получении меню точки: {e}")
                return set()
    def clear_cache(self):
        """Очищает кэш номенклатуры, чтобы принудительно запросить свежие данные."""
        self._products_cache = None
        self._products_cache_time = None