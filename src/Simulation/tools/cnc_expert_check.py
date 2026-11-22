"""Run the collision-aware CNC expert on several seeds; report success/collisions; optionally film episodes.

    docker compose run --rm --no-deps simulation python /app/tools/cnc_expert_check.py --seeds 1000-1005
    ... --video /data/cnc_expert.mp4 --seeds 1000-1001   # overview + robot camera, both tasks per seed
No Dream API calls, no credits.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import av  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402
import yam_env  # noqa: E402

from app.cnc import CellController, cell_xml  # noqa: E402
from app.cnc_expert import TASKS, run_episode  # noqa: E402

_original = yam_env.build_xml


def seeds_arg(text: str) -> list[int]:
    a, _, b = text.partition("-")
    return list(range(int(a), int(b or a) + 1))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=seeds_arg, default=seeds_arg("1000-1003"))
    parser.add_argument("--tasks", default="sort_round,sort_cube,cnc_load,cnc_unload")
    parser.add_argument("--video", type=Path)
    args = parser.parse_args()
    frames: list[np.ndarray] = []
    results = []
    for seed in args.seeds:
        for task in args.tasks.split(","):
            yam_env.build_xml = lambda c=TASKS[task]["cell"]: cell_xml(_original(), c)
            env = yam_env.YamEnv()
            ctrl = CellController(env)
            if args.video:
                renderer = mujoco.Renderer(env.model, height=360, width=640)
                cam = mujoco.MjvCamera()
                cam.lookat[:] = [0.0, -0.08, 0.88]
                cam.distance, cam.azimuth, cam.elevation = 1.5, -150.0 if TASKS[task]["arm"] == "left" else -30.0, -26.0
                original_step = env.step

                def step(left, right, _orig=original_step, _r=renderer, _c=cam, _e=env):
                    out = _orig(left, right)
                    _r.update_scene(_e.data, camera=_c)
                    frames.append(np.concatenate([_r.render().copy(), _e.images()["top"]], axis=1))
                    return out

                env.step = step
            started = time.time()
            ep = run_episode(env, task, seed, ctrl)
            row = ep.public() | {"seconds": round(time.time() - started, 1)}
            results.append(row)
            print(json.dumps(row), flush=True)
            env.close()
    ok = sum(r["passed"] for r in results)
    print(f"passed {ok}/{len(results)}")
    if args.video and frames:
        with av.open(str(args.video), "w") as container:
            stream = container.add_stream("h264", rate=20)
            stream.height, stream.width = frames[0].shape[:2]
            stream.pix_fmt = "yuv420p"
            for f in frames:
                for packet in stream.encode(av.VideoFrame.from_ndarray(f, format="rgb24")):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        print(f"{args.video}: {len(frames)} frames")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
