from pathlib import Path
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
    CORS_ORIGINS: list[str] = ["*"]
    DATA_DIRECTORY: Path = DATA_DIR
    GEMINI_API_KEY: str | None = None

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=str(BASE_DIR / ".env"),
        extra="ignore",
    )


settings = Settings()
