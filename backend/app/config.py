from functools import lru_cache
import json
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Provider and Langfuse credentials live in .env without the SANITIZER_ prefix and are
# read via os.getenv. pydantic-settings does not export those into the process env, so
# load the file explicitly before Settings / LLM / Langfuse code runs.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_process_env() -> None:
    try:
        load_dotenv(_ENV_FILE, override=False)
    except OSError:
        # Tests/sandboxes may not be able to read a local .env; callers can still
        # provide credentials via the real process environment.
        pass


load_process_env()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_prefix="SANITIZER_",
        extra="ignore",
    )

    app_name: str = "UI Design Sanitizer"
    environment: str = "development"
    llm_provider: Literal["openai", "anthropic", "openrouter", "fake"] = "openai"
    llm_model: str = "gpt-5.6-luna"
    llm_temperature: float = 0.0
    llm_max_tokens: int = Field(default=16_384, ge=256, le=131_072)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:5173"
    openrouter_app_title: str = "UI Design Sanitizer"
    max_code_bytes: int = Field(default=250_000, ge=1_024, le=2_000_000)
    max_concurrent_jobs: int = Field(default=4, ge=1, le=64)
    job_ttl_seconds: int = Field(default=3_600, ge=60, le=86_400)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    workspace_roots: Annotated[list[str], NoDecode] = Field(default_factory=list)
    langfuse_enabled: bool = True
    langfuse_capture_code: bool = False

    @field_validator("cors_origins", "workspace_roots", mode="before")
    @classmethod
    def split_list_settings(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    inner = stripped.strip("[] \t")
                    return [
                        item.strip().strip("'\"")
                        for item in inner.split(",")
                        if item.strip()
                    ]
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("workspace_roots")
    @classmethod
    def normalize_workspace_roots(cls, value: list[str]) -> list[str]:
        return [str(Path(root).expanduser().resolve()) for root in value]


@lru_cache
def get_settings() -> Settings:
    load_process_env()
    return Settings()
