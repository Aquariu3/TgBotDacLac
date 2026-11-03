from app.repositories.base import JsonRepository

class UsersRepository(JsonRepository):
    def __init__(self, file_path: str):
        super().__init__(file_path)

    def load_users(self) -> dict:
        users = self.load(default={})
        # Ключи в JSON всегда строки, конвертируем обратно в int
        return {int(k): v for k, v in users.items()}

    def save_users(self, users_db: dict):
        # Перед сохранением конвертируем ключи в строки (требование JSON)
        self.save({str(k): v for k, v in users_db.items()})