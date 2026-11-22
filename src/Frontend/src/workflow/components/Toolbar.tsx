import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useReactFlow } from '@xyflow/react'
import { CheckCircle2, Copy, Download, FilePlus, FileUp, FolderOpen, Pause, Play, RotateCcw, Save, StepForward } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { api } from '@/api/client'
import type { WorkflowDocument } from '@/api/contract'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { isRunActive, useRunAction, useStartRun } from '@/run/useRun'
import { estimateCredits } from '../estimate'
import { toDocument } from '../flow'
import { parseWorkflowJson, serializeWorkflow } from '../io'
import { SAMPLES } from '../sample'
import { POLL_INTERVAL_OPTIONS, selectIsDirty, useEditor, useRunStore } from '../store'
import { validateWorkflow } from '../validate'
import { WorkflowsDialog } from './WorkflowsDialog'

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const fileName = (name: string) => `${name.trim().replace(/[^\p{L}\p{N}_-]+/gu, '_') || 'workflow'}.json`

export function Toolbar() {
  const { fitView } = useReactFlow()
  const name = useEditor((s) => s.name)
  const setName = useEditor((s) => s.setName)
  const setIssues = useEditor((s) => s.setIssues)
  const load = useEditor((s) => s.load)
  const workflowId = useEditor((s) => s.workflowId)
  const newWorkflow = useEditor((s) => s.newWorkflow)
  const dirty = useEditor(selectIsDirty)
  const [dialogOpen, setDialogOpen] = useState(false)
  const queryClient = useQueryClient()
  const confirmDiscard = () =>
    !selectIsDirty(useEditor.getState()) || window.confirm('Ungespeicherte Änderungen verwerfen?')
  const run = useRunStore((s) => s.run)
  const pollIntervalMs = useRunStore((s) => s.pollIntervalMs)
  const setPollInterval = useRunStore((s) => s.setPollInterval)
  const startRun = useStartRun()
  const pauseRun = useRunAction('pause')
  const resumeRun = useRunAction('resume')
  const stepRun = useRunAction('step')
  const fileInput = useRef<HTMLInputElement>(null)
  const active = isRunActive(run)
  const nodes = useEditor((s) => s.nodes)
  const edges = useEditor((s) => s.edges)
  const cells = useQuery({ queryKey: ['cells'], queryFn: () => api.listCells(), retry: false, staleTime: 300_000 })
  const freePrompts = useMemo(
    () => new Set((cells.data ?? []).flatMap((c) => c.tasks.map((t) => t.prompt.trim().toLowerCase()))),
    [cells.data],
  )
  const estimate = useMemo(() => estimateCredits(toDocument('', nodes, edges), freePrompts), [nodes, edges, freePrompts])
  const estimateText =
    estimate.minPerPass === estimate.maxPerPass ? `${estimate.maxPerPass}` : `${estimate.minPerPass}–${estimate.maxPerPass}`

  const check = () => {
    const doc = useEditor.getState().toDocument()
    const result = validateWorkflow(doc)
    setIssues(result.issues)
    return { doc, result }
  }

  // Zweite Stufe: das Backend prüft mit Geräten, Skills und API-Modus (z. B. Skill-Pflicht im Modus sim/real).
  const remoteCheck = useMutation({
    mutationFn: (doc: WorkflowDocument) => api.validateWorkflow(doc),
    onSuccess: (remote) => {
      setIssues(remote.issues)
      if (remote.valid) toast.success(`Prüfung bestanden (Backend) · ≈ ${remote.creditsEstimate} Credits`)
      else toast.error(`Backend: ${remote.issues.length} Problem(e) – am Block markiert`)
    },
    onError: (e) => toast.error(`Prüfung im Backend fehlgeschlagen: ${e.message}`),
  })

  const save = useMutation({
    mutationFn: () => {
      const doc = useEditor.getState().toDocument()
      return workflowId ? api.updateWorkflow(workflowId, doc) : api.createWorkflow(doc)
    },
    onSuccess: (wf) => {
      useEditor.getState().markSaved(wf.id)
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
      toast.success(`Workflow „${wf.name}“ gespeichert`)
    },
    onError: (e) => toast.error(`Speichern fehlgeschlagen: ${e.message}`),
  })

  const saveCopy = useMutation({
    mutationFn: () => {
      const doc = useEditor.getState().toDocument()
      return api.createWorkflow({ ...doc, name: `${doc.name} (Kopie)` })
    },
    onSuccess: (wf) => {
      setName(wf.name)
      useEditor.getState().markSaved(wf.id)
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
      toast.success(`Als „${wf.name}“ gespeichert`)
    },
    onError: (e) => toast.error(`Speichern fehlgeschlagen: ${e.message}`),
  })

  const onImport = async (file: File | undefined) => {
    if (!file) return
    const result = parseWorkflowJson(await file.text())
    if (!result.ok) {
      toast.error('Import fehlgeschlagen', { description: result.error, duration: 10_000 })
      return
    }
    if (!confirmDiscard()) return
    load(result.workflow)
    toast.success(`Workflow „${result.workflow.name}“ importiert – noch nicht gespeichert`)
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b bg-white px-3 py-2">
      <Label htmlFor="wf-name" className="sr-only">
        Name des Workflows
      </Label>
      <Input id="wf-name" value={name} onChange={(e) => setName(e.target.value)} className="h-8 w-48" />
      <span
        data-testid="save-state"
        className={cn(
          'rounded px-1.5 py-0.5 text-[11px] font-medium',
          workflowId === null || dirty ? 'bg-amber-100 text-amber-900' : 'bg-emerald-100 text-emerald-900',
        )}
      >
        {workflowId === null ? 'neu · nicht gespeichert' : dirty ? '● ungespeichert' : 'gespeichert'}
      </span>

      <Button size="sm" variant="outline" disabled={active} onClick={() => confirmDiscard() && newWorkflow()}>
        <FilePlus aria-hidden /> Neu
      </Button>
      <Button size="sm" variant="outline" onClick={() => setDialogOpen(true)}>
        <FolderOpen aria-hidden /> Öffnen …
      </Button>
      <Button size="sm" variant="outline" onClick={() => save.mutate()} disabled={save.isPending}>
        <Save aria-hidden /> Speichern
      </Button>
      <Button size="sm" variant="outline" onClick={() => saveCopy.mutate()} disabled={saveCopy.isPending}>
        <Copy aria-hidden /> Als Kopie
      </Button>
      <WorkflowsDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      <Separator orientation="vertical" className="mx-1 h-6" />

      <Button size="sm" variant="outline" disabled={remoteCheck.isPending} onClick={() => {
        const { doc, result } = check()
        if (!result.valid) {
          toast.error(`${result.issues.length} Problem(e) gefunden – am Block markiert`)
          return
        }
        remoteCheck.mutate(doc)
      }}>
        <CheckCircle2 aria-hidden /> Prüfen
      </Button>
      <Button size="sm" variant="outline" onClick={() => download(fileName(name), serializeWorkflow(useEditor.getState().toDocument()))}>
        <Download aria-hidden /> Exportieren
      </Button>
      <Button size="sm" variant="outline" onClick={() => fileInput.current?.click()}>
        <FileUp aria-hidden /> Importieren
      </Button>
      <input
        ref={fileInput}
        type="file"
        accept="application/json,.json"
        className="hidden"
        data-testid="import-input"
        onChange={(e) => {
          void onImport(e.target.files?.[0])
          e.target.value = ''
        }}
      />
      <Select
        value=""
        disabled={active}
        onValueChange={(id) => {
          const sample = SAMPLES.find((s) => s.id === id)
          if (sample && confirmDiscard()) {
            load(sample.doc)
            requestAnimationFrame(() => void fitView({ padding: 24, maxZoom: 1.1 }))
          }
        }}
      >
        <SelectTrigger size="sm" className="h-8 w-auto gap-1.5 border-0 shadow-none" aria-label="Beispiel laden" data-testid="sample-select">
          <RotateCcw aria-hidden className="size-4" />
          <SelectValue placeholder="Beispiel laden" />
        </SelectTrigger>
        <SelectContent>
          {SAMPLES.map((s) => (
            <SelectItem key={s.id} value={s.id}>
              {s.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="ml-auto flex items-center gap-2">
        <span
          data-testid="credit-estimate"
          className="rounded border border-slate-300 bg-slate-50 px-2 py-1 text-xs text-slate-800"
          title="Erreichbare Prompt-Blöcke × (1 + Wiederholungen). Bei Schleifen pro Durchlauf erneut."
        >
          ≈ {estimateText} Credits/Durchlauf{estimate.hasLoop ? ' · Schleife ×n' : ''}
        </span>
        <Label htmlFor="poll" className="text-xs text-slate-700">
          Abfrage
        </Label>
        <Select value={String(pollIntervalMs)} onValueChange={(v) => setPollInterval(Number(v))}>
          <SelectTrigger id="poll" size="sm" className="w-24">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {POLL_INTERVAL_OPTIONS.map((ms) => (
              <SelectItem key={ms} value={String(ms)}>
                {ms < 1000 ? `${ms} ms` : `${ms / 1000} s`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {run && run.status === 'running' && (
          <Button size="sm" variant="outline" onClick={() => pauseRun.mutate(run.id)} disabled={pauseRun.isPending}>
            <Pause aria-hidden /> Pause
          </Button>
        )}
        {run && run.status === 'paused' && (
          <>
            <Button size="sm" variant="outline" onClick={() => resumeRun.mutate(run.id)} disabled={resumeRun.isPending}>
              <Play aria-hidden /> Weiter
            </Button>
            <Button size="sm" variant="outline" onClick={() => stepRun.mutate(run.id)} disabled={stepRun.isPending}>
              <StepForward aria-hidden /> Einzelschritt
            </Button>
          </>
        )}
        <Button
          size="sm"
          className="bg-emerald-700 text-white hover:bg-emerald-800"
          disabled={active || startRun.isPending}
          onClick={() => {
            const { doc, result } = check()
            if (!result.valid) {
              toast.error(`Start nicht möglich: ${result.issues.length} Problem(e) – am Block markiert`)
              return
            }
            startRun.mutate({ workflowId, workflow: doc })
          }}
        >
          <Play aria-hidden /> Lauf starten
        </Button>
      </div>
    </div>
  )
}
