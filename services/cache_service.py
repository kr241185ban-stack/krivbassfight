import time
from typing import Dict, Any, List
from services.sheets_client import sheets_service

class DataCache:
    def __init__(self, ttl_seconds: int = 300): # Кэш на 5 минут
        self.ttl = ttl_seconds
        self._cache: Dict[str, Any] = {}
        self._last_update: Dict[str, float] = {}

    def get_sheet_data(self, sheet_name: str) -> List[Dict[str, Any]]:
        now = time.time()
        if sheet_name not in self._cache or (now - self._last_update.get(sheet_name, 0)) > self.ttl:
            # Обновляем кэш из Google Sheets
            sheet = sheets_service.spreadsheet.worksheet(sheet_name)
            self._cache[sheet_name] = sheet.get_all_records()
            self._last_update[sheet_name] = now
        return self._cache[sheet_name]

    def invalidate(self, sheet_name: str):
        """Сброс кэша при записи новых данных"""
        if sheet_name in self._cache:
            del self._cache[sheet_name]

cache_service = DataCache()