import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { toast } from 'sonner'
import { api } from '@/api/client'
import {
  DEVICE_TYPE_KIND,
  DEVICE_TYPE_LABELS,
  DeviceProtocolSchema,
  DeviceTypeSchema,
  PROTOCOL_LABELS,
  type Device,
  type DeviceConfig,
  type DeviceInput,
  type DeviceProtocol,
  type DeviceType,
} from '@/api/contract'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { deviceAddress, emptyConfig, formFromDevice, toDeviceInput, type DeviceForm } from './deviceForm'

type Editing = { mode: 'create' } | { mode: 'edit'; device: Device } | null

const KIND_LABELS = { sensor: 'Sensor', actuator: 'Aktor' } as const

function Field({ id, label, children, hint }: { id: string; label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-slate-600">{hint}</p>}
    </div>
  )
}

function Choice<T extends string>({ id, value, options, onChange }: { id: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as T)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function ProtocolFields({ config, passwordSet, onChange }: { config: DeviceConfig; passwordSet: boolean; onChange: (c: DeviceConfig) => void }) {
  if (config.protocol === 'virtual') {
    return <p className="text-sm text-slate-600">Ohne Verbindung – der Wert wird nur in DreamOrchestra simuliert.</p>
  }
  const credentials = (
    <div className="grid grid-cols-2 gap-3">
      <Field id="dev-user" label="Benutzer (optional)">
        <Input id="dev-user" autoComplete="off" value={config.username ?? ''} onChange={(e) => onChange({ ...config, username: e.target.value })} />
      </Field>
      <Field id="dev-password" label="Passwort (optional)">
        <Input
          id="dev-password"
          type="password"
          autoComplete="new-password"
          placeholder={passwordSet ? 'unverändert' : ''}
          value={config.password ?? ''}
          onChange={(e) => onChange({ ...config, password: e.target.value })}
        />
      </Field>
    </div>
  )
  if (config.protocol === 'mqtt') {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-[1fr_7rem] gap-3">
          <Field id="dev-host" label="Broker-Host">
            <Input id="dev-host" placeholder="broker.local" value={config.host} onChange={(e) => onChange({ ...config, host: e.target.value })} />
          </Field>
          <Field id="dev-port" label="Port">
            <Input id="dev-port" type="number" min={1} max={65535} value={config.port} onChange={(e) => onChange({ ...config, port: Number(e.target.value) })} />
          </Field>
        </div>
        <div className="grid grid-cols-[1fr_7rem] gap-3">
          <Field id="dev-topic" label="Topic">
            <Input id="dev-topic" placeholder="halle1/band/lichtschranke" value={config.topic} onChange={(e) => onChange({ ...config, topic: e.target.value })} />
          </Field>
          <Field id="dev-qos" label="QoS">
            <Choice id="dev-qos" value={String(config.qos)} options={['0', '1', '2'].map((q) => ({ value: q, label: q }))} onChange={(q) => onChange({ ...config, qos: Number(q) })} />
          </Field>
        </div>
        <div className="grid grid-cols-[1fr_7rem] items-end gap-3">
          <Field id="dev-payload" label="JSON-Feld im Payload (optional)" hint="leer = Payload ist der Wert selbst">
            <Input id="dev-payload" placeholder="value" value={config.payload_path ?? ''} onChange={(e) => onChange({ ...config, payload_path: e.target.value })} />
          </Field>
          <div className="flex items-center gap-2 pb-6">
            <Switch id="dev-tls" checked={config.tls} onCheckedChange={(tls) => onChange({ ...config, tls })} />
            <Label htmlFor="dev-tls">TLS</Label>
          </div>
        </div>
        {credentials}
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <Field id="dev-endpoint" label="Endpoint">
        <Input id="dev-endpoint" placeholder="opc.tcp://anlage:4840" value={config.endpoint} onChange={(e) => onChange({ ...config, endpoint: e.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field id="dev-node" label="Node-ID">
          <Input id="dev-node" placeholder="ns=2;s=Lichtschranke" value={config.node_id} onChange={(e) => onChange({ ...config, node_id: e.target.value })} />
        </Field>
        <Field id="dev-security" label="Sicherheitsmodus">
          <Choice
            id="dev-security"
            value={config.security_mode}
            options={[
              { value: 'None', label: 'None' },
              { value: 'Sign', label: 'Sign' },
              { value: 'SignAndEncrypt', label: 'SignAndEncrypt' },
            ]}
            onChange={(security_mode) => onChange({ ...config, security_mode })}
          />
        </Field>
      </div>
      {credentials}
    </div>
  )
}

function DeviceDialog({ editing, onClose }: { editing: Exclude<Editing, null>; onClose: () => void }) {
  const queryClient = useQueryClient()
  const initial = editing.mode === 'edit' ? editing.device : undefined
  const [form, setForm] = useState<DeviceForm>(() => formFromDevice(initial))
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (input: DeviceInput) => (initial ? api.updateDevice(initial.id, input) : api.createDevice(input)),
    onSuccess: (device) => {
      void queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success(`Gerät „${device.name}“ gespeichert`)
      onClose()
    },
    onError: (e) => setError(e.message),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const result = toDeviceInput(form)
    if (!result.ok) {
      setError(result.error)
      return
    }
    setError(null)
    save.mutate(result.input)
  }

  const setProtocol = (protocol: DeviceProtocol) =>
    setForm({ ...form, config: initial && initial.protocol === protocol ? formFromDevice(initial).config : emptyConfig(protocol) })
  const passwordSet = initial !== undefined && initial.protocol === form.config.protocol && 'password_set' in initial.config && initial.config.password_set === true

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={submit} className="space-y-3">
          <DialogHeader>
            <DialogTitle>{initial ? 'Gerät bearbeiten' : 'Neues Gerät'}</DialogTitle>
            <DialogDescription>
              {initial ? <>ID „{initial.id}“ bleibt fest, Workflows verweisen darauf.</> : 'Die ID wird aus dem Namen gebildet.'} Werte werden vorerst simuliert.
            </DialogDescription>
          </DialogHeader>
          <Field id="dev-name" label="Name">
            <Input id="dev-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="dev-type" label="Typ">
              <Choice
                id="dev-type"
                value={form.type}
                options={DeviceTypeSchema.options.map((t) => ({ value: t, label: `${DEVICE_TYPE_LABELS[t]} (${KIND_LABELS[DEVICE_TYPE_KIND[t]]})` }))}
                onChange={(type: DeviceType) => setForm({ ...form, type })}
              />
            </Field>
            <Field id="dev-protocol" label="Protokoll">
              <Choice
                id="dev-protocol"
                value={form.config.protocol}
                options={DeviceProtocolSchema.options.map((p) => ({ value: p, label: PROTOCOL_LABELS[p] }))}
                onChange={setProtocol}
              />
            </Field>
          </div>
          {form.type === 'number' && (
            <div className="grid grid-cols-3 gap-3">
              <Field id="dev-unit" label="Einheit">
                <Input id="dev-unit" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
              </Field>
              <Field id="dev-min" label="Min">
                <Input id="dev-min" type="number" value={form.min} onChange={(e) => setForm({ ...form, min: e.target.value })} />
              </Field>
              <Field id="dev-max" label="Max">
                <Input id="dev-max" type="number" value={form.max} onChange={(e) => setForm({ ...form, max: e.target.value })} />
              </Field>
            </div>
          )}
          <fieldset className="space-y-3 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">Verbindung ({PROTOCOL_LABELS[form.config.protocol]})</legend>
            <ProtocolFields config={form.config} passwordSet={passwordSet} onChange={(config) => setForm({ ...form, config })} />
          </fieldset>
          {error && (
            <p role="alert" className="text-sm font-medium text-red-700">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={save.isPending}>
              Speichern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeleteDialog({ device, onClose }: { device: Device; onClose: () => void }) {
  const queryClient = useQueryClient()
  const remove = useMutation({
    mutationFn: () => api.deleteDevice(device.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['devices'] })
      toast.success(`Gerät „${device.name}“ gelöscht`)
      onClose()
    },
    onError: (e) => {
      toast.error(`Löschen nicht möglich: ${e.message}`)
      onClose()
    },
  })
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Gerät löschen?</DialogTitle>
          <DialogDescription>
            „{device.name}“ ({device.id}) wird entfernt. Solange ein gespeicherter Workflow das Gerät verwendet, ist Löschen nicht möglich.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Abbrechen
          </Button>
          <Button variant="destructive" onClick={() => remove.mutate()} disabled={remove.isPending}>
            Löschen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function formatValue(d: Device): string {
  if (typeof d.value === 'number') return `${d.value}${d.unit ? ` ${d.unit}` : ''}`
  return d.value ? 'an' : 'aus'
}

export function DevicesView() {
  const devices = useQuery({ queryKey: ['devices'], queryFn: () => api.listDevices() })
  const [editing, setEditing] = useState<Editing>(null)
  const [deleting, setDeleting] = useState<Device | null>(null)

  return (
    <div className="mx-auto max-w-5xl space-y-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Geräte</h2>
          <p className="text-sm text-slate-600">Sensoren und Aktoren mit Protokoll (MQTT, OPC UA). Werte werden vorerst simuliert.</p>
        </div>
        <Button onClick={() => setEditing({ mode: 'create' })}>
          <Plus aria-hidden /> Neues Gerät
        </Button>
      </div>
      {devices.isError && (
        <p role="alert" className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          Geräte konnten nicht geladen werden: {devices.error.message}
        </p>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Art</TableHead>
            <TableHead>Typ</TableHead>
            <TableHead>Protokoll</TableHead>
            <TableHead>Adresse</TableHead>
            <TableHead>Wert</TableHead>
            <TableHead className="w-48" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(devices.data ?? []).map((d) => (
            <TableRow key={d.id} data-testid={`device-row-${d.id}`}>
              <TableCell>
                <div className="font-medium">{d.name}</div>
                <div className="font-mono text-xs text-slate-600">{d.id}</div>
              </TableCell>
              <TableCell>{KIND_LABELS[d.kind]}</TableCell>
              <TableCell>{DEVICE_TYPE_LABELS[d.type]}</TableCell>
              <TableCell>
                <Badge variant={d.protocol === 'virtual' ? 'secondary' : 'outline'}>{PROTOCOL_LABELS[d.protocol]}</Badge>
              </TableCell>
              <TableCell className="max-w-48 truncate font-mono text-xs" title={deviceAddress(d)}>
                {deviceAddress(d)}
              </TableCell>
              <TableCell className="text-sm">{formatValue(d)}</TableCell>
              <TableCell>
                <div className="flex justify-end gap-1.5">
                  <Button size="sm" variant="outline" onClick={() => setEditing({ mode: 'edit', device: d })} aria-label={`${d.name} bearbeiten`}>
                    <Pencil aria-hidden /> Bearbeiten
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setDeleting(d)} aria-label={`${d.name} löschen`}>
                    <Trash2 aria-hidden />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
          {devices.isSuccess && devices.data.length === 0 && (
            <TableRow>
              <TableCell colSpan={7} className="py-6 text-center text-sm text-slate-600">
                Noch keine Geräte angelegt.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {editing && <DeviceDialog key={editing.mode === 'edit' ? editing.device.id : 'new'} editing={editing} onClose={() => setEditing(null)} />}
      {deleting && <DeleteDialog device={deleting} onClose={() => setDeleting(null)} />}
    </div>
  )
}
