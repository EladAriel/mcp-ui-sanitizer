import os
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.prompt import MERGE_PROMPT, SANITIZE_PROMPT
from app.schemas import CleanDesignArtifactInput, SanitizedArtifact


def uses_strict_json_schema(settings: Settings) -> bool:
    """OpenAI-compatible models support strict JSON schema structured output."""
    if settings.llm_provider == "openai":
        return True
    if settings.llm_provider == "openrouter":
        return settings.llm_model.startswith("openai/")
    return False


def build_chat_model(settings: Settings) -> BaseChatModel:
    if settings.llm_provider == "anthropic":
        return ChatAnthropic(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=0,
        )
    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=0,
        )
    if settings.llm_provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured.")
        return ChatOpenAI(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=0,
            api_key=api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": settings.openrouter_http_referer,
                "X-Title": settings.openrouter_app_title,
            },
        )
    raise RuntimeError("The fake provider is only available through dependency injection in tests.")


class LangChainSanitizer:
    def __init__(self, settings: Settings, model: BaseChatModel | None = None):
        self.settings = settings
        self.model = model

    async def sanitize(
        self,
        request: CleanDesignArtifactInput,
        *,
        callbacks: list[Any] | None = None,
        repair_instruction: str = "",
    ) -> str:
        model = self.model or build_chat_model(self.settings)
        if uses_strict_json_schema(self.settings):
            structured = model.with_structured_output(
                SanitizedArtifact,
                method="json_schema",
                strict=True,
            )
        else:
            structured = model.with_structured_output(SanitizedArtifact)

        chain = SANITIZE_PROMPT | structured
        active_repair = repair_instruction
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                parsed = await chain.ainvoke(
                    {
                        "raw_code": request.raw_code,
                        "target_component_name": request.target_component_name,
                        "allowed_features": "\n".join(
                            f"- {feature}" for feature in request.allowed_features
                        )
                        or "- None",
                        "repair_instruction": active_repair,
                    },
                    config={"callbacks": callbacks or []},
                )
                if isinstance(parsed, SanitizedArtifact):
                    return parsed.code
                return SanitizedArtifact.model_validate(parsed).code
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    active_repair = (
                        "The previous response did not match the required schema. "
                        "Return one valid structured response with source code only."
                    )
        assert last_error is not None
        raise last_error

    async def merge_into_component(
        self,
        *,
        production_jsx: str,
        sanitized_html: str,
        target_component_name: str,
        allowed_features: list[str],
        callbacks: list[Any] | None = None,
        repair_instruction: str = "",
    ) -> str:
        model = self.model or build_chat_model(self.settings)
        if uses_strict_json_schema(self.settings):
            structured = model.with_structured_output(
                SanitizedArtifact,
                method="json_schema",
                strict=True,
            )
        else:
            structured = model.with_structured_output(SanitizedArtifact)

        chain = MERGE_PROMPT | structured
        active_repair = repair_instruction
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                parsed = await chain.ainvoke(
                    {
                        "production_jsx": production_jsx,
                        "sanitized_html": sanitized_html,
                        "target_component_name": target_component_name,
                        "allowed_features": "\n".join(
                            f"- {feature}" for feature in allowed_features
                        )
                        or "- None",
                        "repair_instruction": active_repair,
                    },
                    config={"callbacks": callbacks or []},
                )
                if isinstance(parsed, SanitizedArtifact):
                    return parsed.code
                return SanitizedArtifact.model_validate(parsed).code
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    active_repair = (
                        "The previous response did not match the required schema. "
                        "Return one valid structured response with source code only."
                    )
        assert last_error is not None
        raise last_error
