from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/voxflow"
    USE_SQLITE_FALLBACK: bool = True
    SQLITE_URL: str = "sqlite+aiosqlite:///./voxflow.db"

    GNANI_API_KEY: str = ""
    GNANI_ACCESS_TOKEN: str = ""
    GNANI_STT_URL: str = "https://api.vachana.ai/stt/v3"
    GNANI_TTS_URL: str = "https://tts.gnani.ai/v2.5/synthesize"

    GNANI_EVON_API_KEY: str = ""
    GNANI_EVON_URL: str = "https://evon.gnani.ai/v3.3/extract"

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

