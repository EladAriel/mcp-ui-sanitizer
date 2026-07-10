from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import uuid4

from app.ast_policy import PolicyError, inventory_artifact, validate_sanitized_artifact
from app.config import Settings, get_settings
from app.llm import LangChainSanitizer
from app.observability import sanitization_trace
from app.schemas import (
    CleanDesignArtifactInput,
    ErrorCode,
    ProgressStage,
    ValidationIssue,
)

ProgressReporter = Callable[[ProgressStage, str], Awaitable[None]]


class SanitizerEngine(Protocol):
    async def sanitize(
        self,
        request: CleanDesignArtifactInput,
        *,
        callbacks: list[Any] | None = None,
    ) -> str: ...


class SanitizationError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        issues: list[ValidationIssue] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.issues = issues or []


async def _no_progress(_stage: ProgressStage, _message: str) -> None:
    return None


class SanitizationService:
    def __init__(
        self,
        settings: Settings | None = None,
        engine: SanitizerEngine | None = None,
    ):
        self.settings = settings or get_settings()
        self.engine = engine or LangChainSanitizer(self.settings)

    async def clean(
        self,
        request: CleanDesignArtifactInput,
        *,
        source: str,
        request_id: str | None = None,
        progress: ProgressReporter | None = None,
    ) -> str:
        report = progress or _no_progress
        invocation_id = request_id or str(uuid4())
        if len(request.raw_code.encode()) > self.settings.max_code_bytes:
            raise SanitizationError(
                ErrorCode.INVALID_INPUT,
                f"raw_code exceeds the {self.settings.max_code_bytes}-byte limit.",
            )

        with sanitization_trace(
            self.settings,
            request_id=invocation_id,
            source=source,
            raw_code=request.raw_code,
            target_component_name=request.target_component_name,
            allowed_features=request.allowed_features,
        ) as trace:
            try:
                await report(ProgressStage.PARSING_AST, "Parsing source syntax tree…")
                inventory_artifact(request.raw_code)
                await report(
                    ProgressStage.STRIPPING_MOCK_LOGIC,
                    "Inventorying state, handlers, mock data, and unsupported features…",
                )
                await report(
                    ProgressStage.LLM_PROCESSING, "Generating stateless presentation code…"
                )
                sanitized_code = await self.engine.sanitize(request, callbacks=trace.callbacks)
                await report(
                    ProgressStage.VALIDATING_OUTPUT,
                    "Validating syntax and fail-closed component policy…",
                )
                validate_sanitized_artifact(
                    request.raw_code,
                    sanitized_code,
                    request.target_component_name,
                    request.allowed_features,
                )
                trace.finish(output=sanitized_code, validation_issues=[])
                return sanitized_code
            except PolicyError as exc:
                trace.finish(
                    output=None,
                    validation_issues=[issue.model_dump(mode="json") for issue in exc.issues],
                    error=str(exc),
                )
                raise SanitizationError(exc.code, str(exc), exc.issues) from exc
            except SanitizationError:
                raise
            except Exception as exc:
                message = "The model could not produce a valid sanitized artifact."
                trace.finish(output=None, validation_issues=[], error=message)
                raise SanitizationError(ErrorCode.MODEL_ERROR, message) from exc
