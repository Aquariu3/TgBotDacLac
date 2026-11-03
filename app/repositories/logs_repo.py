from app.repositories.base import JsonRepository

class LogsRepository(JsonRepository):
    def __init__(self, file_path: str):
        super().__init__(file_path)

    def load_logs(self) -> list:
        return self.load(default=[])

    def save_logs(self, action_logs: list):
        self.save(action_logs)