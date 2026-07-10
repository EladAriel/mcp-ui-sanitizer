from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SANITIZER_",
        extra="ignore",
    )

    app_name: str = "UI Design Sanitizer"
    environment: str = "development"
    llm_provider: Literal["openai", "anthropic", "fake"] = "openai"
    llm_model: str = "gpt-5.6-luna"
    llm_temperature: float = 0.0
    llm_max_tokens: int = Field(default=16_384, ge=256, le=131_072)
    max_code_bytes: int = Field(default=250_000, ge=1_024, le=2_000_000)
    max_concurrent_jobs: int = Field(default=4, ge=1, le=64)
    job_ttl_seconds: int = Field(default=3_600, ge=60, le=86_400)
    cors_origins: list[str] = ["http://localhost:5173"]
    langfuse_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
