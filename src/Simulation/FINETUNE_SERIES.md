# Fine-tune series yam-sim: what fine-tuning teaches Dream-1 here, measured

> Written Sa 21.11.2026 ~23:50, **before any fine-tune result exists**. Rules below are fixed from now on;
> anything decided later is marked as such in the write-up.

## Question

On the robot type `yam-sim` (Dream Labs MuJoCo scene, two YAM arms), does a 500-step fine-tune on 50 verified
scripted demonstrations change **success rate** and **cost per success** of `pick-banana` / `pick-apple`
against the base model, and which training choice matters: **Dream data mixed in or not** (`base_share`),
**one task or two** (dataset), **500 or 1000 steps**?

Why it matters for Dream-1 users: Dream Labs says fine-tuning teaches the body, not the task, and that high
reliability on specialist tasks is not guaranteed. A user paying 100–200 $ per job needs to know which knob is
worth it, measured on paired test scenes, not guessed.

## Cells (fine-tune jobs)

| Job | Dataset | Steps | lr_schedule | base_share | learning_rate | Price | Start |
|---|---|---|---|---|---|---|---|
| **R** (reference) | `pick-both-v2` (25 banana + 25 apple) | 500 | constant | 0.5 | default 1e-5 | 100 $ | now |
| **A** (own data only) | `pick-both-v2` | 500 | constant | **0.0** | default | 100 $ | now |
| **B** (one task) | **`pick-banana-v2`** (50 banana) | 500 | constant | 0.5 | default | 100 $ | now |
| **R1000** (optional) | R continued (`resume_from` R) on `pick-both-v2` | +500 | constant | (R's) | (R's) | 100 $ | only if R is finished by So 08:00 and the banana eval is running; dropped otherwise |

All four `constant` so that R can be resumed (Dream Labs: resume only at the constant schedule). Cosine is
therefore **not** tested; the tutorial recommends it for single-task specialization (named limitation).

## Factor inventory

