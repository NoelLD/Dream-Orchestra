import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { TERMINAL_RUN_STATUSES, type Run, type StartRunRequest } from '@/api/contract'
import { validationFromError } from '@/api/realClient'
import { useEditor, useRunStore } from '@/workflow/store'

export const isRunActive = (run: Run | null) => run !== null && !TERMINAL_RUN_STATUSES.includes(run.status)

/** Fragt den Status des aktuellen Laufs ab, bis er beendet ist (F5/F6, N5). Einmal in App einbinden. */
export function useRunPolling() {
  const runId = useRunStore((s) => s.runId)
  const pollIntervalMs = useRunStore((s) => s.pollIntervalMs)
  const setRun = useRunStore((s) => s.setRun)

  const query = useQuery({
    queryKey: ['run', runId],
    queryFn: () => api.getRun(runId as string),
    enabled: runId !== null,
    retry: false,
    refetchInterval: (q) => {
      const run = q.state.data
      return run && TERMINAL_RUN_STATUSES.includes(run.status) ? false : pollIntervalMs
    },
  })

  useEffect(() => {
    if (query.data) setRun(query.data)
  }, [query.data, setRun])

  return query
}

export function useStartRun() {
  const setRun = useRunStore((s) => s.setRun)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (request: StartRunRequest) => api.startRun(request),
    onSuccess: (run) => {
      queryClient.setQueryData(['run', run.id], run)
      setRun(run)
      toast.success('Lauf gestartet')
    },
    onError: (error) => {
      // 422 vom Backend: Prüfergebnis pro Block am Block markieren (F4)
      const remote = validationFromError(error)
      if (remote) {
        useEditor.getState().setIssues(remote.issues)
        toast.error(`Start abgelehnt: ${remote.issues.length} Problem(e) – am Block markiert`)
        return
      }
      toast.error(`Start fehlgeschlagen: ${error.message}`)
    },
  })
}

const ACTIONS = {
  pause: { call: (id: string) => api.pauseRun(id), done: 'Lauf pausiert' },
  resume: { call: (id: string) => api.resumeRun(id), done: 'Lauf fortgesetzt' },
  step: { call: (id: string) => api.stepRun(id), done: 'Einzelschritt' },
} as const

/** Pause / Weiter / Einzelschritt (F8) */
export function useRunAction(kind: keyof typeof ACTIONS) {
  const setRun = useRunStore((s) => s.setRun)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => ACTIONS[kind].call(runId),
    onSuccess: (run) => {
      queryClient.setQueryData(['run', run.id], run)
      setRun(run)
      toast.info(ACTIONS[kind].done)
    },
    onError: (error) => toast.error(error.message),
  })
}

export function useStopRun() {
  const setRun = useRunStore((s) => s.setRun)
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (runId: string) => api.stopRun(runId),
    onSuccess: (run) => {
      queryClient.setQueryData(['run', run.id], run)
      setRun(run)
      toast.warning('Lauf gestoppt')
    },
    onError: (error) => toast.error(`Stopp fehlgeschlagen: ${error.message}`),
  })
}
