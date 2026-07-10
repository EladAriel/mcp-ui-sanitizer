export type JobStatus = 'queued' | 'running' | 'completed' | 'failed'

export type ProgressStage =
  | 'parsing_ast'
  | 'stripping_mock_logic'
  | 'llm_processing'
  | 'validating_output'
  | 'done'
  | 'failed'

export interface SanitizeRequest {
  raw_code: string
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

export interface ProgressEvent {
  job_id: string
  sequence: number
  stage: ProgressStage
  message: string
  terminal: boolean
}
