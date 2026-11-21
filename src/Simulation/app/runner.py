"""Skill runs in the MuJoCo YAM scene: one at a time, in a worker thread, with stop, timeout, video and live frame.

mode "mock":  the Dream Labs scripted IK pickup (mock_pickups.run_trial). No API calls, no credits.
mode "dream": Dream-1 drives both arms through dream.DreamClient (each get_action = 1.6 s of joint targets).
              A run may take several attempts: after a failed attempt the orchestrator re-homes the arms (or
              continues) and re-prompts, optionally with a different wording (reliability without training).
Success comes from the simulator (skills.SuccessTracker / the scripted trial's own check), never from the API.
Every Dream call is priced (config.price_per_call) and checked against the service budget (config.BUDGET_USD).
"""

import base64
import io
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

from . import config
from .render import SmallRenderer
from .skills import SKILLS, Skill, SuccessTracker

log = logging.getLogger("simulation.runner")

TERMINAL = {"succeeded", "failed", "timeout", "stopped", "error"}
JITTER_M = 0.03
SIM_STEP_S = 0.05
RECORD_EVERY = 4  # sim steps are 50 ms -> 5 fps video; the same frames feed Dream-1 (rendered once)
VIDEO_FPS = 5
WALL_FACTOR = 10  # hard wall-clock cap per attempt: 10x timeout_s (software rendering is slower than real time)
WARMING_CAP_S = 3600  # a fine-tune may take up to 1 h to start
REHOME_STEPS = 20  # 1 s of sim time to drive both arms back to home before a new attempt
HOME = np.r_[np.zeros(6), 1.0]  # six joints at zero, gripper open


class RunInterrupted(Exception):
    """Raised inside the sim loop to end a run (or an attempt) early."""

    def __init__(self, status: str, reason: str = "", error: str | None = None):
        super().__init__(status)
        self.status, self.reason, self.error = status, reason, error


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class RunSpec:
    skill: Skill
    mode: str  # "mock" | "dream"
    prompt: str
    checkpoint: str
    timeout_s: float  # simulated seconds per attempt
    seed: int
    record_video: bool = True
    max_attempts: int = 1
    recovery: str = "rehome"  # "rehome" | "continue"
    recovery_prompts: list[str] = field(default_factory=list)
    eval_id: str | None = None

    def prompt_for(self, attempt: int) -> str:
        """Attempt 0 uses the prompt; attempt k uses recovery_prompts[k-1] when given, else the prompt again."""
        if attempt == 0 or attempt - 1 >= len(self.recovery_prompts):
            return self.prompt
        return self.recovery_prompts[attempt - 1]


class Run:
    def __init__(self, spec: RunSpec):
        self.spec = spec
        self.run_id = "run_" + uuid.uuid4().hex[:8]
        self.status = "queued"
        self.success: bool | None = None
        self.success_detail: dict = {}
        self.attempts: list[dict] = []
        self.created_at = now()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.duration_s: float | None = None
        self.api_calls = 0
        self.error: str | None = None
        self.video_path: Path | None = None
        self.stop_event = threading.Event()

    @property
    def cost_usd(self) -> float:
        if self.spec.mode == "mock":
            return 0.0
        return round(self.api_calls * config.price_per_call(self.spec.checkpoint), 4)

    def public(self) -> dict:
        s = self.spec
        return {
            "run_id": self.run_id,
            "skill": s.skill.name,
            "mode": s.mode,
            "prompt": s.prompt,
            "checkpoint": s.checkpoint if s.mode == "dream" else None,
            "seed": s.seed,
            "timeout_s": s.timeout_s,
            "max_attempts": s.max_attempts,
            "recovery": s.recovery if s.max_attempts > 1 else None,
            "eval_id": s.eval_id,
            "status": self.status,
            "success": self.success,
            "success_detail": self.success_detail,
            "attempts": self.attempts,
            "attempts_used": len(self.attempts),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": self.duration_s,
            "api_calls": self.api_calls,
            "cost_usd": self.cost_usd,
            "cost_is_estimate": True,
            "error": self.error,
            "video_url": f"/runs/{self.run_id}/video" if self.video_path else None,
        }


