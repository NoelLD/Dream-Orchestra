import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Power, PowerOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type { CellAction, CellSession, CellView } from '@/api/contract'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

const CELL_NAMES: Record<string, string> = { conveyor: 'Fließband (Sortieren)', cnc: 'CNC-Maschine (Be- und Entladen)' }
const TASK_NAMES: Record<string, string> = {
  sort_round: 'Rundteil in grüne Kiste',
  sort_cube: 'Würfel in blaue Kiste',
  cnc_load: 'Rohteil auf die Maschinenplatte',
  cnc_unload: 'Fertigteil in die Ablage',
}
const ACTIONS: Record<string, { action: CellAction; label: string }[]> = {
  cnc: [
    { action: 'door_open', label: 'Tür auf' },
    { action: 'door_close', label: 'Tür zu' },
    { action: 'cycle_start', label: 'Zyklus starten' },
    { action: 'light_green', label: 'Ampel grün' },
    { action: 'light_red', label: 'Ampel rot' },
    { action: 'light_off', label: 'Ampel aus' },
  ],
  conveyor: [
    { action: 'belt_on', label: 'Band an' },
    { action: 'belt_off', label: 'Band aus' },
    { action: 'feed', label: 'Teil zuführen' },
    { action: 'auto_on', label: 'Automatik an' },
    { action: 'auto_off', label: 'Automatik aus' },
  ],
}
const SENSOR_NAMES: Record<string, string> = {
  door_open: 'Tür offen',
  door_closed: 'Tür zu',
  tray_out: 'Platte draußen',
  tray_in: 'Platte drinnen',
  raw_part_on_tray: 'Rohteil auf Platte',
  finished_part_on_tray: 'Fertigteil auf Platte',
  machine_running: 'Maschine läuft',
  machine_done: 'Maschine fertig',
  stack_light: 'Ampel',
  cycles: 'Zyklen',
  part_at_light_barrier: 'Teil an Lichtschranke',
  belt_on: 'Band läuft',
  auto: 'Automatik',
  barrier_right: 'Lichtschranke rechts',
  barrier_left: 'Lichtschranke links',
  parts_on_belt: 'Teile auf dem Band',
  waiting: 'Wartet auf Arm',
}

function sensorText(value: unknown): string {
  if (value === true) return 'ja'
  if (value === false) return 'nein'
  if (value === null || value === undefined) return '–'
  if (typeof value === 'object') return Object.values(value as Record<string, unknown>).join(' · ')
  return String(value)
}

function LiveImage({ session, view }: { session: CellSession | null; view: CellView }) {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!session) return
    const timer = window.setInterval(() => setTick((t) => t + 1), 400)
    return () => window.clearInterval(timer)
  }, [session])
  if (!session) {
    return (
      <div className="grid aspect-video place-items-center rounded-md bg-slate-200 text-sm text-slate-600">
        Keine Sitzung. Zelle wählen und „Sitzung starten“.
      </div>
    )
  }
  return (
    <img
      src={api.cellFrameUrl(view, tick)}
      alt={`Live-Bild der Zelle ${session.cell}, Ansicht ${view === 'overview' ? 'Übersicht' : 'Roboterkamera'}`}
      className="aspect-video w-full rounded-md bg-slate-200 object-cover"
      data-testid="cell-frame"
    />
  )
}

