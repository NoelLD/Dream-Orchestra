import type { RunStatus } from '@/api/contract'

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  queued: 'wartet',
  running: 'läuft',
  paused: 'pausiert',
  succeeded: 'erfolgreich',
  failed: 'fehlgeschlagen',
  stopped: 'gestoppt',
}
