import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { SKILL_STATUS_SUGGESTIONS, SkillInputSchema, type Skill, type SkillInput } from '@/api/contract'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'

type Editing = { mode: 'create' } | { mode: 'edit'; skill: Skill } | null

function SkillDialog({ editing, onClose }: { editing: Editing; onClose: () => void }) {
  const queryClient = useQueryClient()
  const initial = editing?.mode === 'edit' ? editing.skill : null
  const [form, setForm] = useState<SkillInput>({
    name: initial?.name ?? '',
    description: initial?.description ?? '',
    status: initial?.status ?? 'Entwurf',
    fine_tuned_model: initial?.fine_tuned_model ?? null,
  })
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (input: SkillInput) => (initial ? api.updateSkill(initial.id, input) : api.createSkill(input)),
    onSuccess: (skill) => {
      void queryClient.invalidateQueries({ queryKey: ['skills'] })
      toast.success(`Skill „${skill.name}“ gespeichert`)
      onClose()
    },
    onError: (e) => setError(e.message),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const parsed = SkillInputSchema.safeParse({ ...form, fine_tuned_model: form.fine_tuned_model?.trim() || null })
    if (!parsed.success) {
      setError(parsed.error.issues.map((i) => i.message).join(', '))
      return
    }
    setError(null)
    save.mutate(parsed.data)
  }

  const statusOptions = [...new Set([...SKILL_STATUS_SUGGESTIONS, form.status ?? 'Entwurf'])]

  return (
    <Dialog open={editing !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-3">
          <DialogHeader>
            <DialogTitle>{initial ? 'Skill bearbeiten' : 'Neuer Skill'}</DialogTitle>
            <DialogDescription>Felder entsprechen der Tabelle „skills“ im Backend.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="skill-name">Name</Label>
            <Input id="skill-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="skill-desc">Beschreibung</Label>
            <Textarea id="skill-desc" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="skill-status">Status</Label>
              <Select value={form.status ?? 'Entwurf'} onValueChange={(status) => setForm({ ...form, status })}>
                <SelectTrigger id="skill-status" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {statusOptions.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="skill-model">Fine-getuntes Modell</Label>
              <Input id="skill-model" placeholder="leer = keins" value={form.fine_tuned_model ?? ''} onChange={(e) => setForm({ ...form, fine_tuned_model: e.target.value })} />
            </div>
          </div>
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

export function SkillsView() {
  const skills = useQuery({ queryKey: ['skills'], queryFn: () => api.listSkills() })
  const [editing, setEditing] = useState<Editing>(null)

  return (
    <div className="mx-auto max-w-5xl space-y-3 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">Skills</h2>
        <Button onClick={() => setEditing({ mode: 'create' })}>
          <Plus aria-hidden /> Neuer Skill
        </Button>
      </div>
      {skills.isError && (
        <p role="alert" className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
          Skills konnten nicht geladen werden: {skills.error.message}
        </p>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Beschreibung</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Modell</TableHead>
            <TableHead>Erstellt</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(skills.data ?? []).map((s) => (
            <TableRow key={s.id}>
              <TableCell className="font-medium">{s.name}</TableCell>
              <TableCell className="max-w-xs whitespace-normal text-sm text-slate-700">{s.description}</TableCell>
              <TableCell>
                <Badge variant={s.status === 'Bereit' ? 'default' : s.status === 'Fehler' ? 'destructive' : 'secondary'}>{s.status}</Badge>
              </TableCell>
              <TableCell className="font-mono text-xs">{s.fine_tuned_model ?? '–'}</TableCell>
              <TableCell className="text-xs">{s.created_at}</TableCell>
              <TableCell>
                <Button size="sm" variant="outline" onClick={() => setEditing({ mode: 'edit', skill: s })} aria-label={`${s.name} bearbeiten`}>
                  <Pencil aria-hidden /> Bearbeiten
                </Button>
              </TableCell>
            </TableRow>
          ))}
          {skills.isSuccess && skills.data.length === 0 && (
            <TableRow>
              <TableCell colSpan={6} className="py-6 text-center text-sm text-slate-600">
                Noch keine Skills angelegt.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {editing && <SkillDialog key={editing.mode === 'edit' ? editing.skill.id : 'new'} editing={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}
