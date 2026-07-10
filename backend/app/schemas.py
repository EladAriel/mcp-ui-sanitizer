from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

NonEmptyText = Annotated[str, Field(min_length=1)]


class CleanDesignArtifactInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    raw_code: NonEmptyText
    target_component_name: Annotated[
        str,
        Field(min_length=1, pattern=r"^[A-Za-z_$][A-Za-z0-9_$.-]*$"),
    ]
    allowed_features: list[NonEmptyText] = Field(default_factory=list, max_length=100)

    @field_validator("allowed_features")
    @classmethod
    def features_are_unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class SanitizedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: NonEmptyText


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    line: int | None = None
    column: int | None = None


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_SYNTAX = "INVALID_SYNTAX"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    MODEL_ERROR = "MODEL_ERROR"
    JOB_EXPIRED = "JOB_EXPIRED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: ErrorCode
    message: str


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SanitizeJobAccepted(BaseModel):
    job_id: UUID
    status: Literal[JobStatus.QUEUED] = JobStatus.QUEUED
    events_url: str
    result_url: str


class SanitizeJobResult(BaseModel):
    job_id: UUID
    status: JobStatus
    sanitized_code: str | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    error: ApiError | None = None


class ProgressStage(StrEnum):
    PARSING_AST = "parsing_ast"
    STRIPPING_MOCK_LOGIC = "stripping_mock_logic"
    LLM_PROCESSING = "llm_processing"
    VALIDATING_OUTPUT = "validating_output"
    DONE = "done"
    FAILED = "failed"


class ProgressEvent(BaseModel):
    job_id: UUID
    sequence: int = Field(ge=1)
    stage: ProgressStage
    message: str
    terminal: bool = False
