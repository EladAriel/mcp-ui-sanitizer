export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'

export type ProgressStage =
  | 'parsing_ast'
  | 'stripping_mock_logic'
  | 'llm_processing'
  | 'validating_output'
  | 'done'
  | 'failed'

export type WorkflowStep =
  | 'validating_repos'
  | 'inventorying_production'
  | 'confirming_allowlist'
  | 'loading_design'
  | 'invoking_sanitizer'
  | 'validating_policy'
  | 'merging_into_jsx'
  | 'generating_explanation'
  | 'done'
  | 'failed'

export interface SanitizeRequest {
  raw_code: string
  target_component_name: string
  allowed_features: string[]
}

export interface WorkflowRequest {
  production_repo_path: string
  design_repo_path: string
  design_html_path: string
  target_file_path: string
  target_component_name: string
  allowed_features: string[]
}

export interface JobAccepted {
  job_id: string
  status: 'queued'
  events_url: string
  result_url: string
}

export interface ValidationIssue {
  code: string
  message: string
  line: number | null
  column: number | null
}

export interface JobResult {
  job_id: string
  status: JobStatus
  sanitized_code: string | null
  validation_issues: ValidationIssue[]
  error: { code: string; message: string } | null
}

export interface WorkflowJobResult {
  job_id: string
  status: JobStatus
  raw_html: string | null
  sanitized_html: string | null
  production_jsx_before: string | null
  production_jsx_after: string | null
  explanation: string | null
  suggested_features: string[]
  production_target_path: string | null
  design_html_path: string | null
  validation_issues: ValidationIssue[]
  error: { code: string; message: string } | null
}

export interface SaveComponentRequest {
  production_repo_path: string
  target_file_path: string
  source: string
}

export interface SaveComponentResult {
  production_target_path: string
  bytes_written: number
}

export interface ProgressEvent {
  job_id: string
  sequence: number
  stage: ProgressStage
  message: string
  terminal: boolean
}

export interface TraceEvent {
  job_id: string
  sequence: number
  step: WorkflowStep
  summary: string
  duration_ms: number | null
  error: string | null
  terminal: boolean
  timestamp: string
}

export interface RepoEntry {
  name: string
  path: string
  kind: 'file' | 'directory'
  size: number | null
}

export interface RepoBrowseResult {
  root: string
  path: string
  entries: RepoEntry[]
}

export interface InventoryResult {
  production_repo_path: string
  target_file_path: string
  target_component_name: string
  language: string
  suggested_features: string[]
  tags: string[]
  interactive_tags: string[]
}
