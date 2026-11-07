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
        self._active_employees_cache: list[dict] = []
        self._active_employees_cache_time: Optional[datetime] = None
        # Долгосрочный кэш id -> имя сотрудника. Имена меняются редко,
        # кэш сбрасывается только через clear_cache().
        self._employee_names_cache: dict[str, str] = {}

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
                    p_group_id = p_dict.get('parentGroupId')

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

        iiko_names = {}
        for pid, p in products.items():
            clean_name = p["name"].lower().strip()
            iiko_names[clean_name] = p["unit"]

        updated_count = 0
        for item_name, data in inventory_dict.items():
            clean_local_name = item_name.split('(')[0].strip().lower()

            found_unit = None
            if clean_local_name in iiko_names:
                found_unit = iiko_names[clean_local_name]
            else:
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
                logging.info(f"Структура меню из iiko: {menu.model_dump() if hasattr(menu, 'model_dump') else menu}")

                product_ids = set()
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
        """Очищает кэш номенклатуры и смены, чтобы принудительно запросить свежие данные."""
        self._products_cache = None
        self._products_cache_time = None
        self._active_employees_cache = []
        self._active_employees_cache_time = None
        # Кэш имён сотрудников НЕ сбрасываем — имена редко меняются.

    async def get_active_employees(self) -> list[dict]:
        """Возвращает список сотрудников, открывших смену сегодня (кэш на settings.IIKO_CACHE_TTL).

        Логика:
        1. Один запрос `attendance.list` за сегодня с endAt=null (открытые смены).
        2. Дедупликация по employeeId: если у сотрудника несколько смен за день — берём самую раннюю.
        3. Имена сотрудников резолвятся через `_employee_names_cache` (id -> name).
           Первый раз имя запрашивается, дальше — из кэша. Это убивает N+1 при повторных показах меню.
        4. При ошибке iiko — raise (UI покажет «информация временно недоступна»).
           Если есть старый успешный кэш — отдаём его.
        """
        now = datetime.now()
        ttl = settings.IIKO_CACHE_TTL

        if (self._active_employees_cache_time
                and (now - self._active_employees_cache_time).total_seconds() < ttl):
            return self._active_employees_cache

        try:
            async with self._get_client() as iiko:
                today = now.strftime("%Y-%m-%d")

                response = await iiko.employees.attendance.list(
                    organization_id=settings.IIKO_ORG_ID,
                    start_at=f"{today}T00:00:00",
                    end_at=None,
                    is_closed=False,
                    limit=50,
                )

                items = getattr(response, "items", []) or []

                # Дедупликация: employeeId -> самая ранняя startAt
                shifts_by_emp: dict[str, str] = {}
                for item in items:
                    item_dict = item.model_dump() if hasattr(item, "model_dump") else item
                    emp_id = item_dict.get("employeeId")
                    start_at = item_dict.get("startAt")
                    if not emp_id or not start_at:
                        continue
                    if emp_id not in shifts_by_emp or start_at < shifts_by_emp[emp_id]:
                        shifts_by_emp[emp_id] = start_at

                if not shifts_by_emp:
                    self._active_employees_cache = []
                    self._active_employees_cache_time = now
                    return []

                active = []
                for emp_id, start_at in shifts_by_emp.items():
                    emp_name = self._employee_names_cache.get(emp_id)
                    if emp_name is None:
                        try:
                            emp_info = await iiko.employees.info(employee_id=emp_id)
                            emp_dict = emp_info.model_dump() if hasattr(emp_info, "model_dump") else emp_info
                            emp_name = emp_dict.get("name") or emp_dict.get("displayName") or "Сотрудник"
                        except Exception as e:
                            logging.warning(f"Не удалось получить имя сотрудника {emp_id}: {e}")
                            emp_name = "Сотрудник"
                        self._employee_names_cache[emp_id] = emp_name

                    time_str = ""
                    try:
                        dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                        time_str = dt.strftime("%H:%M")
                    except Exception:
                        time_str = start_at[11:16] if len(start_at) > 16 else start_at

                    active.append({"name": emp_name, "time": time_str})

                active.sort(key=lambda x: x.get("time", ""))

                self._active_employees_cache = active
                self._active_employees_cache_time = now
                return active

        except Exception as e:
            logging.error(f"Ошибка получения списка сотрудников на смене: {e}")
            if self._active_employees_cache:
                return self._active_employees_cache
            raise