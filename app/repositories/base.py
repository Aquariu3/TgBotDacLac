import json
import logging
import os

class JsonRepository:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def _ensure_dir(self):
        # Создаем папку data, если ее нет (на всякий случай)
        directory = os.path.dirname(self.file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

    def load(self, default):
        if not os.path.exists(self.file_path):
            return default
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Ошибка загрузки {self.file_path}: {e}")
            return default

    def save(self, data):
        self._ensure_dir()
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logging.error(f"Ошибка сохранения {self.file_path}: {e}")