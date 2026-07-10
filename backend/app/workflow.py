"""Repository HTML sanitization workflow orchestration."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.ast_policy import (
    SourceLanguage,
    extract_data_component_region,
    inventory_artifact,
    wrap_html_fragment,
)
from app.config import Settings
from app.repos import RepoAccessError, RepositoryAccess
from app.schemas import (
    CleanDesignArtifactInput,
    ErrorCode,
    ProgressStage,
    ValidationIssue,
    WorkflowRequest,
    WorkflowStep,
)
from app.service import SanitizationError, SanitizationService

TraceReporter = Callable[[WorkflowStep, str, int | None, str | None], Awaitable[None]]

_SUMMARY_LIMIT = 500


@dataclass(slots=True)
class WorkflowOutcome:
    raw_html: str
    sanitized_html: str
    production_jsx_before: str
    production_jsx_after: str
    explanation: str
    suggested_features: list[str]
    production_target_path: str
    design_html_path: str


async def _no_trace(
    _step: WorkflowStep,
    _summary: str,
    _duration_ms: int | None,
    _error: str | None,
) -> None:
    return None


def _clip(summary: str) -> str:
    if len(summary) <= _SUMMARY_LIMIT:
        return summary
    return summary[: _SUMMARY_LIMIT - 1] + "…"


def build_explanation(
    *,
    target_component_name: str,
    allowed_features: list[str],
    suggested_features: list[str],
    raw_html: str,
    sanitized_html: str,
    production_jsx_before: str,
    production_jsx_after: str,
) -> str:
    before = inventory_artifact(raw_html)
    after = inventory_artifact(sanitized_html)
    parts = [
        (
            f"Sanitized the design HTML and merged presentation into production target "
            f"'{target_component_name}' using the AST-enforced sanitizer."
        )
    ]
    if allowed_features:
        parts.append("Confirmed allowlist: " + ", ".join(allowed_features) + ".")
    else:
        parts.append("No product features were allowlisted; interactive handlers were stripped.")
    if suggested_features and suggested_features != allowed_features:
        parts.append(
            "Production inventory suggested: " + ", ".join(suggested_features) + "."
        )

    removed_tags = sorted(before.tags - after.tags)
    if removed_tags:
        parts.append("Removed elements: " + ", ".join(removed_tags) + ".")
    removed_interactions = sorted(before.interactive_tags - after.interactive_tags)
    if removed_interactions:
        parts.append(
            "Removed interactive controls: " + ", ".join(removed_interactions) + "."
        )
    if before.text_literals != after.text_literals:
        removed_text = sorted(before.text_literals - after.text_literals)
        if removed_text:
            preview = ", ".join(repr(item) for item in removed_text[:5])
            parts.append(f"Removed text/values not present after sanitization: {preview}.")
    if production_jsx_before == production_jsx_after:
        parts.append("Production JSX was unchanged after the presentation merge.")
    else:
        parts.append(
            f"Production JSX changed from {len(production_jsx_before.encode())} to "
            f"{len(production_jsx_after.encode())} bytes."
        )
    if raw_html == sanitized_html:
        parts.append("The design HTML already satisfied the stateless presentation policy.")
    else:
        parts.append(
            f"HTML size changed from {len(raw_html.encode())} to "
            f"{len(sanitized_html.encode())} bytes."
        )
    return " ".join(parts)


class WorkflowService:
    def __init__(
        self,
        settings: Settings,
        sanitization: SanitizationService,
        repos: RepositoryAccess | None = None,
    ):
        self.settings = settings
        self.sanitization = sanitization
        self.repos = repos or RepositoryAccess(settings)

    async def run(
        self,
        request: WorkflowRequest,
        *,
        request_id: str,
        report: TraceReporter | None = None,
    ) -> WorkflowOutcome:
        emit = report or _no_trace

        async def step(
            workflow_step: WorkflowStep,
            summary: str,
            *,
            mark_start: float | None = None,
            error: str | None = None,
        ) -> float:
            duration = None if mark_start is None else int((time.monotonic() - mark_start) * 1000)
            await emit(workflow_step, _clip(summary), duration, error)
            return time.monotonic()

        mark = await step(
            WorkflowStep.VALIDATING_REPOS,
            "Validating production and design repository paths under workspace roots…",
        )
        try:
            production_repo = self.repos.resolve_path(request.production_repo_path)
            design_repo = self.repos.resolve_path(request.design_repo_path)
            if not production_repo.is_dir() or not design_repo.is_dir():
                raise RepoAccessError("Both production and design paths must be directories.")
            mark = await step(
                WorkflowStep.VALIDATING_REPOS,
                f"Accepted production={production_repo} design={design_repo}.",
                mark_start=mark,
            )

            mark = await step(
                WorkflowStep.INVENTORYING_PRODUCTION,
                f"Inventorying production target {request.target_file_path}…",
            )
            inventory = self.repos.inventory_production(
                request.production_repo_path,
                request.target_file_path,
            )
            production_path = self.repos.resolve_under_repo(
                request.production_repo_path,
                request.target_file_path,
            )
            production_jsx_before = self.repos.read_text_file(production_path)
            if inventory.language != SourceLanguage.TSX.value:
                raise SanitizationError(
                    ErrorCode.INVALID_INPUT,
                    "Production target must be a JSX/TSX component for presentation merge.",
                    [
                        ValidationIssue(
                            code="JSX_REQUIRED",
                            message=(
                                f"Detected language '{inventory.language}'. "
                                "Select a .jsx/.tsx production component."
                            ),
                        )
                    ],
                )
            mark = await step(
                WorkflowStep.INVENTORYING_PRODUCTION,
                (
                    f"Found language={inventory.language}, "
                    f"component={inventory.target_component_name}, "
                    f"{len(inventory.suggested_features)} suggested features."
                ),
                mark_start=mark,
            )

            mark = await step(
                WorkflowStep.CONFIRMING_ALLOWLIST,
                (
                    "Confirming explicit allowlist "
                    f"({len(request.allowed_features)} features); "
                    "no extra capabilities inferred."
                ),
            )
            mark = await step(
                WorkflowStep.CONFIRMING_ALLOWLIST,
                (
                    "Allowlist locked: "
                    + (", ".join(request.allowed_features) if request.allowed_features else "none")
                    + "."
                ),
                mark_start=mark,
            )

            mark = await step(
                WorkflowStep.LOADING_DESIGN,
                f"Loading design HTML from {request.design_html_path}…",
            )
            design_path, raw_html = self.repos.load_design_html(
                request.design_repo_path,
                request.design_html_path,
            )
            mark = await step(
                WorkflowStep.LOADING_DESIGN,
                f"Loaded {len(raw_html.encode())} bytes from {design_path}.",
                mark_start=mark,
            )

            mark = await step(
                WorkflowStep.INVOKING_SANITIZER,
                "Invoking sanitizer service (AST preflight + LLM + policy validation)…",
            )

            region = extract_data_component_region(raw_html, request.target_component_name)
            sanitize_input = wrap_html_fragment(region) if region else raw_html

            async def map_progress(stage: ProgressStage, message: str) -> None:
                if stage is ProgressStage.VALIDATING_OUTPUT:
                    await emit(
                        WorkflowStep.VALIDATING_POLICY,
                        _clip(message),
                        None,
                        None,
                    )
                elif stage in {
                    ProgressStage.PARSING_AST,
                    ProgressStage.STRIPPING_MOCK_LOGIC,
                    ProgressStage.LLM_PROCESSING,
                }:
                    await emit(
                        WorkflowStep.INVOKING_SANITIZER,
                        _clip(f"[{stage.value}] {message}"),
                        None,
                        None,
                    )

            sanitized_html = await self.sanitization.clean(
                CleanDesignArtifactInput(
                    raw_code=sanitize_input,
                    target_component_name=request.target_component_name,
                    allowed_features=request.allowed_features,
                ),
                source="workflow",
                request_id=request_id,
                progress=map_progress,
            )
            mark = await step(
                WorkflowStep.INVOKING_SANITIZER,
                "Sanitizer returned validated presentation HTML.",
                mark_start=mark,
            )
            mark = await step(
                WorkflowStep.VALIDATING_POLICY,
                "AST policy validation completed inside the sanitizer service.",
                mark_start=mark,
            )

            mark = await step(
                WorkflowStep.MERGING_INTO_JSX,
                "Merging sanitized HTML presentation into production JSX…",
            )

            async def map_merge_progress(stage: ProgressStage, message: str) -> None:
                if stage is ProgressStage.VALIDATING_OUTPUT:
                    await emit(
                        WorkflowStep.MERGING_INTO_JSX,
                        _clip(message),
                        None,
                        None,
                    )
                else:
                    await emit(
                        WorkflowStep.MERGING_INTO_JSX,
                        _clip(f"[{stage.value}] {message}"),
                        None,
                        None,
                    )

            production_jsx_after = await self.sanitization.merge_presentation(
                production_jsx=production_jsx_before,
                sanitized_html=sanitized_html,
                target_component_name=request.target_component_name,
                allowed_features=request.allowed_features,
                source="workflow-merge",
                request_id=request_id,
                progress=map_merge_progress,
            )
            mark = await step(
                WorkflowStep.MERGING_INTO_JSX,
                "Merged JSX passed production presentation policy.",
                mark_start=mark,
            )

            mark = await step(
                WorkflowStep.GENERATING_EXPLANATION,
                "Building an evidence-based explanation from inventory diffs…",
            )
            explanation = build_explanation(
                target_component_name=request.target_component_name,
                allowed_features=request.allowed_features,
                suggested_features=inventory.suggested_features,
                raw_html=sanitize_input,
                sanitized_html=sanitized_html,
                production_jsx_before=production_jsx_before,
                production_jsx_after=production_jsx_after,
            )
            await step(
                WorkflowStep.GENERATING_EXPLANATION,
                explanation,
                mark_start=mark,
            )
            return WorkflowOutcome(
                raw_html=raw_html,
                sanitized_html=sanitized_html,
                production_jsx_before=production_jsx_before,
                production_jsx_after=production_jsx_after,
                explanation=explanation,
                suggested_features=inventory.suggested_features,
                production_target_path=inventory.target_file_path,
                design_html_path=str(design_path),
            )
        except RepoAccessError as exc:
            raise SanitizationError(exc.code, str(exc), exc.issues) from exc


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
