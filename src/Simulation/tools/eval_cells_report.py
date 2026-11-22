"""Report for eval_cells.py: per model success with Wilson 95 % intervals, contacts, outcomes, cost, paired flips.

    docker compose run --rm --no-deps simulation python /app/tools/eval_cells_report.py expert beta-r20 <ft-label>
Labels are file names in /data/evals/cells (without .jsonl). The first non-expert label is the "before",
the last one the "after" for the paired comparison (same task x seed in both). Writes report.md next to them.
Honesty rules: simulation, small n; primary test = exact McNemar on the paired scenes, p < 0.05 (pre-registered);
the unpaired Wilson intervals are descriptive only. Scoring: see MODE / load().
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

OUT = config.DATA_DIR / "evals/cells"
TASKS = ["sort_round", "sort_cube", "cnc_load", "cnc_unload"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def fmt(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({lo:.0%}–{hi:.0%})"


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact binomial test on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


ALL: dict[str, list] = {}


MODE = "first"  # first | legacy (set by --legacy)


def is_action_error(r: dict) -> bool:
    """The vendor check rejected the model's own chunk (old files logged it as 'error')."""
    e = r.get("error") or ""
    return r["outcome"] == "action_error" or (r["outcome"] == "error" and "No rows executed" in e)


def load(label: str) -> dict:
    """Scored episodes per task x seed. Every line (errors too) stays in ALL for cost.

    first (primary, corrected 22.11. 10:00 after Codex review): the first attempt that is not an infrastructure
    error; an action error (invalid model output) counts as a failure and is never replaced by a retry.
    legacy (as pre-registered, biased): the latest attempt that is not an error of any kind."""
    rows = [json.loads(x) for x in (OUT / f"{label}.jsonl").read_text().splitlines() if x.strip()]
    ALL[label] = rows
    scored = {}
    for r in rows:
        key = (r["task"], r["seed"])
        if MODE == "legacy":
            if r["outcome"] != "error":
                scored[key] = r
        elif key not in scored and (r["outcome"] != "error" or is_action_error(r)):
            if is_action_error(r):
                r = r | {"success": False, "clean_success": False, "outcome": "action_error", "done_s": None}
            scored[key] = r
    return scored


def median(xs: list) -> float:
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def dataset_row_step() -> float | None:
    """Mean joint change per frame in the training data (10 fps): the reference for a model chunk's row_step."""
    try:
        import numpy as np
        import pyarrow.parquet as pq
    except ImportError:
        return None
    files = sorted((config.DATASETS_DIR / "cells-v1").glob("ep-*/data/chunk-000/*.parquet"))[:40]
    steps = []
    for f in files:
        a = np.array(pq.read_table(f, columns=["action"]).column("action").to_pylist())
        joints = np.c_[a[:, 0:6], a[:, 7:13]]
        moving = np.abs(np.diff(joints, axis=0)).mean(axis=1)
        steps.extend(moving[moving > 1e-4])  # only frames where the arm moves (a chunk is mostly motion)
    return float(np.mean(steps)) if steps else None


def section(label: str, data: dict) -> list[str]:
    rows = list(data.values())
    n = len(rows)
    k = sum(r["success"] for r in rows)
    clean = sum(r["clean_success"] for r in rows)
    with_contact = sum(r["contact_steps"] > 0 for r in rows)
    cost = sum(r.get("cost_usd", 0.0) for r in ALL.get(label, rows))  # incl. error attempts
    all_rows = ALL.get(label, [])
    errors = sum(r["outcome"] == "error" and not is_action_error(r) for r in all_rows)
    action_errors = sum(is_action_error(r) for r in all_rows)
    done = [r["done_s"] for r in rows if r.get("done_s")]
    out = [f"### {label}  ({rows[0]['model'] if rows else ''})", "",
           f"- Success: **{fmt(k, n)}**; collision-free success: **{fmt(clean, n)}**",
           f"- Runs with arm–cell contact: {fmt(with_contact, n)}",
           f"- Median time to done: {median(done):.1f} s" if done else "- Median time to done: –",
           f"- Cost (tariff estimate of answered calls, incl. {errors} infrastructure-error attempts (retried) and "
           f"{action_errors} action-error attempts; calibration, warm-up and training not included): {cost:.3f} $"
           + (f", {cost / k:.4f} $ per success" if k else ", no success")]
    clipped = [r for r in rows if r.get("grip_tol", 0.05) > 0.05]
    if clipped:
        out.append(f"- Gripper clipping up to {max(r['grip_tol'] for r in clipped):g} outside 0..1 (exploratory "
                   f"amendment): {sum(r.get('grip_clipped', 0) for r in clipped)} rows clipped beyond the vendor's 0.05")
    if label != "expert" and n < 40:
        missing = [f"{t} {s}" for t in TASKS for s in range(10) if (t, s) not in data]
        out.append(f"- Not scored (no attempt yet / only infrastructure errors): {n} of 40 scored; missing: "
                   + ", ".join(missing))
    out.append("")
    out += ["| Task | Success | Collision-free | Contact runs | Outcomes |", "|---|---|---|---|---|"]
    for t in TASKS:
        rs = [r for r in rows if r["task"] == t]
        if not rs:
            continue
        outcomes = {}
        for r in rs:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        out.append(f"| {t} | {fmt(sum(r['success'] for r in rs), len(rs))} | "
                   f"{fmt(sum(r['clean_success'] for r in rs), len(rs))} | "
                   f"{sum(r['contact_steps'] > 0 for r in rs)} | "
                   + ", ".join(f"{o} {c}" for o, c in sorted(outcomes.items())) + " |")
    motion = [r for r in rows if "speed_mean" in r]  # logged since 22.11. 10:15 (exploratory, not pre-registered)
    if motion:
        rel = [r["release_drop_m"] for r in motion if r.get("release_drop_m") is not None]
        fall = [r["release_fall_mps"] for r in motion if r.get("release_fall_mps") is not None]
        lift = [r["lift_s"] for r in motion if r.get("lift_s") is not None]
        out += ["", f"- Motion (exploratory, {len(motion)} runs): median release drop "
                + (f"{median(rel) * 100:.1f} cm, fall speed {median(fall):.2f} m/s (n={len(rel)} releases)"
                   if rel else "– (no release)")
                + f"; time to lift {median(lift):.1f} s (n={len(lift)})" * bool(lift)
                + f"; joint speed first 3 s {median([r['speed_first3s'] for r in motion]):.3f} rad/s, "
                  f"overall {median([r['speed_mean'] for r in motion]):.3f} rad/s; "
                  f"jerk RMS {median([r['jerk_rms'] for r in motion]):.0f} rad/s³; "
                  f"joint path {median([r['path_rad'] for r in motion]):.1f} rad"]
    steps = [r["row_step_mean"] for r in rows if r.get("row_step_mean")]
    if steps:
        out += ["", f"- Mean joint change per returned row: {sum(steps) / len(steps):.5f} rad"]
    return out + [""]


