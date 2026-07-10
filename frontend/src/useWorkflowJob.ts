import { useCallback, useEffect, useRef, useState } from 'react'

import { absoluteApiUrl, createWorkflow, getWorkflow } from './api'
import type { TraceEvent, WorkflowJobResult, WorkflowRequest } from './types'

type ConnectionState = 'idle' | 'connecting' | 'live' | 'closed'

async function pollUntilTerminal(
  resultUrl: string,
  signal: AbortSignal,
): Promise<WorkflowJobResult> {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const completed = await getWorkflow(resultUrl, signal)
    if (completed.status === 'completed' || completed.status === 'failed') {
      return completed
    }
    await new Promise((resolve) => setTimeout(resolve, 50))
  }
  return getWorkflow(resultUrl, signal)
}

export function useWorkflowJob() {
  const [logs, setLogs] = useState<TraceEvent[]>([])
  const [result, setResult] = useState<WorkflowJobResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connection, setConnection] = useState<ConnectionState>('idle')
  const sourceRef = useRef<EventSource | null>(null)
  const requestRef = useRef<AbortController | null>(null)

  const close = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
    requestRef.current?.abort()
    requestRef.current = null
  }, [])

  useEffect(() => close, [close])

  const submit = useCallback(
    async (request: WorkflowRequest) => {
      close()
      setLogs([])
      setResult(null)
      setError(null)
      setConnection('connecting')
      const controller = new AbortController()
      requestRef.current = controller

      try {
        const accepted = await createWorkflow(request, controller.signal)
        const source = new EventSource(absoluteApiUrl(accepted.events_url))
        sourceRef.current = source

        const finish = async () => {
          source.close()
          sourceRef.current = null
          const completed = await pollUntilTerminal(
            accepted.result_url,
            controller.signal,
          )
          setResult(completed)
          if (completed.error) setError(completed.error.message)
          setConnection('closed')
        }

        const consume = (event: MessageEvent<string>) => {
          const progress = JSON.parse(event.data) as TraceEvent
          setLogs((current) =>
            current.some((item) => item.sequence === progress.sequence)
              ? current
              : [...current, progress],
          )
        }

        source.onopen = () => setConnection('live')
        source.addEventListener('progress', consume as EventListener)
        source.addEventListener('complete', ((event: MessageEvent<string>) => {
          consume(event)
          void finish().catch((reason: unknown) => {
            setError(
              reason instanceof Error ? reason.message : 'Could not load result.',
            )
            setConnection('closed')
          })
        }) as EventListener)
        source.addEventListener('error', ((event: Event) => {
          if (event instanceof MessageEvent && event.data) {
            consume(event as MessageEvent<string>)
            void finish().catch(() => setConnection('closed'))
            return
          }
          source.close()
          void pollUntilTerminal(accepted.result_url, controller.signal)
            .then((completed) => {
              setResult(completed)
              if (completed.error) setError(completed.error.message)
              else if (completed.status !== 'completed') {
                setError('The progress stream disconnected before completion.')
              }
              setConnection('closed')
            })
            .catch(() => {
              setError('The progress stream disconnected before completion.')
              setConnection('closed')
            })
        }) as EventListener)
      } catch (reason) {
        if (controller.signal.aborted) return
        setError(reason instanceof Error ? reason.message : 'Workflow failed.')
        setConnection('closed')
      }
    },
    [close],
  )

  const reset = useCallback(() => {
    close()
    setLogs([])
    setResult(null)
    setError(null)
    setConnection('idle')
  }, [close])

  return {
    logs,
    result,
    error,
    connection,
    isRunning: connection === 'connecting' || connection === 'live',
    submit,
    reset,
  }
}
