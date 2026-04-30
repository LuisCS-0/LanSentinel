from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ─── Base de datos ────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://lansentinel:lansentinel_pass@db:5432/lansentinel"

    # ─── Aplicación ───────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    SECRET_KEY: str = "changeme"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    LOG_LEVEL: str = "info"

    # ─── Red ──────────────────────────────────────────────────────────
    MONITOR_INTERFACE: str = "eth0"
    MONITOR_INTERVAL_SECONDS: int = 30

    # ─── Suricata ─────────────────────────────────────────────────────
    SURICATA_LOG_PATH: str = "/var/log/suricata/eve.json"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()
