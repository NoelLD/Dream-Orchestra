import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Lightbulb, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { PROTOCOL_LABELS, type Device, type DeviceValue } from '@/api/contract'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { isRunActive } from '@/run/useRun'
import { useRunStore } from '@/workflow/store'
import { devicesInWorkflow, useWorkflowDeviceIds } from './workflowDevices'

const BUTTON_PULSE_MS = 1500

function ConveyorIcon({ running }: { running: boolean }) {
  return (
    <svg viewBox="0 0 24 12" className="h-4 w-8" aria-hidden>
      <rect x="1" y="2" width="22" height="8" rx="4" className={running ? 'fill-sky-200 stroke-sky-700' : 'fill-slate-100 stroke-slate-500'} strokeWidth="1.5" />
      {[6, 12, 18].map((cx) => (
        <circle key={cx} cx={cx} cy="6" r="1.6" className={cn(running ? 'fill-sky-700' : 'fill-slate-500')} />
      ))}
    </svg>
  )
}

function SensorControl({ device, onSet }: { device: Device; onSet: (value: DeviceValue) => void }) {
  const inputId = `device-${device.id}`
  if (device.type === 'switch') {
    return <Switch id={inputId} checked={device.value === true} onCheckedChange={(checked) => onSet(checked)} aria-label={device.name} />
  }
  if (device.type === 'button') {
    return (
      <Button
        size="xs"
        variant={device.value === true ? 'default' : 'outline'}
        onClick={() => {
          onSet(true)
          setTimeout(() => onSet(false), BUTTON_PULSE_MS)
        }}
      >
        {device.value === true ? 'ausgelöst' : 'Auslösen'}
      </Button>
    )
  }
  return (
    <Input
      id={inputId}
      aria-label={device.name}
      type="number"
      className="h-7 w-20"
      min={device.min ?? undefined}
      max={device.max ?? undefined}
      value={typeof device.value === 'number' ? device.value : 0}
      onChange={(e) => {
        const n = Number(e.target.value)
        if (Number.isFinite(n)) onSet(n)
      }}
    />
  )
}

function Unavailable({ device }: { device: Device }) {
  return (
    <span
      className="rounded bg-red-100 px-1.5 py-0.5 text-[11px] font-medium text-red-900"
      title={device.unavailable_reason ?? 'Wert gilt gerade nicht'}
      data-testid={`device-unavailable-${device.id}`}
    >
      nicht verfügbar
    </span>
  )
}

function ActuatorDisplay({ device }: { device: Device }) {
  const on = device.value === true
  if (device.type === 'lamp') {
    const red = device.id.includes('rot')
    return (
      <span className="flex items-center gap-1.5 text-xs font-medium">
        <Lightbulb aria-hidden className={cn('size-5', on ? (red ? 'fill-red-500 text-red-700' : 'fill-emerald-400 text-emerald-700') : 'text-slate-400')} />
        {on ? 'an' : 'aus'}
      </span>
    )
  }
  if (device.type === 'conveyor') {
    return (
      <span className="flex items-center gap-1.5 text-xs font-medium">
        <ConveyorIcon running={on} />
        {on ? 'läuft' : 'steht'}
      </span>
    )
  }
  if (device.type === 'machine') {
    return <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', on ? 'bg-amber-200 text-amber-950' : 'text-slate-600')}>{on ? 'Zyklus läuft' : 'bereit'}</span>
  }
  return <span className="text-xs font-medium">{String(device.value)}</span>
}

function DeviceName({ device, htmlFor }: { device: Device; htmlFor?: string }) {
  const Tag = htmlFor ? 'label' : 'span'
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <Tag htmlFor={htmlFor} className="truncate text-xs text-slate-900" title={`${device.name} (${device.id})`}>
        {device.name}
      </Tag>
      <span
        className="shrink-0 rounded border border-slate-300 px-1 text-[10px] leading-4 text-slate-600"
        title={device.simulated ? `${PROTOCOL_LABELS[device.protocol]} – Wert simuliert` : PROTOCOL_LABELS[device.protocol]}
        data-testid={`device-protocol-${device.id}`}
      >
        {PROTOCOL_LABELS[device.protocol]}
      </span>
    </span>
  )
}

export function DeviceBar() {
  const queryClient = useQueryClient()
  const run = useRunStore((s) => s.run)
  const pollIntervalMs = useRunStore((s) => s.pollIntervalMs)
  const devices = useQuery({
    queryKey: ['devices'],
    queryFn: () => api.listDevices(),
    refetchInterval: isRunActive(run) ? pollIntervalMs : 3000,
  })
  const setDevice = useMutation({
    mutationFn: ({ id, value }: { id: string; value: DeviceValue }) => api.setDevice(id, value),
    onSuccess: (device) => queryClient.setQueryData<Device[]>(['devices'], (old) => old?.map((d) => (d.id === device.id ? device : d))),
    onError: (e) => toast.error(`Gerät konnte nicht gesetzt werden: ${e.message}`),
  })

  const workflowIds = useWorkflowDeviceIds()
  const list = devicesInWorkflow(devices.data ?? [], workflowIds)
  const sensors = list.filter((d) => d.kind === 'sensor')
  const actuators = list.filter((d) => d.kind === 'actuator')

  return (
    <section aria-label="Geräteleiste" className="flex h-full flex-col overflow-y-auto">
      <div className="flex items-center gap-2 border-b px-3 py-1.5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Geräte</h2>
        <span className="text-[11px] text-slate-500">nur Geräte dieses Workflows · Werte simuliert</span>
        {devices.isFetching && <Loader2 className="size-3 animate-spin text-slate-400" aria-hidden />}
      </div>
      {devices.isError && <p role="alert" className="px-3 py-2 text-xs text-red-700">Geräte nicht erreichbar: {devices.error.message}</p>}
      {devices.isSuccess && list.length === 0 ? (
        <p className="px-3 py-3 text-xs text-slate-600">
          Noch keine Geräte im Workflow – im Block (Warte auf Sensor, Bedingung, Aktor setzen) auswählen. Geräte verwalten Sie im Tab „Geräte“.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-x-4 px-3 py-2">
          <div className="min-w-0">
            <h3 className="mb-1 text-[11px] font-semibold text-slate-700">Sensoren (bedienbar)</h3>
            <ul className="space-y-1.5">
              {sensors.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-2" data-testid={`device-${d.id}`}>
                  <DeviceName device={d} htmlFor={`device-${d.id}`} />
                  {d.available === false ? (
                    <Unavailable device={d} />
                  ) : (
                    <SensorControl device={d} onSet={(value) => setDevice.mutate({ id: d.id, value })} />
                  )}
                </li>
              ))}
            </ul>
          </div>
          <div className="min-w-0">
            <h3 className="mb-1 text-[11px] font-semibold text-slate-700">Aktoren (Anzeige)</h3>
            <ul className="space-y-1.5">
              {actuators.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-2" data-testid={`device-${d.id}`}>
                  <DeviceName device={d} />
                  {d.available === false ? <Unavailable device={d} /> : <ActuatorDisplay device={d} />}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  )
}
