# Transfer test – pre-registered 22.11.2026, 11:40 (before any model run on this task)

**Question:** Does the cell fine-tune also help on a similar task that was never in its training data?

**Task `cnc_return`** (new, `TRANSFER_TASKS` in `app/cnc_expert.py`): CNC cell, left arm, the metal block starts on
the machine tray and must end on the grey stand. Reverse of the trained `cnc_load` (same cell, part and arm; new
motion, new prompt: "put the metal block from the machine tray on the grey stand"). Success check as in the main
evaluation (part resting on the stand within 3 cm, released, stable 0.4 s).

**Reference:** scripted expert 20/20 on seeds 0–19, 0 contacts (`xfer-expert.jsonl`), so the task is solvable.

**Runs:** base `beta` (`xfer-beta`) and main fine-tune c500 (`xfer-ft-main`); seeds 0–19, rate 20, grip tolerance
0.05, first attempt counts, action errors (invalid gripper command) count as failures, infrastructure errors retried
once and excluded. Same protocol as `report_corrected.md`. Only these two models; no other checkpoint is added afterwards.

**Decision rules (paired, same 20 scenes, exact McNemar):**
- p < 0.05 in favour of the fine-tune → "transfer shown on this task".
- fine-tune ahead by ≥ 3 scenes but p ≥ 0.05 → "hint of transfer, not shown".
- otherwise → "transfer not shown" (not: "no transfer").
- fine-tune behind by ≥ 3 scenes → "fine-tune hurts on this similar task".
One task, 20 scenes: only large effects are detectable. Never generalise to "flexible on similar tasks" from one task.
