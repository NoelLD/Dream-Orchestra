"""Record one collision-aware expert demonstration in a cell scene as a one-episode LeRobot v2.1 session.

    docker compose run --rm --no-deps simulation python /app/tools/record_cells.py --out datasets/cells-test/ep-4000 --seed 4000
Task per seed: TASKS order (sort_round, sort_cube, cnc_load, cnc_unload) by seed % 4, unless --task is given.
Same format as record_dataset.py --small (14-dim state/action right arm first, 10 fps, 320x180 run-time renderer).
Only episodes that pass (goal reached, no arm-cell contact) are written. No Dream API calls, no credits.
Training seeds start at 4000; evaluation seeds stay below 1000.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import yam_env  # noqa: E402

from app.cnc import CellController, cell_xml  # noqa: E402
from app.cnc_expert import ALL_TASKS, TASKS, run_episode  # noqa: E402
from app.embodiment import CAMERAS  # noqa: E402
from record_dataset import FPS, Recorder, write_video  # noqa: E402

TASK_ORDER = list(TASKS)
_original_xml = yam_env.build_xml


def task_for(seed: int) -> str:
    return TASK_ORDER[seed % len(TASK_ORDER)]


def make_env(task: str):
    yam_env.build_xml = lambda: cell_xml(_original_xml(), ALL_TASKS[task]["cell"])
    try:
        return yam_env.YamEnv()
    finally:
        yam_env.build_xml = _original_xml


def write_session(root: Path, recorder: Recorder, prompt: str, result: dict) -> None:
    if root.exists():
        shutil.rmtree(root)
    (root / "meta").mkdir(parents=True)
    n = len(recorder.states)
    table = pa.table({
        "observation.state": pa.array(recorder.states, type=pa.list_(pa.float32(), 14)),
        "action": pa.array(recorder.actions, type=pa.list_(pa.float32(), 14)),
        "timestamp": pa.array(np.arange(n, dtype=np.float32) / FPS),
        "frame_index": pa.array(np.arange(n, dtype=np.int64)),
        "episode_index": pa.array(np.zeros(n, dtype=np.int64)),
        "index": pa.array(np.arange(n, dtype=np.int64)),
        "task_index": pa.array(np.zeros(n, dtype=np.int64)),
    })
    data_path = root / "data/chunk-000/episode_000000.parquet"
    data_path.parent.mkdir(parents=True)
    pq.write_table(table, data_path)
    for role in CAMERAS:
        write_video(root / f"videos/chunk-000/observation.images.{role}/episode_000000.mp4", recorder.images[role])
    height, width = recorder.images[next(iter(CAMERAS))][0].shape[:2]
    video_feature = {"dtype": "video", "shape": [height, width, 3], "names": ["height", "width", "channels"],
                     "info": {"video.fps": FPS, "video.codec": "h264", "video.pix_fmt": "yuv420p",
                              "video.height": height, "video.width": width, "video.channels": 3,
                              "has_audio": False}}
    info = {
        "codebase_version": "v2.1", "robot_type": "yam", "total_episodes": 1, "total_frames": n,
        "total_tasks": 1, "total_videos": len(CAMERAS), "total_chunks": 1, "chunks_size": 1000, "fps": FPS,
        "splits": {"train": "0:1"},
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
        "features": {
            "action": {"dtype": "float32", "shape": [14], "names": None},
            "observation.state": {"dtype": "float32", "shape": [14], "names": None},
            **{f"observation.images.{role}": video_feature for role in CAMERAS},
            "timestamp": {"dtype": "float32", "shape": [1], "names": None},
            "frame_index": {"dtype": "int64", "shape": [1], "names": None},
            "episode_index": {"dtype": "int64", "shape": [1], "names": None},
            "index": {"dtype": "int64", "shape": [1], "names": None},
            "task_index": {"dtype": "int64", "shape": [1], "names": None},
        },
    }
    (root / "meta/info.json").write_text(json.dumps(info, indent=2))
    (root / "meta/tasks.jsonl").write_text(json.dumps({"task_index": 0, "task": prompt}) + "\n")
    (root / "meta/episodes.jsonl").write_text(
        json.dumps({"episode_index": 0, "tasks": [prompt], "length": n}) + "\n")
    # Sibling file (the validator refuses stray .json inside a dataset folder; modal_gen moves it aside).
    (root.parent / f"{root.name}.sim_results.json").write_text(json.dumps([result], indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True, help="session folder, e.g. datasets/cells-v1/ep-4000")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--task", choices=TASK_ORDER)
    args = parser.parse_args()
    task = args.task or task_for(args.seed)
    env = make_env(task)
    recorder = Recorder(small=True)
    original_step = yam_env.YamEnv.step
    yam_env.YamEnv.step = recorder.wrap(original_step)  # CellRun calls env.step -> class attribute -> recorder
    try:
        ep = run_episode(env, task, args.seed, CellController(env), fresh=True)
    finally:
        yam_env.YamEnv.step = original_step
        env.close()
    result = ep.public() | {"frames": len(recorder.states)}
    print(json.dumps(result), flush=True)
    if not ep.passed:
        print(f"seed {args.seed} ({task}) failed in sim, not exported", flush=True)
        return 2
    write_session(args.out, recorder, TASKS[task]["prompt"], result)
    print(f"{args.out}: {task}, {len(recorder.states)} frames", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