| Factor | State | Value / levels |
|---|---|---|
| base_share | **Varied** | 0.5 (R) vs 0.0 (A); same dataset, steps, schedule |
| training data | **Varied** | `pick-both-v2` (R) vs `pick-banana-v2` (B). **Composite**: task mix *and* banana episodes 25 vs 50 change together; the comparison reads "specialised 50-banana data vs mixed 25+25", not "task mix alone" |
| steps | **Varied** | 500 (R) vs 1000 (R1000 = R + 500 resumed); same model lineage |
| lr_schedule | Fixed | constant (rendered in the job's `hyperparameters`, checked after queueing) |
| learning_rate, batch_size | Fixed | service defaults (record the job's `hyperparameters` verbatim) |
| embodiment | Fixed | `martinkaiser.bln/yam-sim` (14 dims, 3 cameras) |
| demo generator | Fixed | scripted IK expert (`mock_pickups`), randomized ±3 cm / light ±15 %, seeds ≥ 1000; both datasets 100 % on the replay check, `validate_dataset` OK |
| rendering | Fixed | 320×180, no shadows, run-time renderer (`SIM_RENDER_SHADOWS=0`) in data **and** evaluation |
| eval scenes | Fixed | seeds 0–19 (< 1000, never in training), same for every variant (paired) |
| eval prompt | Fixed | the training prompt: `pick up the banana and put it back down` / `pick up the apple and put it back down` |
| eval timeout, attempts | Fixed | 30 sim-s, 1 attempt, recovery off |
| success check | Fixed | object ≥ 8 cm above its start (MuJoCo), never the API reply |
| training seed of each job | **Uncontrolled** | one job per cell (one realized level): a cell difference can be training noise. Named limitation; no repeat jobs (cost) |
| base model the fine-tune starts from | Fixed by Dream, **recorded** | the job's `base_model` (create/get answer, stored); the reference variant uses it |
| Dream-1 sampling noise at inference | Measured | base `beta-1x` evaluated **twice** on the same seeds (noise floor) |

## Evaluation (after warm-up)

Warm-up first, all checkpoints in parallel: `tools/warmup.py <ckpt>...` (one paid call each, cap 60 min). A model
not `ready` after 60 min is reported "not evaluated" and left out of the request (decided now, not after a look).

Requests are fixed in `tools/eval_series.py` (checkpoints resolved by suffix, `--dry-run` prints them):

| Eval | Skill | Seeds | Variants (first = reference) | Trials | Wall time (measured 35 s median / 68 s mean per trial) |
|---|---|---|---|---|---|
| `banana` (primary) | pick-banana | 0–19 | beta-1x, beta-1x-rep, ft-R, ft-A, ft-B | 100 | ~1–2 h |
| `apple` (secondary) | pick-apple | 0–9 | beta-1x, ft-R, ft-A, ft-B | 40 | ~25–45 min |
| `steps` (optional) | pick-banana | 0–9 | beta-1x, ft-R, ft-R1000 | 30 | ~20–35 min |

Every variant gets the **training prompt** (`… and put it back down`), one attempt, 30 sim-s. The success check
measures **lifting ≥ 8 cm**, not the put-down: results are reported as "lift success".

`dream-1-beta-flash` is dropped from this series: the job's `base_model` (stored from the create/get answer) tells
which base the fine-tunes start from; the reference is that base. If it is not `dream-1-beta`, the reference
variant is switched to it before the eval starts (a pre-registered rule, not a look at results).

**Primary contrasts** (no ranking of knobs beyond these): ft-R vs base, ft-A vs ft-R (base_share), ft-B vs ft-R
(specialised data, composite). Exploratory, n = 20, one training job per cell.

**Analysis:** the `paired` block of each eval: only seeds where every variant finished without an infrastructure
`error` count (pairwise exclusion, listed in `excluded_seeds`); per variant successes with Wilson interval and,
against the reference, discordant pairs (`gained` / `lost`). An effect is claimed only if the intervals do not
overlap **and** gained − lost exceeds the beta-1x vs beta-1x-rep discordance; otherwise "not distinguishable at
this n". A variant needs ≥ 18 of 20 (banana) / 9 of 10 (apple) non-error trials, else "not evaluated".
Cost per success is **estimated inference cost** only; training cost (100 $ per job) is reported separately.
No re-running a variant because its number looks wrong; infrastructure reruns are stated in the write-up.

## Costs (estimates)

| Item | Cost |
|---|---|
| R, A, B (3 × 500 steps × 0.20 $) | 300 $ |
| R1000 (+500 steps) | 100 $ |
| Evals: banana 100 + apple 40 trials, ~9 calls each, 0.0014 $ base / 0.0028 $ ft | ~3 $ |
| Second eval (R vs R1000) | ~2 $ |
| **Total** | **~305 $** (R, A, B + evals); **~407 $** with the optional R1000 |

`SIM_BUDGET_USD` (inference guard) is raised from 10 to 20 for the evals.

## Timeline (Dream: ~7–8 h per 1000 steps → ~4 h per 500, assumption)

| When | What |
|---|---|
| Sa ~23:55 | queue R, A, B (script `tools/start_finetune_series.sh`, run by Martin) |
| Sa until 01:30 | check queued → running, hyperparameters as planned; parallel: CNC cell work |
| So ~04:00 | R, A, B expected finished (unattended) |
| So 08:00 | resume R → R1000 (~4 h, until ~12:00); warm up ft-R, ft-A, ft-B (one call each, up to 1 h) |
| So 09:00–11:30 | eval `banana`, then `apple` |
| So ~12:00–13:30 | warm-up R1000, eval 2 |
| So 14:00 | numbers into frontend Training tab / presentation; 15:00 ready |

Fallback: anything not finished by 13:30 is shown as "job running / not evaluated", never as a result.

## What this shows on the platform

The multi-container app (frontend → backend → simulation → Dream API) carries the whole loop: the Training tab
lists jobs per robot type with their knobs, the evaluation compares variants on paired scenes with intervals and
cost per success. The finding itself (whatever it is) is the user value: which fine-tune choice is worth 100 $.
