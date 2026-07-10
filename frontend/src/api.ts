import type {
  InventoryResult,
  JobAccepted,
  JobResult,
  RepoBrowseResult,
  SanitizeRequest,
  SaveComponentRequest,
  SaveComponentResult,
  WorkflowJobResult,
  WorkflowRequest,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as {
      detail?: string | { message?: string }
    }
    if (typeof body.detail === 'string') return body.detail
    return body.detail?.message ?? `Request failed with status ${response.status}`
  } catch {
    return `Request failed with status ${response.status}`
  }
}

export async function createSanitization(
  request: SanitizeRequest,
  signal?: AbortSignal,
): Promise<JobAccepted> {
  const response = await fetch(`${API_BASE}/api/v1/sanitizations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<JobAccepted>
}

export async function getSanitization(
  resultUrl: string,
  signal?: AbortSignal,
): Promise<JobResult> {
  const response = await fetch(`${API_BASE}${resultUrl}`, { signal })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<JobResult>
}

export async function browseRepo(
  path: string,
  options?: { htmlOnly?: boolean; signal?: AbortSignal },
): Promise<RepoBrowseResult> {
  const params = new URLSearchParams({ path })
  if (options?.htmlOnly) params.set('html_only', 'true')
  const response = await fetch(`${API_BASE}/api/v1/repos/browse?${params}`, {
    signal: options?.signal,
  })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<RepoBrowseResult>
}

export async function inventoryRepo(
  productionRepoPath: string,
  targetFilePath: string,
  signal?: AbortSignal,
): Promise<InventoryResult> {
  const response = await fetch(`${API_BASE}/api/v1/repos/inventory`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      production_repo_path: productionRepoPath,
      target_file_path: targetFilePath,
    }),
    signal,
  })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<InventoryResult>
}

export async function createWorkflow(
  request: WorkflowRequest,
  signal?: AbortSignal,
): Promise<JobAccepted> {
  const response = await fetch(`${API_BASE}/api/v1/workflows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<JobAccepted>
}

export async function getWorkflow(
  resultUrl: string,
  signal?: AbortSignal,
): Promise<WorkflowJobResult> {
  const response = await fetch(`${API_BASE}${resultUrl}`, { signal })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<WorkflowJobResult>
}

export async function saveComponent(
  request: SaveComponentRequest,
  signal?: AbortSignal,
): Promise<SaveComponentResult> {
  const response = await fetch(`${API_BASE}/api/v1/repos/save-component`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<SaveComponentResult>
}

export function absoluteApiUrl(path: string): string {
  return new URL(`${API_BASE}${path}`, window.location.origin).toString()
}
