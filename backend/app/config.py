import json
import os
from pathlib import Path
from typing import Any, List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"


class Settings(BaseSettings):
    PROJECT_NAME: str = "VyaparMitra"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/vyaparmitra.db"
    DEBUG: bool = True
    CORS_ORIGINS: List[str] = ["*"]
    ALLOWED_ORIGINS: Optional[str] = None
    DATA_DIRECTORY: Path = DATA_DIR
    GEMINI_API_KEY: Optional[str] = None
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB cap
    MAX_UPLOAD_ROWS: int = 50_000

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["*"]

    def get_cors_origins(self) -> List[str]:
        if self.ALLOWED_ORIGINS:
            return [i.strip() for i in self.ALLOWED_ORIGINS.split(",") if i.strip()]
        return self.CORS_ORIGINS

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",
    )


settings = Settings()
