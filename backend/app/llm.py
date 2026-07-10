from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.config import Settings
from app.prompt import SANITIZE_PROMPT
from app.schemas import CleanDesignArtifactInput, SanitizedArtifact


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
    ) -> str:
        model = self.model or build_chat_model(self.settings)
        if self.settings.llm_provider == "openai":
            structured = model.with_structured_output(
                SanitizedArtifact,
                method="json_schema",
                strict=True,
            )
        else:
            structured = model.with_structured_output(SanitizedArtifact)

        chain = SANITIZE_PROMPT | structured
        repair_instruction = ""
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
                        "repair_instruction": repair_instruction,
                    },
                    config={"callbacks": callbacks or []},
                )
                if isinstance(parsed, SanitizedArtifact):
                    return parsed.code
                return SanitizedArtifact.model_validate(parsed).code
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    repair_instruction = (
                        "The previous response did not match the required schema. "
                        "Return one valid structured response with source code only."
                    )
        assert last_error is not None
        raise last_error
