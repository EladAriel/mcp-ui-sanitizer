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


class RepoEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    path: str
    kind: Literal["file", "directory"]
    size: int | None = None


class RepoBrowseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str
    path: str
    entries: list[RepoEntry]


class InventoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    production_repo_path: NonEmptyText
    target_file_path: NonEmptyText


class InventoryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    production_repo_path: str
    target_file_path: str
    target_component_name: str
    language: str
    suggested_features: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    interactive_tags: list[str] = Field(default_factory=list)


class WorkflowStep(StrEnum):
    VALIDATING_REPOS = "validating_repos"
    INVENTORYING_PRODUCTION = "inventorying_production"
    CONFIRMING_ALLOWLIST = "confirming_allowlist"
    LOADING_DESIGN = "loading_design"
    INVOKING_SANITIZER = "invoking_sanitizer"
    VALIDATING_POLICY = "validating_policy"
    MERGING_INTO_JSX = "merging_into_jsx"
    GENERATING_EXPLANATION = "generating_explanation"
    DONE = "done"
    FAILED = "failed"


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    production_repo_path: NonEmptyText
    design_repo_path: NonEmptyText
    design_html_path: NonEmptyText
    target_file_path: NonEmptyText
    target_component_name: Annotated[
        str,
        Field(min_length=1, pattern=r"^[A-Za-z_$][A-Za-z0-9_$.-]*$"),
    ]
    allowed_features: list[NonEmptyText] = Field(default_factory=list, max_length=100)

    @field_validator("allowed_features")
    @classmethod
    def features_are_unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class WorkflowJobAccepted(BaseModel):
    job_id: UUID
    status: Literal[JobStatus.QUEUED] = JobStatus.QUEUED
    events_url: str
    result_url: str


class WorkflowJobResult(BaseModel):
    job_id: UUID
    status: JobStatus
    raw_html: str | None = None
    sanitized_html: str | None = None
    production_jsx_before: str | None = None
    production_jsx_after: str | None = None
    explanation: str | None = None
    suggested_features: list[str] = Field(default_factory=list)
    production_target_path: str | None = None
    design_html_path: str | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    error: ApiError | None = None


class SaveComponentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    production_repo_path: NonEmptyText
    target_file_path: NonEmptyText
    source: NonEmptyText

    @field_validator("production_repo_path", "target_file_path", mode="before")
    @classmethod
    def strip_paths(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SaveComponentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    production_target_path: str
    bytes_written: int


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    sequence: int = Field(ge=1)
    step: WorkflowStep
    summary: str
    duration_ms: int | None = None
    error: str | None = None
    terminal: bool = False
    timestamp: str
