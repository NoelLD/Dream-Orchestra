"""Before/after evaluation in the cell scenes: base Dream-1 vs the cell fine-tune vs the scripted expert.

    docker compose run --rm --no-deps simulation python /app/tools/eval_cells.py --model expert --seeds 0-9
    docker compose run --rm --no-deps simulation python /app/tools/eval_cells.py --model beta --seeds 0-9 --tasks cnc_load
    ... --model dream-1-ft:<id> --rate 10       # rows/s the model's chunk means (see "rate" below)
Results append to /data/evals/cells/<label>.jsonl (one line per task x seed; finished pairs are skipped on rerun),
videos for --video seeds to /data/evals/cells/video/<label>/<task>-<seed>.mp4. Report: tools/eval_cells_report.py.

Same scenes for every model: cell + prepare_scene(default_rng(seed)) exactly as the expert's training episodes, but
evaluation seeds stay < 1000 (training used 4000+). Same prompts as training (TASKS[task]["prompt"]).
Per episode we measure what the Dream SDK does not report:
  success      cnc_expert.task_done (part resting in the target zone, still) AND the arm's gripper open (> 0.5)
               - checked every 4 sim steps
  contacts     arm-vs-cell contacts deeper than 0.5 mm (Planner.touching; the task's own part is allowed)
  outcome      success | timeout_no_grasp (part never lifted 2 cm) | timeout_dropped (lifted, not at target)
               | action_error (vendor check rejected the model's chunk: a failure, not retried)
               | error (infrastructure, retried once)
  time, calls, cost (calls x price per call)
rate: Dream returns 48 rows per call. The runner plays one row per 50 ms sim step (20 rows/s). A fine-tune on a
10 fps dataset may mean 10 rows/s (tutorial step 8) or 30 (training resamples to 30): --rate resamples the chunk
to the 20 Hz sim linearly; row_step (mean joint change per row) is logged so the right rate can be read off
against the training data (eval_cells_report.py prints the dataset's own per-frame change).
"""

import argparse
import base64
import io
import json
import os
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.cnc import CellController  # noqa: E402
from app.cnc_expert import TASKS, Planner, prepare_scene, run_episode, task_done  # noqa: E402
from app.render import SmallRenderer  # noqa: E402
from record_cells import make_env  # noqa: E402
from record_dataset import write_video  # noqa: E402

SIM_HZ = 20
CHECK_EVERY = 4
LIFT_M = 0.02
RELEASED = 0.5  # gripper opening (0 closed .. 1 open) above which the part counts as let go
HOLD_CHECKS = 3  # done only if placed + released at 3 consecutive checks (0.4 s stable); done_s = the first
MODELS = {"beta": "dreamlabs/dream-1-beta", "flash": "dreamlabs/dream-1-flash"}
OUT = config.DATA_DIR / "evals/cells"


def seeds_arg(text: str) -> list[int]:
    a, _, b = text.partition("-")
    return list(range(int(a), int(b or a) + 1))


def resample(rows: np.ndarray, rate: float) -> np.ndarray:
    """Rows meant at `rate` rows/s -> one row per 50 ms sim step (linear in between)."""
    if rate == SIM_HZ:
        return rows
    duration = len(rows) / rate
    t_sim = np.arange(int(round(duration * SIM_HZ))) / SIM_HZ
    t_src = np.arange(len(rows)) / rate
    return np.stack([np.interp(t_sim, t_src, rows[:, j]) for j in range(rows.shape[1])], axis=1)


