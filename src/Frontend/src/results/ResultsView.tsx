import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { api } from '@/api/client'
import { OUTCOME_BUCKETS, type CellResults, type CheckpointPolicy, type OutcomeBucket, type ResultModel } from '@/api/contract'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'

const OUTCOME: Record<OutcomeBucket, { label: string; className: string }> = {
  success: { label: 'success', className: 'bg-blue-600' },
  dropped: { label: 'dropped', className: 'bg-orange-500' },
  not_released: { label: 'placed, not released', className: 'bg-violet-600' },
  no_grasp: { label: 'not grasped', className: 'bg-slate-300' },
  action_error: { label: 'invalid command (gripper > 1)', className: 'bg-amber-500 bg-[repeating-linear-gradient(45deg,transparent_0_3px,rgba(255,255,255,.55)_3px_6px)]' },
}
const JOB_STATUS: Record<string, string> = { succeeded: 'done', running: 'training', queued: 'queued', failed: 'failed' }
const usd = (v: number) => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const pct = (v: number) => `${Math.round(v * 100)} %`

function RateBar({ model, base, n }: { model: ResultModel; base: ResultModel | undefined; n: number }) {
  return (
    <div className="relative h-4 w-48 rounded bg-slate-200" title={`${pct(model.k / n)} (95 % ${pct(model.lo)}–${pct(model.hi)})`}>
      <div className="absolute top-1.5 h-1 rounded bg-blue-300" style={{ left: `${model.lo * 100}%`, width: `${(model.hi - model.lo) * 100}%` }} />
      {base && <div className="absolute top-0 h-4 w-0.5 bg-slate-500" style={{ left: `${(base.k / n) * 100}%` }} />}
      <div className="absolute top-0.5 h-3 w-1 -translate-x-1/2 rounded bg-blue-600" style={{ left: `${(model.k / n) * 100}%` }} />
    </div>
  )
}

