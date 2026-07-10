"""Async job registry for repository sanitization workflows."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.config import Settings
from app.schemas import (
    ApiError,
    ErrorCode,
    JobStatus,
    TraceEvent,
    ValidationIssue,
    WorkflowJobResult,
    WorkflowRequest,
    WorkflowStep,
)
from app.service import SanitizationError
from app.workflow import WorkflowService, utc_timestamp


@dataclass(slots=True)
class WorkflowJobRecord:
    job_id: UUID
    request: WorkflowRequest
    created_at: float = field(default_factory=time.monotonic)
    status: JobStatus = JobStatus.QUEUED
    raw_html: str | None = None
    sanitized_html: str | None = None
    production_jsx_before: str | None = None
    production_jsx_after: str | None = None
    explanation: str | None = None
    suggested_features: list[str] = field(default_factory=list)
    production_target_path: str | None = None
    design_html_path: str | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    error: ApiError | None = None
    events: list[TraceEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[TraceEvent]] = field(default_factory=set)
    task: asyncio.Task[None] | None = None

    def result(self) -> WorkflowJobResult:
        return WorkflowJobResult(
            job_id=self.job_id,
            status=self.status,
            raw_html=self.raw_html,
            sanitized_html=self.sanitized_html,
            production_jsx_before=self.production_jsx_before,
            production_jsx_after=self.production_jsx_after,
            explanation=self.explanation,
            suggested_features=self.suggested_features,
            production_target_path=self.production_target_path,
            design_html_path=self.design_html_path,
            validation_issues=self.issues,
            error=self.error,
        )


class WorkflowJobRegistry:
    def __init__(self, settings: Settings, workflow: WorkflowService):
        self.settings = settings
        self.workflow = workflow
        self._jobs: dict[UUID, WorkflowJobRecord] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    async def create(self, request: WorkflowRequest) -> WorkflowJobRecord:
        await self._prune()
        job = WorkflowJobRecord(job_id=uuid4(), request=request)
        async with self._lock:
            self._jobs[job.job_id] = job
        job.task = asyncio.create_task(self._run(job), name=f"workflow-{job.job_id}")
        return job

    async def get(self, job_id: UUID) -> WorkflowJobRecord:
        await self._prune()
        async with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            from app.jobs import JobNotFoundError

            raise JobNotFoundError(job_id)
        return job

    async def _publish(
        self,
        job: WorkflowJobRecord,
        step: WorkflowStep,
        summary: str,
        duration_ms: int | None,
        error: str | None,
    ) -> None:
        terminal = step in {WorkflowStep.DONE, WorkflowStep.FAILED}
        event = TraceEvent(
            job_id=job.job_id,
            sequence=len(job.events) + 1,
            step=step,
            summary=summary,
            duration_ms=duration_ms,
            error=error,
            terminal=terminal,
            timestamp=utc_timestamp(),
        )
        job.events.append(event)
        for queue in tuple(job.subscribers):
            queue.put_nowait(event)

    async def _run(self, job: WorkflowJobRecord) -> None:
        async with self._semaphore:
            job.status = JobStatus.RUNNING
            try:
                outcome = await self.workflow.run(
                    job.request,
                    request_id=str(job.job_id),
                    report=lambda step, summary, duration_ms, error: self._publish(
                        job, step, summary, duration_ms, error
                    ),
                )
                job.raw_html = outcome.raw_html
                job.sanitized_html = outcome.sanitized_html
                job.production_jsx_before = outcome.production_jsx_before
                job.production_jsx_after = outcome.production_jsx_after
                job.explanation = outcome.explanation
                job.suggested_features = outcome.suggested_features
                job.production_target_path = outcome.production_target_path
                job.design_html_path = outcome.design_html_path
                job.status = JobStatus.COMPLETED
                elapsed_ms = int((time.monotonic() - job.created_at) * 1000)
                await self._publish(
                    job,
                    WorkflowStep.DONE,
                    f"Workflow completed in {elapsed_ms} ms.",
                    elapsed_ms,
                    None,
                )
            except SanitizationError as exc:
                job.status = JobStatus.FAILED
                job.issues = exc.issues
                job.error = ApiError(code=exc.code, message=str(exc))
                await self._publish(job, WorkflowStep.FAILED, str(exc), None, str(exc))
            except asyncio.CancelledError:
                job.status = JobStatus.FAILED
                job.error = ApiError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Workflow was cancelled.",
                )
                await self._publish(
                    job,
                    WorkflowStep.FAILED,
                    "Workflow was cancelled.",
                    None,
                    "Workflow was cancelled.",
                )
                raise
            except Exception:
                job.status = JobStatus.FAILED
                message = "An unexpected workflow error occurred."
                job.error = ApiError(code=ErrorCode.INTERNAL_ERROR, message=message)
                await self._publish(job, WorkflowStep.FAILED, message, None, message)

    async def stream(self, job_id: UUID) -> AsyncIterator[TraceEvent]:
        job = await self.get(job_id)
        queue: asyncio.Queue[TraceEvent] = asyncio.Queue()
        replay = list(job.events)
        terminal = job.status in {JobStatus.COMPLETED, JobStatus.FAILED}
        if not terminal:
            job.subscribers.add(queue)
        try:
            for event in replay:
                yield event
            while not terminal:
                event = await queue.get()
                yield event
                if event.terminal:
                    terminal = True
        finally:
            job.subscribers.discard(queue)

    async def shutdown(self) -> None:
        tasks = [job.task for job in self._jobs.values() if job.task and not job.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _prune(self) -> None:
        cutoff = time.monotonic() - self.settings.job_ttl_seconds
        async with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.created_at < cutoff and job.status in {JobStatus.COMPLETED, JobStatus.FAILED}
            ]
            for job_id in expired:
                del self._jobs[job_id]