class Recorder:
    """Collects video frames (top camera over both wrist cameras) and keeps the newest top view as JPEG."""

    def __init__(self, keep_video: bool, on_frame):
        self.keep_video = keep_video
        self.frames: list[np.ndarray] = []
        self.on_frame = on_frame

    def add(self, images: dict) -> None:
        top = images["top"]
        if self.keep_video:
            wrists = np.concatenate([images["left"][::2, ::2], images["right"][::2, ::2]], axis=1)
            self.frames.append(np.concatenate([top, wrists], axis=0))
        buffer = io.BytesIO()
        Image.fromarray(top).save(buffer, format="JPEG", quality=80)
        self.on_frame(buffer.getvalue())

    def write(self, path: Path) -> Path | None:
        if not self.frames:
            return None
        import av

        with av.open(str(path), "w") as container:
            stream = container.add_stream("h264", rate=VIDEO_FPS)
            stream.height, stream.width = self.frames[0].shape[:2]
            stream.pix_fmt = "yuv420p"
            for frame in self.frames:
                for packet in stream.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        return path


def jitter_scene(env, seed: int) -> None:
    """Move banana and apple up to +-3 cm, reproducibly per seed (evaluation seeds < 1000, training >= 1000)."""
    import mujoco

    rng = np.random.default_rng(seed)
    for fruit in ("banana", "apple"):
        env.data.joint(f"{fruit}_free").qpos[0:2] += rng.uniform(-JITTER_M, JITTER_M, size=2)
    mujoco.mj_forward(env.model, env.data)


class RunManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.active: Run | None = None
        self.runs: dict[str, Run] = {}
        self.history: list[dict] = []  # finished runs from earlier service starts
        self.latest_jpeg: bytes | None = None
        config.ensure_dirs()
        for path in sorted(config.RUNS_DIR.glob("run_*.json")):
            try:
                self.history.append(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError):
                log.warning("unreadable run record %s", path)

    # ---- public API ----------------------------------------------------------------------------------------
    def start(self, spec: RunSpec) -> Run:
        with self.lock:
            if self.active is not None and self.active.status not in TERMINAL:
                raise BusyError(self.active.run_id)
            run = Run(spec)
            self.runs[run.run_id] = run
            self.active = run
        threading.Thread(target=self._execute, args=(run,), name=run.run_id, daemon=True).start()
        return run

    def busy(self) -> bool:
        return self.active is not None and self.active.status not in TERMINAL

    def get(self, run_id: str) -> dict | None:
        if run_id in self.runs:
            return self.runs[run_id].public()
        return next((r for r in self.history if r["run_id"] == run_id), None)

    def video_path(self, run_id: str) -> Path | None:
        path = config.RUNS_DIR / f"{run_id}.mp4"
        run = self.runs.get(run_id)
        if run is not None and run.status not in TERMINAL:
            return None
        return path if path.exists() else None

    def list(self, limit: int = 50) -> list[dict]:
        current = [r.public() for r in self.runs.values()]
        known = {r["run_id"] for r in current}
        merged = current + [r for r in self.history if r["run_id"] not in known]
        return sorted(merged, key=lambda r: r["created_at"], reverse=True)[:limit]

    def stop(self, run_id: str) -> Run:
        run = self.runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        if run.status in TERMINAL:
            raise AlreadyFinishedError(run_id)
        run.stop_event.set()
        return run

    def spent_usd(self) -> float:
        """Estimated Dream spend of every run this service has recorded (survives restarts via data/runs)."""
        current = sum(r.cost_usd for r in self.runs.values())
        earlier = sum(h.get("cost_usd", 0.0) for h in self.history if h["run_id"] not in self.runs)
        return round(current + earlier, 4)

    def budget(self) -> dict:
        spent = self.spent_usd()
        return {"budget_usd": config.BUDGET_USD, "spent_usd": spent,
                "remaining_usd": round(max(0.0, config.BUDGET_USD - spent), 4),
                "price_per_call_usd": config.PRICE_PER_CALL_USD, "is_estimate": True}

    def preview_jpeg(self) -> bytes:
        """Newest frame of the current/last run, or a fresh render of the start scene."""
        if self.latest_jpeg is not None:
            return self.latest_jpeg
        config.import_example()
        from yam_env import YamEnv

        env = YamEnv()
        renderer = SmallRenderer(env.model, shadows=config.RENDER_SHADOWS)
        try:
            buffer = io.BytesIO()
            Image.fromarray(renderer.views(env.data)["top"]).save(buffer, format="JPEG", quality=80)
            self.latest_jpeg = buffer.getvalue()
        finally:
            renderer.close()
            env.close()
        return self.latest_jpeg

    # ---- execution -----------------------------------------------------------------------------------------
    def _set_frame(self, jpeg: bytes) -> None:
        self.latest_jpeg = jpeg

    def _execute(self, run: Run) -> None:
        started = time.monotonic()
        run.started_at = now()
        final = "error"
        recorder = Recorder(run.spec.record_video, self._set_frame)
        try:
            config.import_example()
            os.chdir(config.WORK_DIR)  # the example writes relative paths (mock_results/)
            if run.spec.mode == "mock":
                final = self._run_mock(run, recorder, started)
            else:
                final = self._run_dream(run, recorder)
        except RunInterrupted as interrupted:
            final = interrupted.status
            run.success = False
            run.error = interrupted.error
        except Exception as error:  # every failure ends up in the run record, never in a crash (N4)
            log.exception("run %s failed", run.run_id)
            final = "error"
            run.success = False
            run.error = _describe(error)
        finally:
            run.status = "finalizing"  # writing video and run record
            run.duration_s = round(time.monotonic() - started, 2)
            run.finished_at = now()
            try:
                run.video_path = recorder.write(config.RUNS_DIR / f"{run.run_id}.mp4")
            except Exception as error:
                log.warning("video for %s not written: %s", run.run_id, error)
            run.status = final  # terminal only once video and record are written
            (config.RUNS_DIR / f"{run.run_id}.json").write_text(json.dumps(run.public(), indent=2))
            log.info("run %s %s success=%s calls=%s", run.run_id, run.status, run.success, run.api_calls)

    def _env_class(self, run: Run, recorder: Recorder, tracker_box: list, deadline_box: list):
        """A YamEnv that jitters the scene, records frames, tracks success and honours stop/timeouts."""
        from yam_env import YamEnv

        class RunEnv(YamEnv):
            def __init__(self):
                super().__init__()
                self.steps = 0
                self._small: SmallRenderer | None = None
                self._cached_step, self._cached = -1, None
                jitter_scene(self, run.spec.seed)
                tracker_box[0] = SuccessTracker(run.spec.skill, self)

            @property
            def sim_seconds(self) -> float:
                return self.steps * SIM_STEP_S

            def images(self):
                """320x180 renders (app/render.py), at most once per sim step."""
                if self._cached_step == self.steps:
                    return self._cached
                if self._small is None:
                    self._small = SmallRenderer(self.model, shadows=config.RENDER_SHADOWS)
                self._cached_step, self._cached = self.steps, self._small.views(self.data)
                return self._cached

            def close(self):
                if self._small is not None:
                    self._small.close()
                    self._small = None
                super().close()

            def step(self, left, right):
                if run.stop_event.is_set():
                    raise RunInterrupted("stopped")
                sim_deadline, wall_deadline = deadline_box
                if sim_deadline is not None and self.sim_seconds > sim_deadline:
                    raise RunInterrupted("timeout", reason="sim")
                if time.monotonic() > wall_deadline:
                    raise RunInterrupted("timeout", reason="wall")
                state = super().step(left, right)
                self.steps += 1
                tracker_box[1] = tracker_box[0].update(self) or tracker_box[1]
                if self.steps % RECORD_EVERY == 0:
                    recorder.add(self.images())
                return state

        return RunEnv

    def _run_mock(self, run: Run, recorder: Recorder, started: float) -> str:
        import mock_pickups

        spec = run.spec
        if not spec.skill.mock_available:
            raise ValueError(f"skill {spec.skill.name} has no scripted (mock) version")
        tracker_box = [None, False]
        deadline_box = [spec.timeout_s, started + WALL_FACTOR * spec.timeout_s]
        run.status = "running"
        run.attempts.append({"attempt": 1, "prompt": None, "api_calls": 0, "success": False})
        mock_pickups.YamEnv = self._env_class(run, recorder, tracker_box, deadline_box)
        result = mock_pickups.run_trial(spec.skill.obj, yaw=spec.skill.mock_yaw)
        run.success = bool(result["passed"])
        run.attempts[0]["success"] = run.success
        run.success_detail = {k: result[k] for k in ("lift_m", "tcp_distance_m", "release_drop_m") if k in result}
        return "succeeded" if run.success else "failed"

    def _run_dream(self, run: Run, recorder: Recorder) -> str:
        import dream_control as dc

        spec = run.spec
        key = os.environ.get("DREAM_API_KEY", "")
        if not key:
            raise RuntimeError("DREAM_API_KEY is not set")
        gateway = os.environ.get("DREAM_GATEWAY_URL", "https://api.dreamlabs.ai")
        tracker_box = [None, False]
        deadline_box = [None, time.monotonic() + WARMING_CAP_S]
        env = self._env_class(run, recorder, tracker_box, deadline_box)()
        policy = None
        windows = {name: deque(maxlen=dc.FRAMES) for name in dc.VIDEO_ROLES}

        def capture(keep: bool) -> None:
            if not keep:
                return
            for name, rgb in env.images().items():
                buffer = io.BytesIO()
                Image.fromarray(rgb).resize(dc.FRAME_SIZE, Image.BILINEAR).save(buffer, "JPEG", quality=85)
                windows[name].append(base64.b64encode(buffer.getvalue()).decode("ascii"))

        def succeeded() -> str:
            run.success = True
            run.success_detail = tracker_box[0].detail(env)
            return "succeeded"

        try:
            while any(len(w) < dc.FRAMES for w in windows.values()):  # fill the 9-frame windows, arms holding
                state = env.state()
                env.step(state["left"], state["right"])
                capture(env.steps % dc.FRAME_EVERY_STEPS == 0)

            poses = spec.checkpoint in dc.POSE_MODELS
            run.status = "warming"
            policy = dc.open_policy(dc.policy_config(spec.checkpoint, gateway, poses), key)
            for attempt in range(spec.max_attempts):
                prompt = spec.prompt_for(attempt)
                record = {"attempt": attempt + 1, "prompt": prompt, "api_calls": 0, "sim_seconds": 0.0,
                          "success": False}
                run.attempts.append(record)
                if attempt > 0:  # new attempt: optionally re-home, then a fresh Dream episode with the new prompt
                    deadline_box[0] = None
                    if spec.recovery == "rehome":
                        self._rehome(env, capture, dc.FRAME_EVERY_STEPS)
                    policy = _new_episode(policy, dc, spec.checkpoint, gateway, poses, key)
                start_sim = env.sim_seconds
                try:
                    poses, policy = self._attempt(run, env, policy, windows, capture, prompt, poses, record,
                                                  deadline_box, tracker_box, dc, gateway, key)
                except RunInterrupted as interrupted:
                    record["sim_seconds"] = round(env.sim_seconds - start_sim, 2)
                    if interrupted.status == "timeout" and interrupted.reason == "sim" \
                            and attempt + 1 < spec.max_attempts:
                        continue  # next attempt
                    run.success_detail = tracker_box[0].detail(env)
                    raise
                record["sim_seconds"] = round(env.sim_seconds - start_sim, 2)
                record["success"] = True
                return succeeded()
            run.success_detail = tracker_box[0].detail(env)
            return "timeout"
        finally:
            if policy is not None:
                try:
                    policy.close()
                except Exception:
                    log.warning("Dream session release failed; it will expire on the server")
            env.close()

    def _attempt(self, run, env, policy, windows, capture, prompt, poses, record, deadline_box, tracker_box, dc,
                 gateway, key):
        """One prompt attempt: call Dream-1 chunk by chunk until the sim says success or the attempt times out."""
        spec = run.spec
        dc.feed(policy, env, windows, prompt, spec.checkpoint, env.steps, every=0, station=poses)
        restarts, last_call, answered = 0, 0.0, False
        while True:
            if run.stop_event.is_set():
                raise RunInterrupted("stopped")
            if deadline_box[0] is not None and env.sim_seconds > deadline_box[0]:
                raise RunInterrupted("timeout", reason="sim")
            if time.monotonic() > deadline_box[1]:
                raise RunInterrupted("timeout", reason="wall")
            if self.spent_usd() + config.price_per_call(spec.checkpoint) > config.BUDGET_USD:
                raise RunInterrupted("stopped", error=f"budget_exhausted: service budget {config.BUDGET_USD} USD")
            time.sleep(max(0.0, config.MIN_CALL_INTERVAL_S - (time.monotonic() - last_call)))
            last_call = time.monotonic()
            try:
                reply = policy.get_action()
            except Exception as error:
                code = getattr(error, "code", None) or getattr(error, "reason", None)
                if code == "pool_warming":  # the model is starting; not counted against timeout_s
                    run.status = "warming"
                    time.sleep(min(float(getattr(error, "retry_after_s", 10) or 10), 30))
                    continue
                if type(error).__name__ == "DreamSessionExpired" and restarts < 3:
                    restarts += 1
                    continue
                if not poses and dc.needs_poses(error):
                    policy.close()
                    poses = True
                    policy = dc.open_policy(dc.policy_config(spec.checkpoint, gateway, poses), key)
                    dc.feed(policy, env, windows, prompt, spec.checkpoint, env.steps, every=0, station=poses)
                    continue
                raise
            restarts = 0
            run.api_calls += 1
            record["api_calls"] += 1
            if not answered:  # timeout_s counts simulated seconds from the first answer of this attempt
                answered = True
                run.status = "running"
                deadline_box[0] = env.sim_seconds + spec.timeout_s
                deadline_box[1] = time.monotonic() + WALL_FACTOR * spec.timeout_s
            left, right = dc.validate_chunk(env, reply, 48, verbose=False)
            for l_row, r_row in zip(left, right):
                tick = time.monotonic()
                env.step(l_row, r_row)
                keep = env.steps % dc.FRAME_EVERY_STEPS == 0  # same steps the recorder renders: cached
                capture(keep)
                if keep:
                    dc.feed(policy, env, windows, prompt, spec.checkpoint, env.steps, station=poses)
                if tracker_box[1]:
                    return poses, policy
                time.sleep(max(0.0, SIM_STEP_S - (time.monotonic() - tick)))  # real-time pacing, 20 Hz

    def _rehome(self, env, capture, frame_every: int) -> None:
        """Drive both arms back to home (grippers open) over REHOME_STEPS sim steps."""
        state = env.state()
        start_l, start_r = state["left"].copy(), state["right"].copy()
        for i in range(1, REHOME_STEPS + 1):
            alpha = i / REHOME_STEPS
            left = start_l + (HOME - start_l) * alpha
            right = start_r + (HOME - start_r) * alpha
            left[6] = right[6] = 1.0
            env.step(left, right)
            capture(env.steps % frame_every == 0)


def _new_episode(policy, dc, checkpoint, gateway, poses, key):
    """A fresh Dream episode (new session) for the next attempt."""
    reset = getattr(policy, "reset_episode", None)
    if callable(reset):
        reset()
        return policy
    policy.close()
    return dc.open_policy(dc.policy_config(checkpoint, gateway, poses), key)


def _describe(error: Exception) -> str:
    reason = getattr(error, "reason", None) or getattr(error, "code", None)
    if reason == "over_cap":
        return "dream_over_cap: the Dream Labs account passed its monthly budget cap (raise it on Billing)"
    return f"{type(error).__name__}: {str(error)[:300]}"


class BusyError(Exception):
    def __init__(self, active_run_id: str):
        super().__init__(active_run_id)
        self.active_run_id = active_run_id


class AlreadyFinishedError(Exception):
    pass


def skill_or_none(name: str) -> Skill | None:
    return SKILLS.get(name)
