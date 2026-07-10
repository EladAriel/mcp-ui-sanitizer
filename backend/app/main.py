import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.config import Settings, get_settings
from app.jobs import JobNotFoundError, JobRegistry
from app.observability import flush_langfuse
from app.repos import RepoAccessError, RepositoryAccess
from app.schemas import (
    CleanDesignArtifactInput,
    InventoryRequest,
    InventoryResult,
    ProgressStage,
    RepoBrowseResult,
    SanitizeJobAccepted,
    SanitizeJobResult,
    SaveComponentRequest,
    SaveComponentResult,
    WorkflowJobAccepted,
    WorkflowJobResult,
    WorkflowRequest,
    WorkflowStep,
)
from app.service import SanitizationService
from app.workflow import WorkflowService
from app.workflow_jobs import WorkflowJobRegistry

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    service: SanitizationService | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_service = service or SanitizationService(resolved_settings)
    registry = JobRegistry(resolved_settings, resolved_service)
    repos = RepositoryAccess(resolved_settings)
    workflow_service = WorkflowService(resolved_settings, resolved_service, repos)
    workflow_registry = WorkflowJobRegistry(resolved_settings, workflow_service)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await registry.shutdown()
        await workflow_registry.shutdown()
        flush_langfuse(resolved_settings)

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.jobs = registry
    app.state.workflows = workflow_registry
    app.state.repos = repos
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(JobNotFoundError)
    async def job_not_found(_request: Request, _exc: JobNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": {"code": "JOB_EXPIRED", "message": "Job was not found or expired."}},
        )

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> JSONResponse:
        provider_key = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(resolved_settings.llm_provider)
        ready_state = provider_key is None or bool(os.getenv(provider_key))
        return JSONResponse(
            status_code=200 if ready_state else 503,
            content={
                "status": "ready" if ready_state else "not_ready",
                "provider": resolved_settings.llm_provider,
                "model": resolved_settings.llm_model,
                "reason": None if ready_state else f"{provider_key} is not configured",
            },
        )

    @app.get("/api/v1/repos/browse", response_model=RepoBrowseResult)
    async def browse_repo(
        path: str = Query(min_length=1),
        html_only: bool = Query(default=False),
    ) -> RepoBrowseResult:
        try:
            return repos.browse(path, html_only=html_only)
        except RepoAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": exc.code.value, "message": str(exc)},
            ) from exc

    @app.post("/api/v1/repos/inventory", response_model=InventoryResult)
    async def inventory_repo(payload: InventoryRequest) -> InventoryResult:
        try:
            return repos.inventory_production(
                payload.production_repo_path,
                payload.target_file_path,
            )
        except RepoAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": exc.code.value, "message": str(exc)},
            ) from exc

    @app.post("/api/v1/repos/save-component", response_model=SaveComponentResult)
    async def save_component(payload: SaveComponentRequest) -> SaveComponentResult:
        try:
            path, bytes_written = repos.save_component(
                payload.production_repo_path,
                payload.target_file_path,
                payload.source,
            )
            return SaveComponentResult(
                production_target_path=str(path),
                bytes_written=bytes_written,
            )
        except RepoAccessError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": exc.code.value, "message": str(exc)},
            ) from exc

    @app.post(
        "/api/v1/sanitizations",
        response_model=SanitizeJobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_sanitization(payload: CleanDesignArtifactInput) -> SanitizeJobAccepted:
        if len(payload.raw_code.encode()) > resolved_settings.max_code_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "code": "INVALID_INPUT",
                    "message": f"raw_code exceeds {resolved_settings.max_code_bytes} bytes.",
                },
            )
        job = await registry.create(payload)
        base = f"/api/v1/sanitizations/{job.job_id}"
        return SanitizeJobAccepted(
            job_id=job.job_id,
            events_url=f"{base}/events",
            result_url=base,
        )

    @app.get(
        "/api/v1/sanitizations/{job_id}",
        response_model=SanitizeJobResult,
    )
    async def get_sanitization(job_id: UUID) -> SanitizeJobResult:
        return (await registry.get(job_id)).result()

    @app.get("/api/v1/sanitizations/{job_id}/events")
    async def sanitization_events(job_id: UUID) -> EventSourceResponse:
        await registry.get(job_id)

        async def event_stream() -> AsyncIterator[ServerSentEvent]:
            async for event in registry.stream(job_id):
                event_name = "progress"
                if event.stage is ProgressStage.DONE:
                    event_name = "complete"
                elif event.stage is ProgressStage.FAILED:
                    event_name = "error"
                yield ServerSentEvent(
                    data=event.model_dump_json(),
                    event=event_name,
                    id=str(event.sequence),
                )

        return EventSourceResponse(
            event_stream(),
            ping=15,
            ping_message_factory=lambda: ServerSentEvent(comment="keepalive"),
        )

    @app.post(
        "/api/v1/workflows",
        response_model=WorkflowJobAccepted,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_workflow(payload: WorkflowRequest) -> WorkflowJobAccepted:
        job = await workflow_registry.create(payload)
        base = f"/api/v1/workflows/{job.job_id}"
        return WorkflowJobAccepted(
            job_id=job.job_id,
            events_url=f"{base}/events",
            result_url=base,
        )

    @app.get("/api/v1/workflows/{job_id}", response_model=WorkflowJobResult)
    async def get_workflow(job_id: UUID) -> WorkflowJobResult:
        return (await workflow_registry.get(job_id)).result()

    @app.get("/api/v1/workflows/{job_id}/events")
    async def workflow_events(job_id: UUID) -> EventSourceResponse:
        await workflow_registry.get(job_id)

        async def event_stream() -> AsyncIterator[ServerSentEvent]:
            async for event in workflow_registry.stream(job_id):
                event_name = "progress"
                if event.step is WorkflowStep.DONE:
                    event_name = "complete"
                elif event.step is WorkflowStep.FAILED:
                    event_name = "error"
                yield ServerSentEvent(
                    data=event.model_dump_json(),
                    event=event_name,
                    id=str(event.sequence),
                )

        return EventSourceResponse(
            event_stream(),
            ping=15,
            ping_message_factory=lambda: ServerSentEvent(comment="keepalive"),
        )

    return app


app = create_app()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
