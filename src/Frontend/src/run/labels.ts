import type { RunStatus } from '@/api/contract'

export const RUN_STATUS_LABELS: Record<RunStatus, string> = {
  queued: 'queued',
  running: 'running',
  paused: 'paused',
  succeeded: 'succeeded',
  failed: 'failed',
  stopped: 'stopped',
}
