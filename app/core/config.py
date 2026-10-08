from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed app config, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    postgres_user: str = "cinevault"
    postgres_password: str = "cinevault"
    postgres_db: str = "cinevault"
    postgres_host: str = "localhost"
    postgres_port: int = 5435

    tmdb_token: str = ""

    llm_provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:latest"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    data_dir: Path = ROOT_DIR / "data"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