function SceneGrid({ data }: { data: CellResults }) {
  const per = data.tasks.length > 0 ? Math.round((data.models[0]?.scenes.length ?? 0) / data.tasks.length) : 0
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-[200px_1fr] gap-3 text-xs text-slate-600">
        <span />
        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${data.tasks.length}, minmax(0, 1fr))` }}>
          {data.tasks.map((t) => (
            <span key={t}>{data.task_names[t] ?? t}</span>
          ))}
        </div>
      </div>
      {data.models.map((m) => (
        <div key={m.label} className="grid grid-cols-[200px_1fr] items-center gap-3">
          <span className="truncate text-sm">{m.name}</span>
          <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${data.tasks.length}, minmax(0, 1fr))` }}>
            {data.tasks.map((t, ti) => (
              <div key={t} className="grid gap-0.5" style={{ gridTemplateColumns: `repeat(${per}, minmax(0, 1fr))` }}>
                {m.scenes.slice(ti * per, (ti + 1) * per).map(([bucket, contact, raw], i) => (
                  <span
                    key={i}
                    className={cn('relative aspect-square rounded-sm', OUTCOME[bucket as OutcomeBucket]?.className ?? 'bg-slate-300')}
                    title={`${data.task_names[t] ?? t}, scene ${i}: ${OUTCOME[bucket as OutcomeBucket]?.label ?? raw}${contact ? ', contact' : ''}`}
                  >
                    {contact && <span className="absolute top-0.5 right-0.5 size-1 rounded-full bg-slate-900" />}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-x-4 gap-y-1 pt-2 text-xs text-slate-600">
        {OUTCOME_BUCKETS.map((b) => (
          <span key={b} className="inline-flex items-center gap-1.5">
            <span className={cn('size-3 rounded-sm', OUTCOME[b].className)} /> {OUTCOME[b].label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="relative size-3 rounded-sm bg-slate-300">
            <span className="absolute top-0.5 right-0.5 size-1 rounded-full bg-slate-900" />
          </span>
          dot = arm touched the cell
        </span>
      </div>
    </div>
  )
}

const score = (k: number | null | undefined, n: number) => (k == null ? '–' : `${k}/${n}`)

/** Wie die Messung das Verhalten steuert: je Aufgabe, wer ausführt und welcher Fine-Tune freigegeben ist */
export function PolicyTable({ policy, fts }: { policy: CheckpointPolicy; fts: ResultModel[] }) {
  const cellRow = policy.rows.find((r) => r.scope === 'cell')
  return (
    <section>
      <h3 className="mb-1 font-semibold">Which model runs which task?</h3>
      <p className="mb-3 max-w-[80ch] text-sm text-slate-600">
        We trained several fine-tunes and tested each on the same scenes. Only the best one is approved, and only inside the
        cells, because it makes the robot forget other skills.
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Task</TableHead>
            <TableHead>Runs today</TableHead>
            <TableHead className="text-right">Base model</TableHead>
            <TableHead>Approved fine-tune</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {policy.rows.map((r) => {
            const outside = r.scope === 'outside'
            return (
              <TableRow key={r.skill} className={cn(outside && 'bg-amber-50')}>
                <TableCell className="font-medium">{r.name}</TableCell>
                <TableCell title={r.controller.reason}>
                  {r.controller.name} <span className="tabular-nums">{score(r.controller.k, r.n)}</span>
                </TableCell>
                <TableCell className="text-right tabular-nums">{score(r.base?.k, r.n)}</TableCell>
                <TableCell className="whitespace-normal">
                  {outside ? (
                    <span className="text-red-700">none – the cell fine-tune {r.rejected[0]?.reason ?? 'is excluded'}</span>
                  ) : (
                    <>
                      {r.checkpoint?.name ?? '–'} <span className="tabular-nums">{score(r.checkpoint?.k, r.n)}</span>
                    </>
                  )}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      {cellRow && cellRow.rejected.length > 0 && (
        <div className="mt-3 text-sm">
          <h4 className="mb-1 font-medium">Other fine-tunes, not approved (score on all 40 scenes; approved c500: {fts.find((m) => m.label === 'ft-main')?.k ?? '–'}/40)</h4>
          <ul className="space-y-0.5 text-slate-700">
            {cellRow.rejected.map((x) => (
              <li key={x.label}>
                {x.name}: <span className="tabular-nums">{x.total}/40</span> – {x.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

export function ResultsView() {
  const results = useQuery({ queryKey: ['cell-results'], queryFn: () => api.getCellResults(), refetchInterval: 60_000 })
  const policy = useQuery({ queryKey: ['checkpoint-policy'], queryFn: () => api.getCheckpointPolicy(), refetchInterval: 60_000 })
  const robots = useQuery({ queryKey: ['robots'], queryFn: () => api.listRobots(), refetchInterval: 60_000 })
  const data = results.data
  const robot = robots.data?.find((r) => r.name === 'yam-sim') ?? robots.data?.[0]

  if (results.isError) {
    return <p className="p-6 text-sm text-red-700">Results unavailable: {results.error.message}</p>
  }
  if (!data) return <p className="p-6 text-sm text-slate-600">Loading results …</p>

  const n = data.models[0]?.scenes.length ?? 0
  const base = data.models.find((m) => m.label === data.base)
  const isBase = (m: ResultModel) => m.label.startsWith('beta')
  const fts = data.models.filter((m) => m.win !== undefined && m.prereg && !isBase(m))
  const spentJobs = data.spend.jobs.reduce((a, j) => a + j.usd, 0)
  const spentEvals = Object.values(data.spend.evals).reduce((a, v) => a + v, 0)

  return (
    <div className="mx-auto max-w-[1200px] space-y-10 p-6">
      <section className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-3">
          <h2 className="text-lg font-semibold">Robot “yam-sim”: is a fine-tune worth it for these cells?</h2>
          {data.public_url && (
            <a href={data.public_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-blue-700 underline underline-offset-2">
              Shareable report <ExternalLink className="size-3.5" aria-hidden />
            </a>
          )}
          <span className="ml-auto text-xs text-slate-500">Updated {data.generated_at.replace('T', ' ').slice(0, 16)}</span>
        </div>
        <p className="max-w-[75ch] text-sm text-slate-600">
          Workflows use the skills of a robot type. If the base model is not good enough in a new cell, the robot learns the
          cell from checked demonstrations. Only what measures better here gets approved.
        </p>
        <p className="max-w-[75ch] text-slate-700">
          The same {n} test scenes for every model, never seen in training. The base model solves <b>{base?.k ?? '–'} of {n}</b>,
          the fine-tunes <b>{fts.map((m) => m.k).join(', ')} of {n}</b> ({fts.length} trainings). Compared scene by scene
          (McNemar test).
        </p>
      </section>

      {policy.data && <PolicyTable policy={policy.data} fts={data.models} />}
      {policy.isError && <p className="text-sm text-red-700">Decision table unavailable: {policy.error.message}</p>}

      <section>
        <h3 className="mb-2 font-semibold">Success on {n} scenes</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Model</TableHead>
              <TableHead className="text-right">Success</TableHead>
              <TableHead>Rate, 95 % interval</TableHead>
              <TableHead className="text-right">won : lost vs. base</TableHead>
              <TableHead className="text-right">McNemar p</TableHead>
              <TableHead className="text-right">Median time</TableHead>
              <TableHead className="text-right">Solved within 30 s</TableHead>
              <TableHead className="text-right">Runs with contact</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.models.map((m) => (
              <TableRow key={m.label}>
                <TableCell>
                  <div className="font-medium">
                    {m.name} {!m.prereg && <Badge variant="outline">explorativ</Badge>}
                  </div>
                  <div className="text-xs text-slate-600">{m.what}</div>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {m.k}/{n}
                </TableCell>
                <TableCell>
                  <RateBar model={m} base={base} n={n} />
                </TableCell>
                <TableCell className="text-right tabular-nums">{m.win !== undefined ? `${m.win} : ${m.loss}` : '–'}</TableCell>
                <TableCell className={cn('text-right tabular-nums', m.p !== undefined && m.p < 0.05 && 'font-semibold')}>{m.p?.toFixed(3) ?? '–'}</TableCell>
                <TableCell className="text-right tabular-nums">{m.t_median != null ? `${m.t_median.toFixed(1)} s` : '–'}</TableCell>
                <TableCell className="text-right tabular-nums">{m.within30 !== undefined ? `${m.within30}/${n}` : '–'}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {m.contact}/{n}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <p className="mt-2 max-w-[80ch] text-xs text-slate-600">
          A variant only counts as better or worse if the gap is larger than between two identical trainings. Time = sim seconds
          until the part is placed, median over solved scenes only. “Solved within 30 s” combines speed and success over all
          scenes. Runs with contact go up with the fine-tune, so we make no safety claim. Everything is simulation.
        </p>
      </section>

      <section>
        <h3 className="mb-1 font-semibold">Every scene compared</h3>
        <p className="mb-3 text-sm text-slate-600">One square per scene, same position in every row. Hover to see the outcome.</p>
        <SceneGrid data={data} />
      </section>

      <section className="grid grid-cols-2 gap-8">
        <div>
          <h3 className="mb-2 font-semibold">Fine-tune jobs {robot && <span className="font-normal text-slate-600">({robot.name})</span>}</h3>
          {robot?.fine_tuned_model && (
            <p className="mb-2 text-sm">
              Active checkpoint: <code className="rounded bg-slate-100 px-1 text-xs">{robot.fine_tuned_model}</code>
            </p>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Job</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Steps</TableHead>
                <TableHead className="text-right">US$</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(robot?.finetune_jobs ?? []).map((j) => (
                <TableRow key={j.job_id}>
                  <TableCell className="font-mono text-xs">{j.suffix}</TableCell>
                  <TableCell>
                    <Badge variant={j.status === 'succeeded' ? 'secondary' : 'outline'}>{JOB_STATUS[j.status] ?? j.status}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{j.steps}</TableCell>
                  <TableCell className="text-right tabular-nums">{usd(j.price_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {robots.isError && <p className="mt-2 text-sm text-red-700">Robots unavailable: {robots.error.message}</p>}
        </div>
        <div className="space-y-6">
          <div>
            <h3 className="mb-2 font-semibold">Spending</h3>
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
              <dt className="text-slate-600">Fine-tunes (done and running)</dt>
              <dd className="text-right tabular-nums">{usd(spentJobs)} $</dd>
              <dt className="text-slate-600">Evaluation runs (Dream calls)</dt>
              <dd className="text-right tabular-nums">{usd(spentEvals)} $</dd>
              <dt className="font-semibold">Committed</dt>
              <dd className="text-right font-semibold tabular-nums">
                {usd(spentJobs + spentEvals)} of {usd(data.spend.credit)} $
              </dd>
            </dl>
          </div>
          <div>
            <h3 className="mb-2 font-semibold">Measurement plan today</h3>
            <ul className="space-y-1 text-sm">
              {data.queue.map((q) => (
                <li key={q.label} className="flex gap-3">
                  <Badge variant={q.done ? 'secondary' : 'outline'} className="w-16 justify-center">
                    {q.done ? 'done' : 'open'}
                  </Badge>
                  <span className={cn('flex-1', q.done && 'text-slate-500')}>{q.name}</span>
                  {!q.done && <span className="tabular-nums text-slate-500">{q.eta}</span>}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </div>
  )
}
