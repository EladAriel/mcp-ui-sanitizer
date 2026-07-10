import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.config import Settings, get_settings
from app.jobs import JobNotFoundError, JobRegistry
from app.observability import flush_langfuse
from app.schemas import (
    CleanDesignArtifactInput,
    ProgressStage,
    SanitizeJobAccepted,
    SanitizeJobResult,
)
from app.service import SanitizationService

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    service: SanitizationService | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_service = service or SanitizationService(resolved_settings)
    registry = JobRegistry(resolved_settings, resolved_service)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await registry.shutdown()
        flush_langfuse(resolved_settings)

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.jobs = registry
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

    return app


app = create_app()


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
