import { Octagon, Workflow } from 'lucide-react'
import { toast } from 'sonner'
import { apiMode } from '@/api/client'
import { useBackendStatus } from '@/api/useBackendStatus'
import { Button } from '@/components/ui/button'
import { RUN_STATUS_LABELS } from '@/run/labels'
import { isRunActive, useStopRun } from '@/run/useRun'
import { useRunStore } from '@/workflow/store'

const BACKEND_MODE_TEXT: Record<string, string> = {
  mock: 'backend stand-in: no Dream-1, no credits. Status messages are replayed.',
  sim: 'cell tasks run the scripted controller; model results are precomputed measurements of the trained checkpoints. No live Dream-1 calls, no credits.',
}

export function MockBanner() {
  const status = useBackendStatus()
  const backendSimulated = status.data?.banner === 'SIMULIERTE API'
  const problems = status.data?.problems ?? []
  if (apiMode !== 'mock' && !backendSimulated && problems.length === 0) return null

  const text =
    apiMode === 'mock'
      ? 'test mode: no backend, no Dream-1, no credits. All status messages are replayed.'
      : (BACKEND_MODE_TEXT[status.data?.api_mode ?? ''] ?? 'backend reports a simulated mode.')
  return (
    <>
      {(apiMode === 'mock' || backendSimulated) && (
        <div
          role="status"
          data-testid="mock-banner"
          className="flex items-center justify-center gap-2 bg-amber-400 px-3 py-1 text-sm font-bold tracking-wide text-black"
          style={{ backgroundImage: 'repeating-linear-gradient(135deg, transparent 0 14px, rgba(0,0,0,.08) 14px 28px)' }}
        >
          {status.data?.api_mode === 'sim' && apiMode !== 'mock' ? 'PRECOMPUTED' : '⚠ SIMULATED API'} – {text}
        </div>
      )}
      {problems.map((problem) => (
        <div key={problem} role="alert" className="bg-red-100 px-3 py-1 text-center text-xs font-medium text-red-900">
          Backend: {problem}
        </div>
      ))}
    </>
  )
}

export function AppHeader() {
  const run = useRunStore((s) => s.run)
  const stop = useStopRun()
  const active = isRunActive(run)
  const status = useBackendStatus()
  const backendMode = status.data?.api_mode
  const simulated = apiMode === 'mock' || status.data?.banner === 'SIMULIERTE API'
  const modeLabel = apiMode === 'mock' ? 'SIMULATED' : backendMode === 'real' ? 'live' : backendMode === 'sim' ? 'PRECOMPUTED (sim)' : `SIMULATED (${backendMode ?? '…'})`

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b bg-slate-900 px-4 text-white">
      <Workflow className="size-5" aria-hidden />
      <h1 className="text-base font-semibold">DreamOrchestra</h1>
      <span className="hidden text-xs text-slate-300 xl:inline">Dream-1 skills as machine workflows, measured to show whether they really work</span>
      <span
        data-testid="api-mode"
        className={simulated ? 'rounded bg-amber-400 px-2 py-0.5 text-xs font-bold text-black' : 'rounded bg-emerald-600 px-2 py-0.5 text-xs font-semibold text-white'}
        title={status.isError ? `Status unavailable: ${status.error.message}` : undefined}
      >
        API: {modeLabel}
      </span>
      {run && (
        <span className="text-xs text-slate-300" aria-live="polite">
          Lauf {run.id}: {RUN_STATUS_LABELS[run.status]}
        </span>
      )}
      <Button
        data-testid="stop-button"
        variant="destructive"
        className="ml-auto h-9 bg-red-600 px-4 text-sm font-bold text-white hover:bg-red-700"
        disabled={stop.isPending}
        onClick={() => {
          if (!run || !active) {
            toast.info('No running workflow to stop.')
            return
          }
          stop.mutate(run.id)
        }}
      >
        <Octagon aria-hidden /> STOP
      </Button>
    </header>
  )
}
