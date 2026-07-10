from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import uuid4

from app.ast_policy import (
    PolicyError,
    demote_form_wrappers,
    inventory_artifact,
    validate_merged_jsx,
    validate_sanitized_artifact,
)
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
        repair_instruction: str = "",
    ) -> str: ...

    async def merge_into_component(
        self,
        *,
        production_jsx: str,
        sanitized_html: str,
        target_component_name: str,
        allowed_features: list[str],
        callbacks: list[Any] | None = None,
        repair_instruction: str = "",
    ) -> str: ...


def _policy_repair_instruction(issues: list[ValidationIssue]) -> str:
    details = "\n".join(f"- {issue.code}: {issue.message}" for issue in issues[:12])
    return (
        "The previous sanitized output failed the fail-closed policy:\n"
        f"{details}\n"
        "Fix only those violations. Do not paraphrase or shorten retained text — keep exact "
        "artifact copy, or remove the whole element/text node. Return one valid structured "
        "response with source code only."
    )


def _merge_repair_instruction(issues: list[ValidationIssue]) -> str:
    details = "\n".join(f"- {issue.code}: {issue.message}" for issue in issues[:12])
    return (
        "The previous merged JSX failed the fail-closed policy:\n"
        f"{details}\n"
        "Fix only those violations. Keep the production component name and props. Keep "
        "non-interactive presentation from the sanitized HTML: full class lists "
        "(including panel), subtitle copy, and line-item as a <div className=\"line-item\"> "
        "wrapping name/meta and price — never use <p> for line-item (invalid with nested "
        "divs; breaks CSS grid). Replace any <form> with <div> keeping the same className. "
        "Return one valid structured response with source code only."
    )


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
                sanitized_code = demote_form_wrappers(sanitized_code)
                await report(
                    ProgressStage.VALIDATING_OUTPUT,
                    "Validating syntax and fail-closed component policy…",
                )
                last_policy_error: PolicyError | None = None
                for policy_attempt in range(2):
                    try:
                        validate_sanitized_artifact(
                            request.raw_code,
                            sanitized_code,
                            request.target_component_name,
                            request.allowed_features,
                        )
                    except PolicyError as exc:
                        last_policy_error = exc
                        if policy_attempt == 0:
                            sanitized_code = demote_form_wrappers(
                                await self.engine.sanitize(
                                    request,
                                    callbacks=trace.callbacks,
                                    repair_instruction=_policy_repair_instruction(exc.issues),
                                )
                            )
                            continue
                        break
                    else:
                        trace.finish(output=sanitized_code, validation_issues=[])
                        return sanitized_code

                assert last_policy_error is not None
                trace.finish(
                    output=None,
                    validation_issues=[
                        issue.model_dump(mode="json") for issue in last_policy_error.issues
                    ],
                    error=str(last_policy_error),
                )
                raise SanitizationError(
                    last_policy_error.code,
                    str(last_policy_error),
                    last_policy_error.issues,
                ) from last_policy_error
            except SanitizationError:
                raise
            except Exception as exc:
                message = "The model could not produce a valid sanitized artifact."
                trace.finish(output=None, validation_issues=[], error=message)
                raise SanitizationError(ErrorCode.MODEL_ERROR, message) from exc

    async def merge_presentation(
        self,
        *,
        production_jsx: str,
        sanitized_html: str,
        target_component_name: str,
        allowed_features: list[str],
        source: str,
        request_id: str | None = None,
        progress: ProgressReporter | None = None,
    ) -> str:
        report = progress or _no_progress
        invocation_id = request_id or str(uuid4())
        if len(production_jsx.encode()) > self.settings.max_code_bytes:
            raise SanitizationError(
                ErrorCode.INVALID_INPUT,
                f"production JSX exceeds the {self.settings.max_code_bytes}-byte limit.",
            )
        if len(sanitized_html.encode()) > self.settings.max_code_bytes:
            raise SanitizationError(
                ErrorCode.INVALID_INPUT,
                f"sanitized HTML exceeds the {self.settings.max_code_bytes}-byte limit.",
            )

        with sanitization_trace(
            self.settings,
            request_id=f"{invocation_id}-merge",
            source=source,
            raw_code=production_jsx,
            target_component_name=target_component_name,
            allowed_features=allowed_features,
        ) as trace:
            try:
                await report(
                    ProgressStage.LLM_PROCESSING,
                    "Merging sanitized HTML presentation into production JSX…",
                )
                merged = await self.engine.merge_into_component(
                    production_jsx=production_jsx,
                    sanitized_html=sanitized_html,
                    target_component_name=target_component_name,
                    allowed_features=allowed_features,
                    callbacks=trace.callbacks,
                )
                merged = demote_form_wrappers(merged)
                await report(
                    ProgressStage.VALIDATING_OUTPUT,
                    "Validating merged JSX against production and design inventories…",
                )
                last_policy_error: PolicyError | None = None
                for policy_attempt in range(2):
                    try:
                        validate_merged_jsx(
                            production_jsx,
                            sanitized_html,
                            merged,
                            target_component_name,
                            allowed_features,
                        )
                    except PolicyError as exc:
                        last_policy_error = exc
                        if policy_attempt == 0:
                            # Prefer deterministic form demotion before asking the model to repair.
                            demoted = demote_form_wrappers(merged)
                            if demoted != merged:
                                merged = demoted
                                continue
                            merged = demote_form_wrappers(
                                await self.engine.merge_into_component(
                                    production_jsx=production_jsx,
                                    sanitized_html=sanitized_html,
                                    target_component_name=target_component_name,
                                    allowed_features=allowed_features,
                                    callbacks=trace.callbacks,
                                    repair_instruction=_merge_repair_instruction(exc.issues),
                                )
                            )
                            continue
                        break
                    else:
                        trace.finish(output=merged, validation_issues=[])
                        return merged

                assert last_policy_error is not None
                trace.finish(
                    output=None,
                    validation_issues=[
                        issue.model_dump(mode="json") for issue in last_policy_error.issues
                    ],
                    error=str(last_policy_error),
                )
                raise SanitizationError(
                    last_policy_error.code,
                    str(last_policy_error),
                    last_policy_error.issues,
                ) from last_policy_error
            except SanitizationError:
                raise
            except Exception as exc:
                message = "The model could not produce a valid merged JSX component."
                trace.finish(output=None, validation_issues=[], error=message)
                raise SanitizationError(ErrorCode.MODEL_ERROR, message) from exc
