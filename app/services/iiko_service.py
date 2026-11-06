import asyncio
import logging
import time
from datetime import datetime, timedelta
import requests
from iikocloudapi import AppAuth, IikoCloud
from app.domain.constants import SUPPLY_KEYWORDS, DESSERT_KEYWORDS, BAR_KEYWORDS, KITCHEN_KEYWORDS
from app.config import settings
from app.repositories.base import JsonRepository

class IikoService:
    def __init__(self, tech_cards_file: str):
        self.tech_cards_file = tech_cards_file
        self._tech_cards_repo = JsonRepository(tech_cards_file)
        self.cached_tech_card_ids = set()
        self.cached_tech_cards_map = {}
        self.iiko_stock_cache = []
        self.iiko_cache_time = None
        self.iiko_products_cache = {}
        self.iiko_products_cache_time = None
        self.groups_cache = {}
        self.IIKO_CACHE_TTL = 300
        self.PRODUCTS_CACHE_TTL = 3600
        self.load_tech_cards()

    def load_tech_cards(self):
        data = self._tech_cards_repo.load(default=None)
        if data is None:
            return

        if isinstance(data, dict):
            self.cached_tech_cards_map = data
            all_ing_ids = set()
            for dish_id, ings in self.cached_tech_cards_map.items():
                for ing_id in ings.keys():
                    all_ing_ids.add(ing_id)
            self.cached_tech_card_ids = all_ing_ids
        elif isinstance(data, list):
            self.cached_tech_card_ids = set(data)
            self.cached_tech_cards_map = {}

    def save_tech_cards(self):
        self._tech_cards_repo.save(self.cached_tech_cards_map)

    def classify_iiko_item(self, name: str) -> str:
        name_lower = name.lower()
        if any(k in name_lower for k in SUPPLY_KEYWORDS): return "supplies"
        if any(k in name_lower for k in DESSERT_KEYWORDS): return "desserts"
        if any(k in name_lower for k in BAR_KEYWORDS): return "bar"
        if any(k in name_lower for k in KITCHEN_KEYWORDS): return "kitchen"
        return "other"

    def sync_get_token(self):
        url = "https://api-ru.iiko.services/api/v2/access_token"
        payload = {
            "apiKey": settings.IIKO_API_KEY,
            "appId": settings.IIKO_APP_ID,
            "clientSecret": settings.IIKO_CLIENT_SECRET
        }

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 200:
                    try:
                        return resp.json().get("token")
                    except Exception as e:
                        logging.error(f"Ошибка парсинга JSON токена: {e}")
                        return None
                else:
                    logging.warning(f"iiko вернула статус {resp.status_code} при получении токена")
                    if resp.status_code in (400, 401, 403):
                        return None
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logging.warning(f"Попытка {attempt + 1}/3 получить токен iiko не удалась (сеть): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logging.error(f"Неизвестная ошибка при получении токена: {e}")
                return None

        logging.error("Не удалось получить токен iiko после 3 попыток. iiko недоступна.")
        return None

    def sync_get_products(self, token):
        if self.iiko_products_cache:
            return self.iiko_products_cache

        url = "https://api-ru.iiko.services/api/nomenclature/v2/product/list"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        product_map = {}
        offset = 0
        limit = 1000

        while True:
            payload = {"filters": [], "limit": limit, "offset": offset}
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code != 200:
                    logging.warning(f"⚠️ Ошибка загрузки номенклатуры: {resp.status_code} - {resp.text}")
                    break
                data = resp.json()
            except Exception as e:
                logging.error(f"Ошибка при запросе или парсинге номенклатуры: {e}")
                break

            items = data.get("items", [])
            if not items: break
            for p in items:
                pid = p.get("productId") or p.get("id")
                name = p.get("name", "Без названия")
                ptype = p.get("type", "UNKNOWN")
                group_id = p.get("parentGroupId")
                
                unit = "шт"
                if p.get("measureUnit"):
                    unit = p["measureUnit"].get("name", "шт") if isinstance(p["measureUnit"], dict) else str(p["measureUnit"])
                
                if pid: product_map[pid] = {"name": name, "type": ptype, "group_id": group_id, "unit": unit}
            if len(items) < limit: break
            offset += limit

        self.iiko_products_cache = product_map
        self.iiko_products_cache_time = datetime.now()
        return product_map

    def sync_get_groups(self, token):
        if self.groups_cache:
            return self.groups_cache

        url = "https://api-ru.iiko.services/api/nomenclature/v2/group/list"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        groups_map = {}
        offset = 0
        limit = 1000

        for attempt in range(3):
            try:
                payload = {"filters": [], "limit": limit, "offset": offset}
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code != 200:
                    logging.warning(f"⚠️ Ошибка загрузки групп: {resp.status_code}")
                    break
                data = resp.json()

                items = data.get("groups", [])
                if not items: break
                for g in items:
                    gid = g.get("groupId") or g.get("id")
                    gname = g.get("name")
                    if gid and gname:
                        groups_map[gid] = gname
                if len(items) < limit: break
                offset += limit
            except Exception as e:
                logging.error(f"Попытка {attempt+1} загрузки групп не удалась: {e}")
                if attempt == 2:
                    logging.warning("Возвращаем пустой список групп (iiko не ответила).")
                    return {}

        if groups_map:
            self.groups_cache = groups_map

        return groups_map

    def sync_get_documents(self, token, doc_type, from_date=None, to_date=None):
        if not from_date:
            from_date = datetime.now().strftime("%Y-%m-%d")
        if not to_date:
            try:
                to_date = (datetime.strptime(from_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            except ValueError as e:
                logging.error(f"Неверный формат from_date='{from_date}': {e}")
                return []

        url = f"https://api-ru.iiko.services/api/inventory/v1/{doc_type}/list"
        payload = {"organizationId": settings.IIKO_ORG_ID, "from": from_date, "to": to_date, "returnFullDetails": True}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                if resp.status_code != 200:
                    logging.warning(f"⚠️ Ошибка запроса {doc_type}: {resp.status_code} - {resp.text}")
                    if resp.status_code in (400, 401, 403, 404):
                        return []
                else:
                    return resp.json()
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logging.warning(f"Попытка {attempt + 1}/3 запроса {doc_type} не удалась (сеть): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logging.error(f"⚠️ Исключение при запросе {doc_type}: {e}")
                return []

        logging.error(f"Не удалось получить {doc_type} после 3 попыток.")
        return []

    def sync_get_all_tech_cards(self, token):
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        url = "https://api-ru.iiko.services/api/nomenclature/v2/assembly-chart/list"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"dateFrom": today, "dateTo": tomorrow, "includePreparedCharts": True}

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except Exception as e:
                        logging.error(f"Ошибка парсинга JSON техкарт: {e}")
                        return None
                elif resp.status_code == 429:
                    wait_time = 2 ** attempt
                    logging.warning(f"⚠️ Лимит запросов iiko (429). Ждём {wait_time} сек и пробуем снова...")
                    time.sleep(wait_time)
                    continue
                else:
                    logging.warning(f"⚠️ Ошибка массового запроса техкарт: {resp.status_code} - {resp.text}")
                    return None
            except Exception as e:
                logging.error(f"⚠️ Исключение при массовом запросе техкарт: {e}")
                return None

        logging.warning("⚠️ Не удалось получить техкарты после 3 попыток (429).")
        return None

    def sync_get_tech_card_by_id(self, token, product_id):
        url = "https://api-ru.iiko.services/api/nomenclature/v2/assembly-chart/list"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"productId": product_id, "includePreparedCharts": True}

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=15)
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except Exception as e:
                        logging.error(f"Ошибка парсинга JSON техкарты {product_id}: {e}")
                        return None
                elif resp.status_code == 429:
                    wait_time = 2 ** attempt
                    logging.warning(f"⚠️ Лимит (429) техкарты {product_id}. Ждём {wait_time} сек (попытка {attempt+1}/3).")
                    time.sleep(wait_time)
                    continue
                else:
                    return None
            except Exception as e:
                logging.error(f"Ошибка запроса техкарты {product_id}: {e}")
                return None

        logging.warning(f"⚠️ Не удалось получить техкарту {product_id} после 3 попыток (429).")
        return None

    async def scan_tech_cards_and_nomenclature(self):
        token = await asyncio.to_thread(self.sync_get_token)
        if not token:
            raise Exception("Не удалось получить токен iiko для сканирования техкарт.")

        product_map = await asyncio.to_thread(self.sync_get_products, token)
        resp_data = await asyncio.to_thread(self.sync_get_all_tech_cards, token)

        new_tech_card_ids = set()
        new_tech_cards_map = {}

        if resp_data and "items" in resp_data:
            for chart in resp_data.get('items', []):
                dish_id = chart.get('productId')
                if not dish_id: continue
                dish_ings = {}
                for ing in chart.get('items', []):
                    ing_id = ing.get('productId')
                    ing_amount = float(ing.get('quantityIn', 0) or ing.get('amount', 0))
                    if ing_id and ing_amount > 0:
                        new_tech_card_ids.add(ing_id)
                        dish_ings[ing_id] = dish_ings.get(ing_id, 0) + ing_amount
                if dish_ings:
                    new_tech_cards_map[dish_id] = dish_ings
        else:
            logging.warning("⚠️ Массовый запрос техкарт не дал результатов.")
            active_dishes = [pid for pid, p in product_map.items() if p["type"] in ['DISH', 'PREPARATION']]

            MAX_FALLBACK_ITEMS = 300
            if len(active_dishes) > MAX_FALLBACK_ITEMS:
                raise Exception(
                    f"Слишком много блюд для точечного сканирования ({len(active_dishes)} > {MAX_FALLBACK_ITEMS}). "
                    f"Массовый запрос техкарт не сработал. Проверьте iiko — возможно, она временно недоступна. "
                    f"Точечный перебор не запускается автоматически, чтобы не получить бан по лимитам."
                )

            logging.warning(f"⚠️ Точечный перебор {len(active_dishes)} блюд (лимит {MAX_FALLBACK_ITEMS}). Это может занять несколько минут.")
            for dish_id in active_dishes:
                resp = await asyncio.to_thread(self.sync_get_tech_card_by_id, token, dish_id)
                if not resp: continue
                dish_ings = {}
                for chart in resp.get('items', []):
                    for ing in chart.get('items', []):
                        ing_id = ing.get('productId')
                        ing_amount = float(ing.get('quantityIn', 0) or ing.get('amount', 0))
                        if ing_id and ing_amount > 0:
                            new_tech_card_ids.add(ing_id)
                            dish_ings[ing_id] = dish_ings.get(ing_id, 0) + ing_amount
                if dish_ings:
                    new_tech_cards_map[dish_id] = dish_ings
                await asyncio.sleep(0.5)

        self.cached_tech_card_ids = new_tech_card_ids
        self.cached_tech_cards_map = new_tech_cards_map
        self.save_tech_cards()

        if len(self.cached_tech_cards_map) == 0:
            raise Exception("Не найдено ни одной техкарты. Возможно, в iiko они не настроены.")
        return len(self.cached_tech_card_ids)

    async def safe_request(self, coro_func, *args, **kwargs):
        max_retries = 5
        for attempt in range(max_retries):
            try:
                return await coro_func(*args, **kwargs)
            except Exception as e:
                if "429" in str(e) or "TOO_MANY_REQUESTS" in str(e):
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    raise e
        raise Exception("Превышено количество попыток.")

    async def fetch_fast_stock(self):
        now = datetime.now()
        if self.iiko_cache_time and (now - self.iiko_cache_time).total_seconds() < self.IIKO_CACHE_TTL:
            return self.iiko_stock_cache

        auth = AppAuth(api_key=settings.IIKO_API_KEY, app_id=settings.IIKO_APP_ID, client_secret=settings.IIKO_CLIENT_SECRET)
        async with IikoCloud(auth=auth) as iiko:
            product_map = {}
            offset = 0
            while True:
                products_response = await self.safe_request(iiko.nomenclature.product.list, limit=1000, offset=offset)
                products = getattr(products_response, 'products', getattr(products_response, 'items', []))
                if not products: break
                for p in products:
                    p_dict = p.model_dump() if hasattr(p, 'model_dump') else p
                    p_id = p_dict.get('id') or p_dict.get('productId')
                    p_name = p_dict.get('name', 'Без названия')
                    unit_dict = p_dict.get('measureUnit') or {}
                    unit = unit_dict.get('name', 'шт') if isinstance(unit_dict, dict) else 'шт'
                    if p_id: product_map[p_id] = {"name": p_name, "unit": unit}
                if len(products) < 1000: break
                offset += 1000

            now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            balances = await self.safe_request(iiko.inventory.stock_balance.list, balance_at=now_str, organization_id=settings.IIKO_ORG_ID, store_ids=[settings.IIKO_STORE_ID], limit=1000)
            result = []
            for item in balances.items:
                item_dict = item.model_dump() if hasattr(item, 'model_dump') else item
                item_id = item_dict.get('productId') or item_dict.get('product_id')
                qty = float(item_dict.get('quantity', 0))
                if item_id in self.cached_tech_card_ids:
                    p_name = product_map.get(item_id, {}).get('name', '')
                    p_unit = product_map.get(item_id, {}).get('unit', 'шт')
                    if p_name: result.append({"name": p_name, "qty": qty, "unit": p_unit})
            self.iiko_stock_cache = result
            self.iiko_cache_time = now
            return result