export function CellsView() {
  const queryClient = useQueryClient()
  const [view, setView] = useState<CellView>('overview')
  const [seed, setSeed] = useState('1000')
  const cells = useQuery({ queryKey: ['cells'], queryFn: () => api.listCells() })
  const session = useQuery({ queryKey: ['cell-session'], queryFn: () => api.getCellSession(), refetchInterval: 1000 })
  const current = session.data ?? null
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['cell-session'] })

  const start = useMutation({
    mutationFn: (cell: string) => api.startCellSession(cell),
    onSuccess: refresh,
    onError: (e) => toast.error(e.message),
  })
  const end = useMutation({ mutationFn: () => api.endCellSession(), onSuccess: refresh, onError: (e) => toast.error(e.message) })
  const act = useMutation({
    mutationFn: (action: CellAction) => api.cellAction(action),
    onSuccess: refresh,
    onError: (e) => toast.error(e.message),
  })
  const task = useMutation({
    mutationFn: (name: string) => api.cellTask(name, seed.trim() === '' ? undefined : Number(seed)),
    onSuccess: refresh,
    onError: (e) => toast.error(e.message),
  })

  const cell = cells.data?.find((c) => c.cell === current?.cell)
  const sensors = Object.entries(current?.sensors ?? {})
  const result = current?.last_result

  return (
    <div className="mx-auto grid max-w-[1400px] grid-cols-[minmax(0,1fr)_400px] gap-6 p-6">
      <section className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-2 text-lg font-semibold">Zellen-Leitstand</h2>
          {cells.data?.map((c) => (
            <Button
              key={c.cell}
              variant={current?.cell === c.cell ? 'default' : 'outline'}
              disabled={start.isPending}
              onClick={() => start.mutate(c.cell)}
            >
              <Power className="size-4" aria-hidden /> {CELL_NAMES[c.cell] ?? c.cell}
            </Button>
          ))}
          {current && (
            <Button variant="ghost" onClick={() => end.mutate()} disabled={end.isPending}>
              <PowerOff className="size-4" aria-hidden /> Sitzung beenden
            </Button>
          )}
          <div className="ml-auto flex gap-1" role="group" aria-label="Kameraansicht">
            {(['overview', 'robot'] as const).map((v) => (
              <Button key={v} size="sm" variant={view === v ? 'secondary' : 'ghost'} aria-pressed={view === v} onClick={() => setView(v)}>
                {v === 'overview' ? 'Übersicht' : 'Roboterkamera'}
              </Button>
            ))}
          </div>
        </div>
        <LiveImage session={current} view={view} />
        <p className="text-xs text-slate-600">
          Bewegung: geskripteter Referenz-Controller (dieselben Vorführungen, mit denen Dream-1 fine-getunt wurde), nicht
          Dream-1. Keine Credits. Bestanden = Teil liegt ruhig im Ziel und der Arm hat die Zelle nicht berührt.
        </p>
        {cells.isError && <p className="text-sm text-red-700">Zellen nicht abrufbar: {cells.error.message}</p>}
      </section>

      <aside className="min-w-0 space-y-5">
        <div>
          <h3 className="mb-2 text-sm font-semibold">Status</h3>
          {current ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant="secondary">{CELL_NAMES[current.cell] ?? current.cell}</Badge>
              <span className="tabular-nums text-slate-600">{current.sim_seconds?.toFixed(1) ?? '0.0'} s Simulation</span>
              {current.busy ? <Badge className="bg-amber-500 text-black">arbeitet: {current.busy}</Badge> : <Badge variant="outline">bereit</Badge>}
            </div>
          ) : (
            <p className="text-sm text-slate-600">Keine Sitzung aktiv.</p>
          )}
        </div>

        {cell && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Tasks</h3>
            <div className="mb-2 flex items-center gap-2">
              <Label htmlFor="cell-seed" className="text-xs text-slate-600">
                Szene (Seed)
              </Label>
              <Input id="cell-seed" className="h-8 w-24 tabular-nums" inputMode="numeric" value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ''))} />
            </div>
            <ul className="space-y-2">
              {cell.tasks.map((t) => (
                <li key={t.task} className="flex items-center gap-2 rounded-md bg-slate-50 p-2">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium">{TASK_NAMES[t.task] ?? t.task}</div>
                    <div className="truncate text-xs text-slate-600" title={t.prompt}>
                      Arm {t.arm === 'left' ? 'links' : 'rechts'} · „{t.prompt}“
                    </div>
                  </div>
                  <Button size="sm" disabled={!!current?.busy || task.isPending} onClick={() => task.mutate(t.task)}>
                    <Play className="size-3.5" aria-hidden /> Ausführen
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {current && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Steuerung</h3>
            <div className="flex flex-wrap gap-1.5">
              {(ACTIONS[current.cell] ?? []).map((a) => (
                <Button key={a.action} size="sm" variant="outline" disabled={act.isPending} onClick={() => act.mutate(a.action)}>
                  {a.label}
                </Button>
              ))}
            </div>
          </div>
        )}

        {result && (
          <div className={cn('rounded-md p-3 text-sm', result.passed ? 'bg-emerald-50 text-emerald-950' : 'bg-red-50 text-red-950')}>
            <b>{result.passed ? 'Bestanden' : 'Nicht bestanden'}</b>: {TASK_NAMES[result.task] ?? result.task}, Szene {result.seed} ({result.reason})
          </div>
        )}

        {sensors.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Sensoren</h3>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
              {sensors.map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-slate-600">{SENSOR_NAMES[key] ?? key}</dt>
                  <dd className="tabular-nums">{sensorText(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        {current && current.events.length > 0 && (
          <div>
            <h3 className="mb-2 text-sm font-semibold">Ereignisse</h3>
            <ol className="max-h-56 space-y-1 overflow-auto text-xs" data-testid="cell-events">
              {[...current.events].reverse().map((e, i) => (
                <li key={`${e.t}-${i}`} className={cn(e.gate === false && 'text-red-700', e.gate === true && 'text-emerald-800')}>
                  <span className="mr-2 tabular-nums text-slate-500">{e.t.toFixed(1)} s</span>
                  {e.text}
                </li>
              ))}
            </ol>
          </div>
        )}
      </aside>
    </div>
  )
}
