"""Record scripted YAM pickups as a LeRobot v2.1 dataset and validate it locally against the YAM embodiment.

    docker compose run --rm simulation python /app/tools/record_dataset.py --out datasets/pick-smoke
No API calls, no credits: validate_dataset() runs offline. Uploading is a separate, explicit step.

Layout follows the Dream Labs fine-tuning tutorial (material/fine_tuning_tutorial_joint_space.ipynb, step 4):
state/action are 14 floats, right arm first (right_arm 6, right_gripper 1, left_arm 6, left_gripper 1),
action = the absolute joint/gripper target commanded at that frame, state = measured before the command.
The sim servos at 20 Hz; training accepts 30/15/10/5 fps, so every second control step is kept (10 fps).
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import av  # noqa: E402
import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from dream import datasets  # noqa: E402

import mock_pickups  # noqa: E402
from yam_env import YamEnv  # noqa: E402

FPS = 10
KEEP_EVERY = 2  # 20 Hz control -> 10 fps
from app.embodiment import CAMERAS, EMBODIMENT  # noqa: E402

SKILLS = [  # (fruit, grasp yaw, task prompt); banana sits on the right arm's side, apple on the left's
    ("banana", np.pi / 2, "pick up the banana and put it back down"),
    ("apple", 0.0, "pick up the apple and put it back down"),
]
JITTER_M = 0.03  # uniform +-3 cm on the fruit's table position
LIGHT_JITTER = 0.15  # +-15 % light intensity


def randomized_reset(original, rng: np.random.Generator):
    """Wrap YamEnv.reset: after the stock reset, shift the fruits and scale the lights (domain randomization)."""

    def reset(env):
        original(env)
        for fruit in ("banana", "apple"):
            qpos = env.data.joint(f"{fruit}_free").qpos
            qpos[0:2] += rng.uniform(-JITTER_M, JITTER_M, size=2)
        if not hasattr(env, "_base_diffuse"):
            env._base_diffuse = env.model.light_diffuse.copy()
        scale = 1 + rng.uniform(-LIGHT_JITTER, LIGHT_JITTER)
        env.model.light_diffuse[:] = env._base_diffuse * scale
        import mujoco

        mujoco.mj_forward(env.model, env.data)
        return env.state()

    return reset


class Recorder:
    """Collects one episode's frames by wrapping YamEnv.step."""

    def __init__(self):
        self.steps = 0
        self.states: list[np.ndarray] = []
        self.actions: list[np.ndarray] = []
        self.images: dict[str, list[np.ndarray]] = {role: [] for role in CAMERAS}

    def wrap(self, original):
        recorder = self

        def step(env, left, right):
            if recorder.steps % KEEP_EVERY == 0:
                measured = env.state()
                recorder.states.append(np.r_[measured["right"], measured["left"]].astype(np.float32))
                recorder.actions.append(np.r_[np.asarray(right), np.asarray(left)].astype(np.float32))
                frames = env.images()
                for role, cam in CAMERAS.items():
                    recorder.images[role].append(frames[cam])
            recorder.steps += 1
            return original(env, left, right)

        return step


def write_video(path: Path, frames: list[np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w") as container:
        stream = container.add_stream("h264", rate=FPS)
        stream.height, stream.width = frames[0].shape[:2]
        stream.pix_fmt = "yuv420p"
        for frame in frames:
            for packet in stream.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=config.DATASETS_DIR / "pick-smoke")
    parser.add_argument("--episodes", type=int, default=2, help="attempts; failed sim trials are dropped")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--randomize", action="store_true", help="jitter fruit positions and light")
    parser.add_argument("--skill-offset", type=int, default=0, help="first SKILLS entry (for one-episode workers)")
    parser.add_argument("--no-validate", action="store_true", help="skip validate_dataset (validated after merge)")
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    if args.randomize:
        YamEnv.reset = randomized_reset(YamEnv.reset, rng)
    attempts = [SKILLS[(args.skill_offset + i) % len(SKILLS)] for i in range(args.episodes)]
    root = args.out
    if root.exists():
        shutil.rmtree(root)
    (root / "meta").mkdir(parents=True)

    original_step = YamEnv.step
    tasks: dict[str, int] = {}
    episodes_meta, total_frames, index = [], 0, 0
    height = width = None
    episode_index = 0
    for attempt, (fruit, yaw, prompt) in enumerate(attempts):
        recorder = Recorder()
        YamEnv.step = recorder.wrap(original_step)
        try:
            result = mock_pickups.run_trial(fruit, yaw=yaw)
        except ValueError as error:  # IK found no grasp pose for this placement
            result = {"object": fruit, "passed": False, "error": str(error)}
        finally:
            YamEnv.step = original_step
        if not result["passed"]:
            print(f"attempt {attempt} ({fruit}) failed in sim, not exported: {result}", flush=True)
            continue
        result["attempt"] = attempt
        task_index = tasks.setdefault(prompt, len(tasks))
        n = len(recorder.states)
        table = pa.table({
            "observation.state": pa.array(recorder.states, type=pa.list_(pa.float32(), 14)),
            "action": pa.array(recorder.actions, type=pa.list_(pa.float32(), 14)),
            "timestamp": pa.array(np.arange(n, dtype=np.float32) / FPS),
            "frame_index": pa.array(np.arange(n, dtype=np.int64)),
            "episode_index": pa.array(np.full(n, episode_index, dtype=np.int64)),
            "index": pa.array(np.arange(index, index + n, dtype=np.int64)),
            "task_index": pa.array(np.full(n, task_index, dtype=np.int64)),
        })
        data_path = root / f"data/chunk-000/episode_{episode_index:06d}.parquet"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, data_path)
        for role in CAMERAS:
            write_video(root / f"videos/chunk-000/observation.images.{role}/episode_{episode_index:06d}.mp4",
                        recorder.images[role])
        height, width = recorder.images["overhead"][0].shape[:2]
        episodes_meta.append({"episode_index": episode_index, "tasks": [prompt], "length": n,
                              "sim_result": result})
        total_frames += n
        index += n
        print(f"episode {episode_index} (attempt {attempt}): {fruit}, {n} frames, passed", flush=True)
        episode_index += 1

    if not episodes_meta:
        print("no successful episodes")
        return 1
    video_feature = {"dtype": "video", "shape": [height, width, 3], "names": ["height", "width", "channels"],
                     "info": {"video.fps": FPS, "video.codec": "h264", "video.pix_fmt": "yuv420p",
                              "video.height": height, "video.width": width, "video.channels": 3,
                              "has_audio": False}}
    info = {
        "codebase_version": "v2.1",
        "robot_type": "yam",
        "total_episodes": len(episodes_meta),
        "total_frames": total_frames,
        "total_tasks": len(tasks),
        "total_videos": len(episodes_meta) * len(CAMERAS),
        "total_chunks": 1,
        "chunks_size": 1000,
        "fps": FPS,
        "splits": {"train": f"0:{len(episodes_meta)}"},
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
    (root / "meta/tasks.jsonl").write_text(
        "".join(json.dumps({"task_index": i, "task": t}) + "\n" for t, i in tasks.items()))
    (root / "meta/episodes.jsonl").write_text(
        "".join(json.dumps({k: v for k, v in e.items() if k != "sim_result"}) + "\n" for e in episodes_meta))
    (root.parent / f"{root.name}.sim_results.json").write_text(
        json.dumps([e["sim_result"] for e in episodes_meta], indent=2))

    if args.no_validate:
        return 0
    report = datasets.validate_dataset(root, EMBODIMENT)
    print("validate_dataset:", "OK" if report.ok else "FAILED")
    print(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
