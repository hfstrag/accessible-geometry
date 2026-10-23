"""Application settings, read from environment variables and an optional `.env` file."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: SecretStr | None = None
    llm_model: str = "openai/gpt-oss-120b"
    stt_model: str = "whisper-large-v3-turbo"

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"

    request_timeout_s: float = Field(default=30.0, gt=0)
    max_audio_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

    @property
    def has_api_key(self) -> bool:
        return self.groq_api_key is not None and bool(self.groq_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
