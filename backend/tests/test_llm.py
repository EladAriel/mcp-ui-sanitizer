import os
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.llm import build_chat_model, uses_strict_json_schema
from app.main import create_app
from app.service import SanitizationService


def test_openrouter_uses_strict_schema_for_openai_models() -> None:
    settings = Settings(
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        langfuse_enabled=False,
    )
    assert uses_strict_json_schema(settings) is True


def test_openrouter_uses_default_schema_for_non_openai_models() -> None:
    settings = Settings(
        llm_provider="openrouter",
        llm_model="anthropic/claude-haiku-4-5",
        langfuse_enabled=False,
    )
    assert uses_strict_json_schema(settings) is False


def test_build_chat_model_openrouter_requires_api_key() -> None:
    settings = Settings(
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        langfuse_enabled=False,
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENROUTER_API_KEY", None)
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            build_chat_model(settings)


def test_build_chat_model_openrouter_configures_openai_compatible_client() -> None:
    settings = Settings(
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_http_referer="http://localhost:5173",
        openrouter_app_title="UI Design Sanitizer",
        langfuse_enabled=False,
    )
    fake_model = MagicMock(name="ChatOpenAI")
    with (
        patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}),
        patch("app.llm.ChatOpenAI", return_value=fake_model) as chat_openai,
    ):
        model = build_chat_model(settings)

    assert model is fake_model
    chat_openai.assert_called_once()
    kwargs = chat_openai.call_args.kwargs
    assert kwargs["model"] == "openai/gpt-4o-mini"
    assert kwargs["api_key"] == "test-key"
    assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert kwargs["default_headers"]["HTTP-Referer"] == "http://localhost:5173"
    assert kwargs["default_headers"]["X-Title"] == "UI Design Sanitizer"


@pytest.mark.asyncio
async def test_ready_requires_openrouter_api_key() -> None:
    settings = Settings(
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        langfuse_enabled=False,
    )
    app = create_app(settings, SanitizationService(settings, engine=MagicMock()))

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENROUTER_API_KEY", None)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["provider"] == "openrouter"
    assert response.json()["reason"] == "OPENROUTER_API_KEY is not configured"


@pytest.mark.asyncio
async def test_ready_accepts_openrouter_when_key_present() -> None:
    settings = Settings(
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        langfuse_enabled=False,
    )
    app = create_app(settings, SanitizationService(settings, engine=MagicMock()))

    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["provider"] == "openrouter"
