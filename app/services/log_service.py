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
        if len(self.logs) > 100: self.logs.pop(0)
        self.repo.save_logs(self.logs)