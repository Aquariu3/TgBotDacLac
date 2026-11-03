from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    BOT_TOKEN: str
    ADMIN_ID: int

    IIKO_API_KEY: str
    IIKO_APP_ID: str
    IIKO_CLIENT_SECRET: str
    IIKO_ORG_ID: str
    IIKO_STORE_ID: str

    IIKO_CACHE_TTL: int = 300
    PRODUCTS_CACHE_TTL: int = 3600

settings = Settings()