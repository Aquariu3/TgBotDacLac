from app.repositories.base import JsonRepository

class InventoryRepository(JsonRepository):
    def __init__(self, file_path: str):
        super().__init__(file_path)

    def load_inventory(self) -> dict:
        return self.load(default={})

    def save_inventory(self, inventory: dict):
        self.save(inventory)