def main() -> int:
    global MODE
    args = sys.argv[1:]
    out_name = "report.md"
    if "--legacy" in args:
        args.remove("--legacy")
        MODE = "legacy"
    if "--out" in args:
        i = args.index("--out")
        out_name = args[i + 1]
        del args[i:i + 2]
    labels = args
    if not labels:
        print(__doc__)
        return 2
    data = {label: load(label) for label in labels}
    lines = ["# Cell evaluation: before / after fine-tune", "",
             "Simulation (MuJoCo, YAM arms), evaluation seeds < 1000 (training 4000+), same scene per task x seed "
             "for every model, training prompts. Success = part resting in the target zone (cnc_expert.task_done) AND "
             "the arm's gripper open, stable for 3 checks (0.4 s); time from the model's first answer. "
             "Primary: paired success (exact McNemar); secondary: paired time where both succeed, runs with contact. "
             + ("Scoring: FIRST attempt per scene (corrected 22.11. 10:00, Codex review): an action the vendor check "
                "rejects (e.g. gripper 1.05-1.09 outside 0..1) is the model's failure, not retried; only infrastructure "
                "errors are retried once and excluded. "
                if MODE == "first" else
                "Scoring: LEGACY as pre-registered: latest non-error attempt; action errors were wrongly treated as "
                "infrastructure (retried, scene excluded) - biased in favour of models that produce them. ")
             + "Contact runs = runs with at least one detected contact, not a collision count. "
             "Expert = reference only (its success also requires no contact and a retreat). "
             "Contact = arm–cell penetration > 0.5 mm; arm–arm and part–environment are not checked. "
             "Wilson 95 % intervals.", ""]
    ref = dataset_row_step()
    if ref:
        lines += [f"Rate check: training data moves {ref:.5f} rad per frame at 10 fps while the arm moves "
                  f"(= {ref / 2:.5f} per row at 20 rows/s, {ref / 3:.5f} at 30). Compare with each model's "
                  "'joint change per returned row' to pick --rate.", ""]
    for label in labels:
        lines += section(label, data[label])
    models = [x for x in labels if x != "expert"]
    for after in models[1:]:  # the first model (the base) against each later one, paired on identical scenes
        before = models[0]
        pairs = sorted(set(data[before]) & set(data[after]))
        b = [p for p in pairs if not data[before][p]["success"] and data[after][p]["success"]]
        c = [p for p in pairs if data[before][p]["success"] and not data[after][p]["success"]]
        kb = sum(data[before][p]["success"] for p in pairs)
        ka = sum(data[after][p]["success"] for p in pairs)
        lo_b, hi_b = wilson(kb, len(pairs))
        lo_a, hi_a = wilson(ka, len(pairs))
        separated = lo_a > hi_b or lo_b > hi_a
        p = mcnemar_exact(len(b), len(c))
        both = [x for x in pairs if data[before][x]["success"] and data[after][x]["success"]]
        dt = [data[after][x]["done_s"] - data[before][x]["done_s"] for x in both]
        cb = sum(data[before][p]["contact_steps"] > 0 for p in pairs)
        ca = sum(data[after][p]["contact_steps"] > 0 for p in pairs)
        lines += [f"## Paired: {before} → {after} ({len(pairs)} identical scenes)", "",
                  f"- Success {fmt(kb, len(pairs))} → {fmt(ka, len(pairs))}",
                  f"- **Paired (primary): fail→success {len(b)}, success→fail {len(c)}; exact McNemar p = {p:.3f}**"
                  + (" → paired difference on these simulated test scenes" if p < 0.05 else " → no proven difference"),
                  f"- Unpaired Wilson intervals {'do not overlap' if separated else 'overlap'} (descriptive only)",
                  f"- Time to done on scenes both solved (n={len(both)}): median change "
                  + (f"{median(dt):+.1f} s" if dt else "–"),
                  f"- Runs with arm–cell contact: {cb} → {ca}",
                  "- Fail→success scenes: " + (", ".join(f"{t} seed {s}" for t, s in b) or "none"),
                  "- Success→fail scenes: " + (", ".join(f"{t} seed {s}" for t, s in c) or "none"), ""]
    report = "\n".join(lines)
    (OUT / out_name).write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
