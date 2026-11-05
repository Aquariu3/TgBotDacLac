import json
import logging
import os
import tempfile
import threading

# Реестр блокировок по пути файла — чтобы параллельные записи в ОДИН файл шли по очереди.
# Разные файлы (inventory.json, users.json и т.д.) друг друга не блокируют.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _get_file_lock(file_path: str) -> threading.Lock:
    with _locks_guard:
        if file_path not in _locks:
            _locks[file_path] = threading.Lock()
        return _locks[file_path]


class JsonRepository:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._lock = _get_file_lock(file_path)

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
        with self._lock:
            directory = os.path.dirname(self.file_path) or "."
            tmp_path = None
            try:
                # 1. Пишем во временный файл рядом с целевым (в той же папке!)
                fd, tmp_path = tempfile.mkstemp(
                    dir=directory, prefix=".tmp_", suffix=".json", text=True
                )
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                    f.flush()
                    try:
                        os.fsync(f.fileno())  # гарантируем, что данные на диске
                    except OSError as fsync_err:
                        logging.warning(f"fsync не удался для {self.file_path}: {fsync_err}")

                # 2. mkstemp создаёт файл с правами 0600 — приводим к обычным 0644
                try:
                    os.chmod(tmp_path, 0o644)
                except OSError:
                    pass

                # 3. Атомарная замена — файл либо старый, либо новый.
                os.replace(tmp_path, self.file_path)
                tmp_path = None  # успех — временный файл больше не наш
            except Exception as e:
                logging.error(f"Ошибка сохранения {self.file_path}: {e}")
            finally:
                # Если что-то упало — не оставляем мусорных файлов
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass