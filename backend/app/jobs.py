import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.config import Settings
from app.schemas import (
    ApiError,
    CleanDesignArtifactInput,
    ErrorCode,
    JobStatus,
    ProgressEvent,
    ProgressStage,
    SanitizeJobResult,
    ValidationIssue,
)
from app.service import SanitizationError, SanitizationService


@dataclass(slots=True)
class JobRecord:
    job_id: UUID
    request: CleanDesignArtifactInput
    created_at: float = field(default_factory=time.monotonic)
    status: JobStatus = JobStatus.QUEUED
    sanitized_code: str | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    error: ApiError | None = None
    events: list[ProgressEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[ProgressEvent]] = field(default_factory=set)
    task: asyncio.Task[None] | None = None

    def result(self) -> SanitizeJobResult:
        return SanitizeJobResult(
            job_id=self.job_id,
            status=self.status,
            sanitized_code=self.sanitized_code,
            validation_issues=self.issues,
            error=self.error,
        )


class JobNotFoundError(KeyError):
    pass


class JobRegistry:
    def __init__(self, settings: Settings, service: SanitizationService):
        self.settings = settings
        self.service = service
        self._jobs: dict[UUID, JobRecord] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    async def create(self, request: CleanDesignArtifactInput) -> JobRecord:
        await self._prune()
        job = JobRecord(job_id=uuid4(), request=request)
        async with self._lock:
            self._jobs[job.job_id] = job
        job.task = asyncio.create_task(self._run(job), name=f"sanitize-{job.job_id}")
        return job

    async def get(self, job_id: UUID) -> JobRecord:
        await self._prune()
        async with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            raise JobNotFoundError(job_id)
        return job

    async def _publish(
        self,
        job: JobRecord,
        stage: ProgressStage,
        message: str,
        *,
        terminal: bool = False,
    ) -> None:
        event = ProgressEvent(
            job_id=job.job_id,
            sequence=len(job.events) + 1,
            stage=stage,
            message=message,
            terminal=terminal,
        )
        job.events.append(event)
        for queue in tuple(job.subscribers):
            queue.put_nowait(event)

    async def _run(self, job: JobRecord) -> None:
        async with self._semaphore:
            job.status = JobStatus.RUNNING
            try:
                job.sanitized_code = await self.service.clean(
                    job.request,
                    source="rest",
                    request_id=str(job.job_id),
                    progress=lambda stage, message: self._publish(job, stage, message),
                )
                job.status = JobStatus.COMPLETED
                await self._publish(
                    job,
                    ProgressStage.DONE,
                    "Sanitized artifact is ready.",
                    terminal=True,
                )
            except SanitizationError as exc:
                job.status = JobStatus.FAILED
                job.issues = exc.issues
                job.error = ApiError(code=exc.code, message=str(exc))
                await self._publish(job, ProgressStage.FAILED, str(exc), terminal=True)
            except asyncio.CancelledError:
                job.status = JobStatus.FAILED
                job.error = ApiError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Sanitization was cancelled.",
                )
                await self._publish(
                    job,
                    ProgressStage.FAILED,
                    "Sanitization was cancelled.",
                    terminal=True,
                )
                raise
            except Exception:
                job.status = JobStatus.FAILED
                job.error = ApiError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="An unexpected sanitization error occurred.",
                )
                await self._publish(
                    job,
                    ProgressStage.FAILED,
                    "An unexpected sanitization error occurred.",
                    terminal=True,
                )

    async def stream(self, job_id: UUID) -> AsyncIterator[ProgressEvent]:
        job = await self.get(job_id)
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
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