class Episode:
    def __init__(self, task: str, seed: int, video: bool):
        self.task, self.seed = task, seed
        self.env = make_env(task)
        self.ctrl = CellController(self.env)
        prepare_scene(self.env, task, np.random.default_rng(seed), self.ctrl)
        self.part = TASKS[task]["part"]
        self.planner = Planner(self.env, TASKS[task]["arm"], np.random.default_rng(0))
        self.z0 = float(self.env.data.body(self.part).xpos[2])
        self.steps = 0
        self.max_lift = 0.0
        self.contacts: dict[str, int] = {}
        self.contact_steps = 0
        self.done_at: float | None = None
        self.placed_seen = False
        self.t0 = 0  # sim step of the model's first answer: times are measured from here
        self.streak = 0
        self.video = [] if video else None
        self.small: SmallRenderer | None = None
        # release / drop (added 22.11. 10:15, exploratory, after Martin saw lower drops in a video): when the arm's
        # gripper opens after the part was lifted, follow the part for 1.5 s: drop = release height - lowest point,
        # fall speed = fastest downward part speed in that window
        self.arm = TASKS[task]["arm"]
        self.was_open = True
        self.lifted = False
        self.releases: list[dict] = []
        self.watch: dict | None = None
        self.z_prev = self.z0
        # motion (exploratory, 22.11. 10:20: arm looked calmer and more targeted): task arm joints 1-6 per step
        self.q_hist: list[np.ndarray] = []
        self.lift_at: float | None = None

    def images(self):
        if self.small is None:
            self.small = SmallRenderer(self.env.model, shadows=config.RENDER_SHADOWS)
        return self.small.views(self.env.data)

    def step(self, left, right) -> bool:
        """One 50 ms sim step like the expert (controller, then physics). True once the task is done."""
        self.ctrl.step()
        self.env.step(left, right)
        self.steps += 1
        z = float(self.env.data.body(self.part).xpos[2])
        self.max_lift = max(self.max_lift, z - self.z0)
        if not self.lifted and z - self.z0 > LIFT_M and self.steps > self.t0:
            self.lift_at = round((self.steps - self.t0) / SIM_HZ, 2)
        self.lifted = self.lifted or z - self.z0 > LIFT_M
        if self.steps > self.t0:
            self.q_hist.append(np.array(self.env.state()[self.arm][:6], dtype=float))
        is_open = self.env.state()[self.arm][6] > RELEASED
        if self.lifted and is_open and not self.was_open and self.watch is None:
            self.watch = {"t_s": round((self.steps - self.t0) / SIM_HZ, 2), "z_rel": z, "z_min": z, "v_max": 0.0,
                          "until": self.steps + int(1.5 * SIM_HZ)}
        if self.watch is not None:
            self.watch["z_min"] = min(self.watch["z_min"], z)
            self.watch["v_max"] = max(self.watch["v_max"], (self.z_prev - z) * SIM_HZ)
            if self.steps >= self.watch["until"]:
                self.releases.append({"t_s": self.watch["t_s"], "drop_m": round(self.watch["z_rel"] - self.watch["z_min"], 4),
                                      "fall_mps": round(self.watch["v_max"], 3)})
                self.watch = None
        self.was_open, self.z_prev = is_open, z
        hits = self.planner.touching((self.part,))
        if hits:
            self.contact_steps += 1
            for h in hits:
                self.contacts[h] = self.contacts.get(h, 0) + 1
        if self.steps % CHECK_EVERY == 0:
            if self.video is not None:
                frames = self.images()
                self.video.append(np.concatenate([frames["top"], frames["left"], frames["right"]], axis=1))
            placed = task_done(self.env, self.task, self.ctrl, self.part)
            self.placed_seen = self.placed_seen or placed
            released = self.env.state()[TASKS[self.task]["arm"]][6] > RELEASED
            self.streak = self.streak + 1 if (placed and released) else 0  # resting AND let go, stably
            if self.streak >= HOLD_CHECKS:
                self.done_at = (self.steps - (HOLD_CHECKS - 1) * CHECK_EVERY - self.t0) / SIM_HZ
                return True
        return False

    def result(self, status: str) -> dict:
        if self.watch is not None:  # episode ended inside the 1.5 s window (e.g. success): keep what was seen
            self.releases.append({"t_s": self.watch["t_s"], "drop_m": round(self.watch["z_rel"] - self.watch["z_min"], 4),
                                  "fall_mps": round(self.watch["v_max"], 3), "partial": True})
            self.watch = None
        success = self.done_at is not None
        motion = {}
        if len(self.q_hist) > 4:
            q = np.array(self.q_hist)
            v = np.diff(q, axis=0) * SIM_HZ  # rad/s per joint
            speed = np.linalg.norm(v, axis=1)
            jerk = np.diff(q, n=3, axis=0) * SIM_HZ ** 3
            first_s = min(len(speed), SIM_HZ * 3)  # first 3 s after the first answer
            motion = {"path_rad": round(float(np.abs(np.diff(q, axis=0)).sum()), 3),  # summed joint travel
                      "speed_first3s": round(float(speed[:first_s].mean()), 4),  # rad/s, start of the motion
                      "speed_mean": round(float(speed.mean()), 4),
                      "jerk_rms": round(float(np.sqrt((jerk ** 2).sum(axis=1).mean())), 2)}  # rad/s^3
        if status in ("error", "action_error"):
            outcome = status
        elif success:
            outcome = "success"
        else:
            outcome = ("timeout_no_grasp" if self.max_lift < LIFT_M else
                       "timeout_placed_not_released" if self.placed_seen else "timeout_dropped")
        return {"task": self.task, "seed": self.seed, "success": success, "outcome": outcome,
                "clean_success": success and not self.contacts, "contact_steps": self.contact_steps,
                "contacts": dict(sorted(self.contacts.items(), key=lambda kv: -kv[1])[:6]),
                "sim_s": round((self.steps - self.t0) / SIM_HZ, 2), "done_s": self.done_at,
                "max_lift_m": round(self.max_lift, 3),
                "lift_s": self.lift_at, **motion,
                "releases": self.releases[:6],  # each: time, drop (m) within 1.5 s, max downward speed (m/s)
                "release_drop_m": (self.releases[-1]["drop_m"] if self.releases else None),  # last release
                "release_fall_mps": (self.releases[-1]["fall_mps"] if self.releases else None),
                "part_end": np.round(self.env.data.body(self.part).xpos, 3).tolist()}

    def close(self):
        if self.small is not None:
            self.small.close()
        self.env.close()


