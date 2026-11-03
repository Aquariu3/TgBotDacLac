import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from iikocloudapi import AppAuth, IikoCloud
from app.config import settings


class IikoAsyncService:
    """Асинхронный сервис для чтения данных из iikoCloud (только чтение)."""

    def __init__(self):
        self.auth = AppAuth(
            api_key=settings.IIKO_API_KEY,
            app_id=settings.IIKO_APP_ID,
            client_secret=settings.IIKO_CLIENT_SECRET,
        )
        # Кэш для номенклатуры, чтобы не дёргать API каждый раз
        self._products_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._products_cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=settings.PRODUCTS_CACHE_TTL)

    def _get_client(self) -> IikoCloud:
        # Клиент создается без await
        return IikoCloud(auth=self.auth)

    async def get_nomenclature(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает словарь: {product_id: {"name": str, "unit": str, "type": str}}"""
        now = datetime.now()
        if self._products_cache and self._products_cache_time and (now - self._products_cache_time) < self._cache_ttl:
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

                    if p_id:
                        result[p_id] = {"name": p_name, "unit": unit, "type": p_type}

                if len(products) < limit:
                    break
                offset += limit

        self._products_cache = result
        self._products_cache_time = now
        return result

    async def get_tech_cards(self) -> Dict[str, Dict[str, float]]:
        """Возвращает словарь: {dish_id: {ingredient_id: quantity}}"""
        result = {}
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        async with self._get_client() as iiko:
            response = await iiko.nomenclature.assembly_chart.list(
                date_from=today, 
                date_to=tomorrow, 
                include_prepared_charts=True
            )

            for chart in getattr(response, "items", []):
                chart_dict = chart.model_dump() if hasattr(chart, 'model_dump') else chart
                dish_id = chart_dict.get('productId')
                if not dish_id:
                    continue
                
                dish_ings = {}
                for ing in chart_dict.get('items', []):
                    ing_id = ing.get('productId')
                    ing_amount = float(ing.get('quantityIn') or ing.get('amount') or 0)
                    if ing_id and ing_amount > 0:
                        dish_ings[ing_id] = dish_ings.get(ing_id, 0) + ing_amount
                
                if dish_ings:
                    result[dish_id] = dish_ings

        return result

    async def get_documents(self, doc_type: str, date_from: str, date_to: str) -> List[Any]:
        """Универсальный метод для получения списка документов инвентаризации."""
        result = []
        async with self._get_client() as iiko:
            kwargs = {
                "organization_id": settings.IIKO_ORG_ID,
                "from_": date_from, # В библиотеке может быть from_ или date_from
                "to": date_to,
                "return_full_details": True
            }
            
            try:
                if doc_type == "incoming":
                    response = await iiko.inventory.incoming_invoice.list(**kwargs)
                elif doc_type == "outgoing":
                    response = await iiko.inventory.outgoing_invoice.list(**kwargs)
                elif doc_type == "writeoff":
                    response = await iiko.inventory.writeoff_document.list(**kwargs)
                elif doc_type == "transfer":
                    response = await iiko.inventory.internal_transfer.list(**kwargs)
                elif doc_type == "sales":
                    response = await iiko.inventory.sales_document.list(**kwargs)
                else:
                    logging.warning(f"Тип документа '{doc_type}' не поддерживается.")
                    return []
            except TypeError:
                # Если библиотека ожидает другие имена аргументов (например, date_from вместо from_)
                kwargs = {"organization_id": settings.IIKO_ORG_ID, "date_from": date_from, "date_to": date_to, "return_full_details": True}
                if doc_type == "incoming": response = await iiko.inventory.incoming_invoice.list(**kwargs)
                elif doc_type == "outgoing": response = await iiko.inventory.outgoing_invoice.list(**kwargs)
                elif doc_type == "writeoff": response = await iiko.inventory.writeoff_document.list(**kwargs)
                elif doc_type == "transfer": response = await iiko.inventory.internal_transfer.list(**kwargs)
                elif doc_type == "sales": response = await iiko.inventory.sales_document.list(**kwargs)

            items = getattr(response, "items", []) or getattr(response, "documents", [])
            for item in items:
                result.append(item.model_dump() if hasattr(item, 'model_dump') else item)
                
        return result

    async def get_stock_balance(self) -> List[Dict[str, Any]]:
        """Возвращает список остатков: [{"name": str, "qty": float, "unit": str}, ...]"""
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        result = []

        async with self._get_client() as iiko:
            response = await iiko.inventory.stock_balance.list(
                balance_at=now_str,
                organization_id=settings.IIKO_ORG_ID,
                store_ids=[settings.IIKO_STORE_ID],
                limit=1000
            )

            products = await self.get_nomenclature()

            for item in getattr(response, "items", []):
                item_dict = item.model_dump() if hasattr(item, 'model_dump') else item
                item_id = item_dict.get('productId')
                qty = float(item_dict.get('quantity', 0))
                
                if item_id in products and qty != 0:
                    p = products[item_id]
                    result.append({"name": p["name"], "qty": qty, "unit": p["unit"]})

        return result