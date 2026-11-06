import asyncio
import logging
from datetime import datetime

class LogService:
    def __init__(self, logs_repo):
        self.repo = logs_repo
        self.logs = []
        self.log_id_counter = 1
        self.load()

    def load(self):
        self.logs = self.repo.load_logs()
        if self.logs:
            self.log_id_counter = max([l.get("id", 0) for l in self.logs]) + 1

    def add_log(self, user_id, user_name, action, snapshot=None):
        now = datetime.now().strftime("%d.%m в %H:%M")
        log_entry = {"id": self.log_id_counter, "time": now, "user_id": user_id, "user_name": user_name, "action": action, "snapshot": snapshot}
        self.log_id_counter += 1
        self.logs.append(log_entry)
        
        # ФИКС #43: храним 300 логов вместо 100
        if len(self.logs) > 300: 
            self.logs.pop(0)
        
        logs_to_save = list(self.logs)
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(asyncio.to_thread(self.repo.save_logs, logs_to_save))
        except RuntimeError:
            self.repo.save_logs(logs_to_save)