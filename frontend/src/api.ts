import type { JobAccepted, JobResult, SanitizeRequest } from './types'

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

export function absoluteApiUrl(path: string): string {
  return new URL(`${API_BASE}${path}`, window.location.origin).toString()
}
