"""Pre-flight check before paying for a fine-tune: replay each recorded episode open-loop and see it succeed again.

For every session ep-<seed> of a dataset, rebuild the same scene (same seed -> same fruit positions and light),
then send exactly the recorded `action` rows (10 fps, each held for two 50 ms sim steps) - no script, no IK.
If the fruit is lifted again, the recorded actions are the commands that solved the task, aligned with the
states and frames. Misaligned or wrongly ordered actions would fail here, for free, instead of in training.

    docker compose run --rm simulation python /app/tools/replay_check.py datasets/pick-banana-v2
Exit code 0 when at least --min-rate of the episodes succeed on replay (default 0.9).
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
from yam_env import YamEnv  # noqa: E402

from record_dataset import KEEP_EVERY, randomized_reset  # noqa: E402  (same scene randomization as recording)

LIFT_M = 0.08


def replay(session: Path) -> dict:
    seed = int(session.name.split("-")[-1])
    info = json.loads((session / "meta/info.json").read_text())
    task = json.loads((session / "meta/tasks.jsonl").read_text().splitlines()[0])["task"]
    fruit = "banana" if "banana" in task else "apple"
    table = pq.read_table(next((session / "data").rglob("*.parquet")), columns=["action", "observation.state"])
    actions = np.array(table.column("action").to_pylist(), dtype=float)
    states = np.array(table.column("observation.state").to_pylist(), dtype=float)

    original_reset = YamEnv.reset
    YamEnv.reset = randomized_reset(original_reset, np.random.default_rng(seed))
    try:
        env = YamEnv()
    finally:
        YamEnv.reset = original_reset
    try:
        start_z = float(env.data.body(fruit).xpos[2])
        first_state_err = float(np.abs(np.r_[env.state()["right"], env.state()["left"]] - states[0]).max())
        max_lift = 0.0
        for row in actions:
            right, left = row[:7], row[7:]
            for _ in range(KEEP_EVERY):
                env.step(left, right)
                max_lift = max(max_lift, float(env.data.body(fruit).xpos[2]) - start_z)
        return {"session": session.name, "fruit": fruit, "frames": len(actions), "fps": info["fps"],
                "max_lift_m": round(max_lift, 4), "start_state_max_err": round(first_state_err, 4),
                "replay_success": max_lift >= LIFT_M}
    finally:
        env.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="check only the first N sessions (0 = all)")
    parser.add_argument("--min-rate", type=float, default=0.9)
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
    rate = ok / len(results) if results else 0.0
    print(f"replay: {ok}/{len(results)} succeed ({rate:.0%}); required {args.min_rate:.0%} -> "
          f"{'PASS' if rate >= args.min_rate else 'FAIL'}")
    return 0 if rate >= args.min_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
