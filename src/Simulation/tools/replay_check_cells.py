"""Pre-flight check for a cell dataset (record_cells.py): replay every session open-loop and see the task succeed.

For each ep-<seed>: rebuild the same cell, prepare_scene with the same seeded rng (the expert draws the scene first),
then send exactly the recorded `action` rows, each held for two control steps, with CellController.step() before
every env.step like the expert. Success = cnc_expert.task_done for the arm's part; arm-cell contacts are reported.

    docker compose run --rm --no-deps simulation python /app/tools/replay_check_cells.py datasets/cells-v1
Exit code 0 when at least --min-rate of the sessions succeed (default 0.9). No API calls, no credits.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import numpy as np  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from app.cnc import CellController  # noqa: E402
from app.cnc_expert import TASKS, Planner, prepare_scene, task_done  # noqa: E402
from record_cells import make_env  # noqa: E402
from record_dataset import KEEP_EVERY  # noqa: E402

PROMPT_TO_TASK = {spec["prompt"]: name for name, spec in TASKS.items()}
START_TOL = 1e-3  # recorded first state must match the rebuilt scene (rad / gripper units)


def replay(session: Path) -> dict:
    """Strict: no extra settle steps (success must hold at the dataset's last frame), only the task's own part
    (TASKS[task]["part"], the one the expert grips: on the belt the leading part of its kind) counts and may be
    touched; any other arm contact, or a start-state mismatch, fails the session."""
    seed = int(session.name.split("-")[-1])
    prompt = json.loads((session / "meta/tasks.jsonl").read_text().splitlines()[0])["task"]
    task = PROMPT_TO_TASK.get(prompt)
    if task is None:
        return {"session": session.name, "task": None, "replay_success": False, "error": f"unknown prompt {prompt!r}"}
    part = TASKS[task]["part"]
    table = pq.read_table(next((session / "data").rglob("*.parquet")), columns=["action", "observation.state"])
    actions = np.array(table.column("action").to_pylist(), dtype=float)
    states = np.array(table.column("observation.state").to_pylist(), dtype=float)
    env = make_env(task)
    try:
        ctrl = CellController(env)
        prepare_scene(env, task, np.random.default_rng(seed), ctrl)
        planner = Planner(env, TASKS[task]["arm"], np.random.default_rng(0))
        s0 = env.state()
        start_err = float(np.abs(np.r_[s0["right"], s0["left"]] - states[0]).max())
        contacts: set[str] = set()
        for row in actions:
            right, left = row[:7], row[7:]
            for _ in range(KEEP_EVERY):
                ctrl.step()
                env.step(left, right)
                contacts.update(planner.touching((part,)))
        done = task_done(env, task, ctrl, part)
        ok = done and not contacts and start_err <= START_TOL and bool(np.isfinite(actions).all())
        return {"session": session.name, "task": task, "part": part, "frames": len(actions),
                "start_state_max_err": round(start_err, 5), "done": done, "contacts": sorted(contacts),
                "replay_success": bool(ok)}
    finally:
        env.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-rate", type=float, default=0.9)
    parser.add_argument("--reject", type=Path, help="move sessions that fail the replay into this folder")
    args = parser.parse_args()
    sessions = sorted(p for p in args.dataset.iterdir() if (p / "meta/info.json").exists())
    if args.limit:
        sessions = sessions[: args.limit]
    results = []
    for session in sessions:
        result = replay(session)
        results.append(result)
        print(json.dumps(result), flush=True)
    ok = sum(r["replay_success"] for r in results)
    if args.reject:
        args.reject.mkdir(parents=True, exist_ok=True)
        for r in results:
            if not r["replay_success"]:
                (args.dataset / r["session"]).rename(args.reject / r["session"])
                print(f"rejected {r['session']} -> {args.reject}")
    rate = ok / len(results) if results else 0.0
    per_task = {t: f"{sum(r['replay_success'] for r in results if r.get('task') == t)}/"
                   f"{sum(r.get('task') == t for r in results)}" for t in TASKS}
    print(f"per task: {per_task}")
    print(f"replay: {ok}/{len(results)} succeed ({rate:.0%}); required {args.min_rate:.0%} -> "
          f"{'PASS' if rate >= args.min_rate else 'FAIL'}")
    return 0 if rate >= args.min_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
