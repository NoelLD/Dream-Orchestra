import { AlertCircle } from 'lucide-react'
import type { RunLogEntry } from '@/api/contract'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { BLOCKS } from '@/workflow/blocks'
import { useEditor, useRunStore } from '@/workflow/store'
import { RUN_STATUS_LABELS } from './labels'

const formatTime = (iso: string) => new Date(iso).toLocaleTimeString('de-DE', { hour12: false })
const formatDuration = (ms: number | null) => (ms === null ? '–' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`)

function apiStatusClass(status: string | null) {
  if (status === 'succeeded') return 'bg-emerald-100 text-emerald-900'
  if (status === 'timeout' || status === 'stopped') return 'bg-amber-100 text-amber-900'
  if (status === 'failed' || status === 'error') return 'bg-red-100 text-red-900'
  if (status === 'running') return 'bg-blue-100 text-blue-900'
  return 'bg-slate-100 text-slate-700'
}

export function RunLog({ pollError }: { pollError: Error | null }) {
  const run = useRunStore((s) => s.run)
  const nodes = useEditor((s) => s.nodes)
  const blockName = (entry: RunLogEntry) => {
    if (!entry.nodeId) return '–'
    const node = nodes.find((n) => n.id === entry.nodeId)
    return node ? node.data.label?.trim() || BLOCKS[node.type].label : entry.nodeId
  }

  return (
    <section aria-label="Ablaufprotokoll" className="flex h-full min-w-0 flex-col">
      <div className="flex items-center gap-3 border-b px-3 py-1.5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Protokoll</h2>
        {run ? (
          <>
            <Badge variant="outline" data-testid="run-status">Status: {RUN_STATUS_LABELS[run.status]}</Badge>
            <span className="text-xs text-slate-700" data-testid="run-credits">Credits verbraucht: {run.credits.used}</span>
            <span className="text-xs text-slate-500">Lauf {run.id}</span>
          </>
        ) : (
          <span className="text-xs text-slate-600">Noch kein Lauf gestartet.</span>
        )}
      </div>

      {run && run.log.length > 0 && (
        <p className="border-b bg-slate-50 px-3 py-1.5 text-sm font-medium" data-testid="run-last-message">
          <ExecutionBadge message={run.log[run.log.length - 1]!.message} />
          {run.log[run.log.length - 1]!.message}
        </p>
      )}

      {(pollError || run?.error) && (
        <Alert variant="destructive" className="m-2 py-2">
          <AlertCircle aria-hidden />
          <AlertTitle>{pollError ? 'Status konnte nicht abgefragt werden' : 'Lauf fehlgeschlagen'}</AlertTitle>
          <AlertDescription>{pollError?.message ?? run?.error}</AlertDescription>
        </Alert>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        <Table>
          <TableHeader className="sticky top-0 bg-white">
            <TableRow>
              <TableHead className="w-24">Zeit</TableHead>
              <TableHead className="w-40">Block</TableHead>
              <TableHead className="w-28">API-Status</TableHead>
              <TableHead className="w-20">Dauer</TableHead>
              <TableHead>Meldung</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...(run?.log ?? [])].reverse().map((entry, index) => (
              <TableRow key={`${entry.ts}-${index}`} className={cn(entry.level === 'error' && 'bg-red-50', entry.level === 'warn' && 'bg-amber-50')}>
                <TableCell className="font-mono text-xs">{formatTime(entry.ts)}</TableCell>
                <TableCell className="truncate text-xs">{blockName(entry)}</TableCell>
                <TableCell>
                  {entry.apiStatus ? <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-medium', apiStatusClass(entry.apiStatus))}>{entry.apiStatus}</span> : '–'}
                </TableCell>
                <TableCell className="text-xs">{formatDuration(entry.durationMs)}</TableCell>
                <TableCell className="whitespace-normal text-xs">
                  <ExecutionBadge message={entry.message} />
                  {entry.message}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  )
}

/** P4: Ausführungsart sichtbar machen – geskripteter Referenz-Controller (Zelle) oder Lauf im Simulationsdienst. */
function ExecutionBadge({ message }: { message: string }) {
  if (message.includes('geskriptet-')) {
    return <span className="mr-1.5 rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-800" title="Bewegung vom geskripteten Referenz-Controller der Zelle, nicht von Dream-1. Keine Credits.">Referenz-Controller</span>
  }
  if (/\brun_[a-z0-9]/.test(message)) {
    return <span className="mr-1.5 rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-900" title="Lauf im Simulationsdienst (Dream-1 im Modus real, sonst geskriptet).">Simulationslauf</span>
  }
  return null
}
