import { useQuery } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useId } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { api } from '@/api/client'
import type { ComparisonOperator, Device, DeviceValue } from '@/api/contract'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { BLOCKS, OPERATOR_LABELS } from '../blocks'
import { useEditor } from '../store'

const NONE = '__none__'

function Field({ label, children, hint }: { label: string; children: (id: string) => React.ReactNode; hint?: string }) {
  const id = useId()
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs font-medium text-slate-800">
        {label}
      </Label>
      {children(id)}
      {hint && <p className="text-[11px] text-slate-600">{hint}</p>}
    </div>
  )
}

function NumberInput({ id, value, onChange, min, step, allowEmpty }: { id: string; value: number | null; onChange: (v: number | null) => void; min?: number; step?: number; allowEmpty?: boolean }) {
  return (
    <Input
      id={id}
      type="number"
      min={min}
      step={step ?? 1}
      value={value ?? ''}
      placeholder={allowEmpty ? 'ohne Zeitlimit' : undefined}
      onChange={(e) => {
        if (e.target.value === '') return onChange(allowEmpty ? null : (min ?? 0))
        const n = Number(e.target.value)
        if (Number.isFinite(n)) onChange(n)
      }}
    />
  )
}

function DeviceSelect({ id, devices, value, onChange }: { id: string; devices: Device[]; value: string; onChange: (id: string) => void }) {
  return (
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? '' : v)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue placeholder="Gerät wählen" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>– Gerät wählen –</SelectItem>
        {devices.map((d) => (
          <SelectItem key={d.id} value={d.id}>
            {d.name} ({d.id})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function ValueInput({ id, device, value, onChange }: { id: string; device: Device | undefined; value: DeviceValue; onChange: (v: DeviceValue) => void }) {
  if (device?.type === 'number') {
    return <NumberInput id={id} value={typeof value === 'number' ? value : 0} onChange={(v) => onChange(v ?? 0)} />
  }
  return (
    <Select value={value === true ? 'true' : 'false'} onValueChange={(v) => onChange(v === 'true')}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="true">an / ausgelöst</SelectItem>
        <SelectItem value="false">aus</SelectItem>
      </SelectContent>
    </Select>
  )
}

function OperatorSelect({ id, value, onChange, numeric }: { id: string; value: ComparisonOperator; onChange: (v: ComparisonOperator) => void; numeric: boolean }) {
  const ops = (numeric ? Object.keys(OPERATOR_LABELS) : ['eq', 'neq']) as ComparisonOperator[]
  return (
    <Select value={value} onValueChange={(v) => onChange(v as ComparisonOperator)}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {ops.map((op) => (
          <SelectItem key={op} value={op}>
            {OPERATOR_LABELS[op]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function PropertiesPanel() {
  const node = useEditor((s) => s.nodes.find((n) => n.id === s.selectedNodeId))
  const updateData = useEditor((s) => s.updateData)
  const removeNode = useEditor((s) => s.removeNode)
  const globalIssues = useEditor(useShallow((s) => s.issues.filter((i) => i.nodeId === null)))
  const devicesQuery = useQuery({ queryKey: ['devices'], queryFn: () => api.listDevices() })
  const skillsQuery = useQuery({ queryKey: ['skills'], queryFn: () => api.listSkills() })
  const devices = devicesQuery.data ?? []
  const sensors = devices.filter((d) => d.kind === 'sensor')
  const actuators = devices.filter((d) => d.kind === 'actuator')

  return (
    <aside aria-label="Properties" className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-600">Properties</h2>

      {globalIssues.map((i) => (
        <p key={i.message} role="alert" className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs font-medium text-red-800">
          {i.message}
        </p>
      ))}

      {!node ? (
        <p className="text-sm text-slate-600">Select a block to edit it.</p>
      ) : (
        <div className="space-y-3" data-testid="properties">
          <div className="text-sm font-semibold text-slate-900">{BLOCKS[node.type].label}</div>

          <Field label="Bezeichnung">
            {(id) => <Input id={id} value={node.data.label ?? ''} placeholder={BLOCKS[node.type].label} onChange={(e) => updateData(node.id, { label: e.target.value })} />}
          </Field>

          {node.type === 'prompt' && (
            <>
              <Field label="Prompt an Dream-1">
                {(id) => <Textarea id={id} rows={3} value={node.data.prompt} onChange={(e) => updateData<'prompt'>(node.id, { prompt: e.target.value })} />}
              </Field>
              <Field label="Skill / Modell" hint={skillsQuery.isError ? 'Skills konnten nicht geladen werden.' : undefined}>
                {(id) => (
                  <Select value={node.data.skillId === null ? NONE : String(node.data.skillId)} onValueChange={(v) => updateData<'prompt'>(node.id, { skillId: v === NONE ? null : Number(v) })}>
                    <SelectTrigger id={id} className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>Dream-1 Basismodell</SelectItem>
                      {(skillsQuery.data ?? []).map((s) => (
                        <SelectItem key={s.id} value={String(s.id)}>
                          {s.name} ({s.status})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Zeitlimit (s)">{(id) => <NumberInput id={id} min={1} value={node.data.timeoutS} onChange={(v) => updateData<'prompt'>(node.id, { timeoutS: Math.max(1, v ?? 1) })} />}</Field>
                <Field label="Wiederholungen">{(id) => <NumberInput id={id} min={0} value={node.data.retries} onChange={(v) => updateData<'prompt'>(node.id, { retries: Math.max(0, Math.round(v ?? 0)) })} />}</Field>
              </div>
            </>
          )}

          {(node.type === 'waitSensor' || node.type === 'condition') && (() => {
            const device = devices.find((d) => d.id === node.data.deviceId)
            const numeric = device?.type === 'number'
            return (
              <>
                <Field label="Sensor">{(id) => <DeviceSelect id={id} devices={sensors} value={node.data.deviceId} onChange={(deviceId) => updateData(node.id, { deviceId })} />}</Field>
                <div className="grid grid-cols-[80px_1fr] gap-2">
                  <Field label="Vergleich">{(id) => <OperatorSelect id={id} numeric={numeric} value={node.data.operator} onChange={(operator) => updateData(node.id, { operator })} />}</Field>
                  <Field label="Wert">{(id) => <ValueInput id={id} device={device} value={node.data.value} onChange={(value) => updateData(node.id, { value })} />}</Field>
                </div>
                {node.type === 'waitSensor' && (
                  <Field label="Zeitlimit (s)" hint="Leer = ohne Zeitlimit. Danach Ausgang „Fehler“.">
                    {(id) => <NumberInput id={id} min={1} allowEmpty value={node.data.timeoutS} onChange={(v) => updateData<'waitSensor'>(node.id, { timeoutS: v === null ? null : Math.max(1, v) })} />}
                  </Field>
                )}
              </>
            )
          })()}

          {node.type === 'setActuator' && (
            <>
              <Field label="Aktor">{(id) => <DeviceSelect id={id} devices={actuators} value={node.data.deviceId} onChange={(deviceId) => updateData<'setActuator'>(node.id, { deviceId })} />}</Field>
              <Field label="Wert">{(id) => <ValueInput id={id} device={devices.find((d) => d.id === node.data.deviceId)} value={node.data.value} onChange={(value) => updateData<'setActuator'>(node.id, { value })} />}</Field>
            </>
          )}

          {node.type === 'wait' && (
            <Field label="Dauer (s)">{(id) => <NumberInput id={id} min={0.1} step={0.5} value={node.data.seconds} onChange={(v) => updateData<'wait'>(node.id, { seconds: Math.max(0.1, v ?? 1) })} />}</Field>
          )}

          <Button variant="outline" size="sm" className="text-red-700" onClick={() => removeNode(node.id)}>
            <Trash2 aria-hidden /> Block löschen
          </Button>
        </div>
      )}
    </aside>
  )
}
