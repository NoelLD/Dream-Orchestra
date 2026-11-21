import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { isRunActive } from '@/run/useRun'
import { selectIsDirty, useEditor, useRunStore } from '../store'

const formatDate = (iso: string) => {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })
}

/** Gespeicherte Workflows öffnen und löschen. */
export function WorkflowsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const queryClient = useQueryClient()
  const workflowId = useEditor((s) => s.workflowId)
  const dirty = useEditor(selectIsDirty)
  const runActive = isRunActive(useRunStore((s) => s.run))
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const list = useQuery({ queryKey: ['workflows'], queryFn: () => api.listWorkflows(), enabled: open })

  const openWorkflow = useMutation({
    mutationFn: (id: string) => api.getWorkflow(id),
    onSuccess: (wf) => {
      useEditor.getState().load(wf, wf.id)
      onOpenChange(false)
      toast.success(`Workflow „${wf.name}“ geöffnet`)
    },
    onError: (e) => toast.error(`Öffnen fehlgeschlagen: ${e.message}`),
  })

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteWorkflow(id).then(() => id),
    onSuccess: (id) => {
      if (useEditor.getState().workflowId === id) useEditor.getState().detach()
      setConfirmDelete(null)
      void queryClient.invalidateQueries({ queryKey: ['workflows'] })
      toast.success('Workflow gelöscht')
    },
    onError: (e) => toast.error(`Löschen fehlgeschlagen: ${e.message}`),
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setConfirmDelete(null)
        onOpenChange(next)
      }}
    >
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Workflows</DialogTitle>
          <DialogDescription>Gespeicherte Abläufe öffnen oder löschen. Zuletzt geänderte stehen oben.</DialogDescription>
        </DialogHeader>

        {dirty && (
          <p role="alert" className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Der aktuelle Workflow hat ungespeicherte Änderungen. Beim Öffnen eines anderen gehen sie verloren.
          </p>
        )}
        {runActive && (
          <p className="rounded border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-800">
            Während ein Lauf aktiv ist, kann kein anderer Workflow geöffnet werden.
          </p>
        )}
        {list.isError && (
          <p role="alert" className="text-sm text-red-700">
            Workflows konnten nicht geladen werden: {list.error.message}
          </p>
        )}

        <div className="max-h-[50vh] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="w-36">Geändert</TableHead>
                <TableHead className="w-64" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(list.data ?? []).map((wf) => (
                <TableRow key={wf.id} data-testid={`workflow-row-${wf.id}`}>
                  <TableCell className="font-medium">
                    {wf.name}
                    {wf.id === workflowId && (
                      <Badge variant="secondary" className="ml-2">
                        geöffnet
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-slate-700">{formatDate(wf.updated_at)}</TableCell>
                  <TableCell className="space-x-2 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={runActive || openWorkflow.isPending}
                      onClick={() => openWorkflow.mutate(wf.id)}
                      aria-label={`${wf.name} öffnen`}
                    >
                      <FolderOpen aria-hidden /> Öffnen
                    </Button>
                    <Button
                      size="sm"
                      variant={confirmDelete === wf.id ? 'destructive' : 'outline'}
                      className={confirmDelete === wf.id ? undefined : 'text-red-700'}
                      disabled={remove.isPending}
                      onClick={() => (confirmDelete === wf.id ? remove.mutate(wf.id) : setConfirmDelete(wf.id))}
                      aria-label={confirmDelete === wf.id ? `${wf.name} wirklich löschen` : `${wf.name} löschen`}
                    >
                      <Trash2 aria-hidden /> {confirmDelete === wf.id ? 'Wirklich löschen?' : 'Löschen'}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {list.isSuccess && list.data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="py-6 text-center text-sm text-slate-600">
                    Noch keine Workflows gespeichert.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </DialogContent>
    </Dialog>
  )
}
