import { useCallback, useEffect, useRef, useState } from 'react'

import {
  absoluteApiUrl,
  createSanitization,
  getSanitization,
} from './api'
import type {
  JobResult,
  ProgressEvent,
  SanitizeRequest,
} from './types'

type ConnectionState = 'idle' | 'connecting' | 'live' | 'closed'

export function useSanitizationJob() {
  const [logs, setLogs] = useState<ProgressEvent[]>([])
  const [result, setResult] = useState<JobResult | null>(null)
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
    async (request: SanitizeRequest) => {
      close()
      setLogs([])
      setResult(null)
      setError(null)
      setConnection('connecting')
      const controller = new AbortController()
      requestRef.current = controller

      try {
        const accepted = await createSanitization(request, controller.signal)
        const source = new EventSource(absoluteApiUrl(accepted.events_url))
        sourceRef.current = source

        const finish = async () => {
          source.close()
          sourceRef.current = null
          const completed = await getSanitization(
            accepted.result_url,
            controller.signal,
          )
          setResult(completed)
          if (completed.error) setError(completed.error.message)
          setConnection('closed')
        }

        const consume = (event: MessageEvent<string>) => {
          const progress = JSON.parse(event.data) as ProgressEvent
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
            setError(reason instanceof Error ? reason.message : 'Could not load result.')
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
          setError('The progress stream disconnected before completion.')
          setConnection('closed')
        }) as EventListener)
      } catch (reason) {
        if (controller.signal.aborted) return
        setError(reason instanceof Error ? reason.message : 'Sanitization failed.')
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