def run_expert(task: str, seed: int) -> dict:
    """Reference: the scripted collision-aware expert on the same scene (no API)."""
    env = make_env(task)
    try:
        ep = run_episode(env, task, seed, CellController(env), fresh=True)
    finally:
        env.close()
    return {"task": task, "seed": seed, "success": ep.passed, "outcome": "success" if ep.passed else ep.reason,
            "clean_success": ep.passed, "contact_steps": len(ep.collisions), "contacts": ep.collisions[:6],
            "sim_s": round(ep.steps / SIM_HZ, 2), "done_s": round(ep.steps / SIM_HZ, 2) if ep.passed else None,
            "max_lift_m": round(ep.max_lift_m, 3), "api_calls": 0, "cost_usd": 0.0,
            "note": "reference only: expert success also requires no contact and a retreat; contact_steps = distinct contacts"}


def run_dream(task: str, seed: int, checkpoint: str, rate: float, timeout_s: float, video: bool, key: str,
              grip_tol: float = 0.05) -> dict:
    import dream_control as dc

    gateway = os.environ.get("DREAM_GATEWAY_URL", "https://api.dreamlabs.ai")
    ep = Episode(task, seed, video)
    prompt = TASKS[task]["prompt"]
    windows = {name: deque(maxlen=dc.FRAMES) for name in dc.VIDEO_ROLES}
    calls, row_steps, status, error, policy, restarts = 0, [], "timeout", None, None, 0
    grip_clipped = 0  # rows of accepted chunks whose gripper was clipped beyond the vendor's 0.05 (amendment 22.11.)
    started = time.monotonic()

    def capture():
        for name, rgb in ep.images().items():
            buffer = io.BytesIO()
            Image.fromarray(rgb).resize(dc.FRAME_SIZE, Image.BILINEAR).save(buffer, "JPEG", quality=85)
            windows[name].append(base64.b64encode(buffer.getvalue()).decode("ascii"))

    try:
        while any(len(w) < dc.FRAMES for w in windows.values()):  # 9-frame windows, arms holding
            s = ep.env.state()
            ep.step(s["left"], s["right"])
            if ep.steps % dc.FRAME_EVERY_STEPS == 0:
                capture()
        t0 = ep.t0 = ep.steps
        poses = checkpoint in dc.POSE_MODELS
        def open_session(with_poses):
            cfg = dc.policy_config(checkpoint, gateway, with_poses)
            cfg["action_hz"] = rate  # client pacing + seam smoothing at the rate the rows are played (Grok review)
            session = dc.open_policy(cfg, key)
            dc.feed(session, ep.env, windows, prompt, checkpoint, ep.steps, every=0, station=with_poses)
            return session

        policy = open_session(poses)
        done = False

        while not done and (ep.steps - t0) / SIM_HZ < timeout_s:
            for attempt in range(40):  # model warm-up (NO_CAPACITY) and transient errors
                try:
                    reply = policy.get_action()
                    break
                except Exception as exc:  # noqa: BLE001
                    name = type(exc).__name__
                    if name == "DreamSessionExpired" and restarts < 3:  # runner.py does the same
                        restarts += 1
                        policy.close()
                        policy = open_session(poses)
                        continue
                    if not poses and dc.needs_poses(exc):  # runner.py pose fallback
                        policy.close()
                        poses = True
                        policy = open_session(poses)
                        continue
                    if attempt < 39 and ("Capacity" in name or "Warming" in name or "Timeout" in name
                                         or getattr(exc, "retry_after_s", None)):
                        time.sleep(min(float(getattr(exc, "retry_after_s", 10) or 10), 30))
                        continue
                    raise
            calls += 1
            chunk_clipped = 0
            if grip_tol > 0.05:  # exploratory amendment 22.11. (separate labels): fine-tunes return gripper 1.05-1.09;
                # the vendor already clips up to 0.05 outside 0..1 and aborts beyond; we clip up to grip_tol
                reply = {k: reply[k] for k in ("q_l_chunk", "q_r_chunk")}
                for k in ("q_l_chunk", "q_r_chunk"):
                    a = np.array(reply[k], dtype=float, copy=True)
                    if a.ndim == 2 and a.shape[1] == 7:  # malformed replies go to the vendor check unchanged
                        g = a[:48, 6]  # only the rows that are executed
                        near = (g >= -grip_tol) & (g <= 1 + grip_tol)
                        chunk_clipped += int((near & ((g < -0.05) | (g > 1.05))).sum())  # beyond the vendor's own clip
                        g[near] = np.clip(g[near], 0.0, 1.0)  # values beyond grip_tol still abort below
                    reply[k] = a
            left, right = dc.validate_chunk(ep.env, reply, 48, verbose=False)
            grip_clipped += chunk_clipped  # counted only for accepted chunks (rows of both arms)
            per_row = np.abs(np.diff(np.c_[right[:, :6], left[:, :6]], axis=0)).mean(axis=1)
            moving = per_row[per_row > 1e-4]  # same filter as the training-data reference in the report
            if len(moving):
                row_steps.append(float(moving.mean()))
            left, right = resample(left, rate), resample(right, rate)
            for l_row, r_row in zip(left, right):
                if ep.step(l_row, r_row):
                    done = True
                    break
                if ep.steps % dc.FRAME_EVERY_STEPS == 0:
                    capture()
                    dc.feed(policy, ep.env, windows, prompt, checkpoint, ep.steps, station=poses)
                if (ep.steps - t0) / SIM_HZ >= timeout_s:
                    break
        status = "success" if done else "timeout"
    except Exception as exc:  # noqa: BLE001 - every failure is a result line, never a crash of the series
        text = str(exc)
        # an action the vendor check rejects is the model's output, not infrastructure: a failure, never retried
        action = isinstance(exc, ValueError) and ("No rows executed" in text or "no rows executed" in text
                                                  or "joint chunks" in text)
        status, error = ("action_error" if action else "error"), f"{type(exc).__name__}: {text[:200]}"
    finally:
        if policy is not None:
            try:
                policy.close()
            except Exception:  # noqa: BLE001
                pass
    result = ep.result(status) | {"api_calls": calls, "cost_usd": round(calls * config.price_per_call(checkpoint), 4),
                                  "row_step_mean": round(float(np.mean(row_steps)), 5) if row_steps else None,
                                  "wall_s": round(time.monotonic() - started, 1), "error": error,
                                  "obs_window_hz": SIM_HZ / dc.FRAME_EVERY_STEPS, "frames": dc.FRAMES,
                                  "action_hz": rate, "restarts": restarts,
                                  "grip_tol": grip_tol, "grip_clipped": grip_clipped}
    if ep.video:
        path = OUT / "video" / LABEL / f"{task}-{seed}.mp4"
        write_video(path, ep.video)
    ep.close()
    return result


