from app.repositories.base import JsonRepository

class ProgressRepository(JsonRepository):
    def __init__(self, file_path: str):
        super().__init__(file_path)

    def load_progress(self) -> dict:
        prog = self.load(default={})
        return {int(k): v for k, v in prog.items()}

    def save_progress(self, user_progress: dict):
        self.save({str(k): v for k, v in user_progress.items()})