LABEL = ""


def main() -> int:
    global LABEL
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="expert | beta | flash | dream-1-ft:<id> | full model id")
    parser.add_argument("--label", help="results file name (default: derived from model and rate)")
    parser.add_argument("--tasks", default=",".join(TASKS))
    parser.add_argument("--seeds", type=seeds_arg, default=seeds_arg("0-9"))
    parser.add_argument("--rate", type=float, default=20.0, help="rows/s of the model's chunk (runner: 20)")
    parser.add_argument("--timeout", type=float, default=45.0, help="sim seconds after the first answer")
    parser.add_argument("--video", type=seeds_arg, default=[], help="seeds to film, e.g. 0-1")
    parser.add_argument("--grip-tol", type=float, default=0.05,
                        help="clip gripper values up to this far outside 0..1 (0.05 = vendor behaviour: clips up to 0.05, aborts beyond)")
    parser.add_argument("--max-usd", type=float, default=5.0, help="stop the series above this spend")
    args = parser.parse_args()
    checkpoint = MODELS.get(args.model, args.model)
    LABEL = args.label or ("expert" if args.model == "expert"
                           else f"{args.model.replace('/', '_').replace(':', '_')}-r{args.rate:g}")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{LABEL}.jsonl"
    done = set()
    if path.exists():
        for line in path.read_text().splitlines():
            r = json.loads(line)
            if args.model != "expert":
                same = (r.get("model") == checkpoint and r.get("rate") == args.rate
                        and r.get("grip_tol", 0.05) == args.grip_tol)
                if not same:
                    print(f"{path.name} holds runs with another model/rate/grip_tol: use a new --label")
                    return 2
            action = r.get("outcome") == "action_error" or "No rows executed" in (r.get("error") or "")
            if r.get("outcome") != "error" or action:  # an action error is a scored failure (old files: "error")
                done.add((r["task"], r["seed"]))
    key = os.environ.get("DREAM_API_KEY", "")
    if args.model != "expert" and not key:
        print("DREAM_API_KEY is not set")
        return 2
    import fcntl

    lock = open(OUT / ".dream.lock", "w")  # one Dream session per API key: parallel runs replace each other's session
    if args.model != "expert":
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another Dream evaluation is running (one session per key); run them one after another")
            return 2
    spent = 0.0
    for seed in args.seeds:
        for task in args.tasks.split(","):
            if (task, seed) in done:
                continue
            if spent > args.max_usd:
                print(f"budget {args.max_usd} $ reached, stopping")
                return 1
            for attempt in (1, 2):  # an infrastructure error is retried once (both kept); action_error is not
                if args.model == "expert":
                    r = run_expert(task, seed)
                else:
                    r = run_dream(task, seed, checkpoint, args.rate, args.timeout, seed in args.video, key, args.grip_tol)
                r |= {"model": checkpoint, "label": LABEL, "rate": args.rate, "attempt": attempt,
                      "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                spent += r.get("cost_usd", 0.0)
                with path.open("a") as fh:
                    fh.write(json.dumps(r) + "\n")
                print(json.dumps({k: r.get(k) for k in ("task", "seed", "outcome", "contact_steps", "done_s",
                                                         "api_calls", "row_step_mean", "error")}), flush=True)
                if r["outcome"] != "error":
                    break
    print(f"done: {path} (spent ~{spent:.3f} $)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
