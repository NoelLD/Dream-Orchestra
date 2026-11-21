"""Collision-aware scripted expert for the CNC cell: demonstrations for fine-tuning the robot type.

No fixed trajectory: every episode is planned anew from the randomized scene (part pose, approach heights, speed).
Each waypoint is solved by IK over several grasp orientations; a candidate is accepted only if the joint-space path
from the previous configuration is free of contacts between the arm and the cell (machine, door, belts, table,
other parts). During execution contacts are monitored again; an episode is valid only if the task goal is met in
MuJoCo AND the arm never touched the cell.

Tasks (both on robot type yam-sim, one dataset holds both, each episode with its own prompt):
  load    left arm: raw part from the in-feed belt into the vise
  unload  right arm: finished part from the vise onto the out-feed belt
"""

from dataclasses import dataclass, field

import mujoco
import numpy as np

from .cnc import (BELT_TOP, FIN_HALF_H, IN_BELT_X, OUT_BELT_X, RAW_HALF, SEAT_Z, VISE, CellController)

TASKS = {
    "load": {"arm": "left", "part": "raw_part_0", "prompt": "load the raw part from the conveyor into the machine"},
    "unload": {"arm": "right", "part": "fin_part_0", "prompt": "unload the finished part onto the conveyor"},
}
OUT_PLACE = np.array([OUT_BELT_X, -0.13])
PENETRATION_M = 0.002  # contacts deeper than this count as a collision


class PlanError(Exception):
    pass


@dataclass
class Episode:
    task: str
    seed: int
    passed: bool = False
    reason: str = ""
    collisions: list = field(default_factory=list)
    steps: int = 0
    part_end: list = field(default_factory=list)
    max_lift_m: float = 0.0

    def public(self) -> dict:
        return {"task": self.task, "seed": self.seed, "passed": self.passed, "reason": self.reason,
                "collisions": self.collisions[:5], "steps": self.steps, "part_end": self.part_end,
                "max_lift_m": round(self.max_lift_m, 3)}


def rotation(yaw: float, pitch: float = 0.0) -> np.ndarray:
    """Gripper pointing down, turned by yaw about z, then tilted by pitch about the world x axis."""
    c, s = np.cos(yaw), np.sin(yaw)
    down = np.array([[c, s, 0], [s, -c, 0], [0, 0, -1.0]])
    cp, sp = np.cos(pitch), np.sin(pitch)
    return np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ down


class Planner:
    def __init__(self, env, side: str, rng: np.random.Generator):
        from mock_pickups import solve  # the example's damped least-squares IK

        self.solve = solve
        self.env, self.side, self.rng = env, side, rng
        m = env.model
        self.ids = [m.joint(f"{side}_joint{i}").id for i in range(1, 7)]
        self.qadr = m.jnt_qposadr[self.ids]
        self.limits = m.jnt_range[self.ids]
        self.robot = {i for i in range(m.nbody) if (m.body(i).name or "").startswith(("left_", "right_"))}
        self.scratch = mujoco.MjData(m)

    def _forward(self, q, held=None):
        m, d = self.env.model, self.scratch
        mujoco.mj_copyData(d, m, self.env.data)
        d.qpos[self.qadr] = q
        flags = m.opt.disableflags
        m.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONSTRAINT  # contacts are detected, no solver arena
        try:
            mujoco.mj_forward(m, d)
        finally:
            m.opt.disableflags = flags
        return d

    def collisions(self, q, allow=()) -> list[str]:
        """Arm-vs-cell contacts at configuration q. `allow`: body names the arm may touch (the gripped part)."""
        m, d = self.env.model, self._forward(q)
        allowed = {m.body(n).id for n in allow}
        hits = []
        for k in range(d.ncon):
            con = d.contact[k]
            b1, b2 = m.geom_bodyid[con.geom1], m.geom_bodyid[con.geom2]
            if (b1 in self.robot) == (b2 in self.robot) or con.dist > -PENETRATION_M:
                continue
            arm, other = (b1, con.geom2) if b1 in self.robot else (b2, con.geom1)
            if m.geom_bodyid[other] in allowed:
                continue
            hits.append(f"{m.body(arm).name}~{m.geom(other).name or m.body(m.geom_bodyid[other]).name}")
        return hits

    def path_free(self, q0, q1, allow=(), n=16) -> bool:
        return all(not self.collisions(q0 + (q1 - q0) * a, allow) for a in np.linspace(0, 1, n)[1:])

    def reach(self, q_from, target, yaws, allow=(), pitches=(0.0, 0.3, -0.3)) -> np.ndarray:
        """A collision-free IK solution for target whose straight joint path from q_from is also free."""
        best, why = None, {"ik": 0, "pose": 0, "path": 0}
        for yaw in yaws:
            for pitch in pitches:
                try:
                    q = self.solve(self.env, self.side, np.asarray(target, float), rotation(yaw, pitch), q_from)
                except ValueError:
                    why["ik"] += 1
                    continue
                hits = self.collisions(q, allow)
                if hits:
                    why["pose"] += 1
                    why.setdefault("hit", hits[0])
                    continue
                if not self.path_free(q_from, q, allow):
                    why["path"] += 1
                    continue
                cost = float(np.abs(q - q_from).sum())
                if best is None or cost < best[0]:
                    best = (cost, q)
        if best is None:
            raise PlanError(f"no collision-free pose for {np.round(target, 3).tolist()}: {why}")
        return best[1]


class CellRun:
    """Executes a planned episode in the env and monitors arm-vs-cell contacts on every control step."""

    def __init__(self, env, ctrl: CellController, planner: Planner, home):
        self.env, self.ctrl, self.planner, self.home = env, ctrl, planner, home
        self.q = env.state()[planner.side][:6].copy()
        self.opening = 1.0
        self.hits: list[str] = []
        self.steps = 0
        self.allow: tuple = ()
        self.watch: str | None = None
        self.watch_z0 = 0.0
        self.max_lift = 0.0

    def command(self, q, opening):
        arm = np.r_[np.clip(q, self.planner.limits[:, 0], self.planner.limits[:, 1]), opening]
        return (arm, self.home) if self.planner.side == "left" else (self.home, arm)

    def _step(self, q, opening):
        self.ctrl.step()
        self.env.step(*self.command(q, opening))
        self.steps += 1
        if self.watch:
            self.max_lift = max(self.max_lift, float(self.env.data.body(self.watch).xpos[2]) - self.watch_z0)
        hits = self.planner.collisions(self.env.state()[self.planner.side][:6], self.allow)
        if hits:
            self.hits.extend(h for h in hits if h not in self.hits)

    def go(self, q_end, steps):
        start = self.q.copy()
        for a in np.linspace(0, 1, steps)[1:]:
            s = a * a * (3 - 2 * a)  # smooth start and stop
            self._step(start + (q_end - start) * s, self.opening)
        self.q = q_end

    def grip(self, opening, steps):
        for o in np.linspace(self.opening, opening, steps)[1:]:
            self._step(self.q, o)
        self.opening = opening

    def hold(self, steps):
        for _ in range(steps):
            self._step(self.q, self.opening)


def prepare_scene(env, task: str, rng: np.random.Generator) -> None:
    """Randomize the start state for this task (seeded): part poses, door open, vise empty for loading."""
    d = env.data
    if task == "load":
        # the vise is empty when the machine waits for a raw part: park the finished part off-table
        d.joint("fin_part_0_free").qpos[:3] = [0.9, 0.9, 0.05]
        q = d.joint("raw_part_0_free").qpos
        q[0] += rng.uniform(-0.008, 0.008)
        yaw = rng.uniform(-0.25, 0.25)
        q[3:7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
    else:
        q = d.joint("fin_part_0_free").qpos
        q[0:2] = VISE + rng.uniform(-0.006, 0.006, size=2)
    mujoco.mj_forward(env.model, d)


def task_done(env, task: str) -> bool:
    if task == "load":
        p = env.data.body("raw_part_0").xpos
        return bool(np.linalg.norm(p[:2] - VISE) < 0.025 and abs(p[2] - (SEAT_Z + RAW_HALF[2])) < 0.01)
    p = env.data.body("fin_part_0").xpos
    on_belt = abs(p[0] - OUT_BELT_X) < 0.045 and -0.55 < p[1] < -0.03
    return bool(on_belt and abs(p[2] - (BELT_TOP + FIN_HALF_H)) < 0.012)


def run_episode(env, task: str, seed: int, ctrl: CellController | None = None) -> Episode:
    """Plan and execute one demonstration in a freshly reset CNC env. The caller records frames via env.step."""
    spec = TASKS[task]
    rng = np.random.default_rng(seed)
    ep = Episode(task, seed)
    ctrl = ctrl or CellController(env)
    ctrl.door, ctrl.door_target = 1.0, 1.0  # machine finished, door already open
    ctrl.in_belt_on = task != "load"  # the in-feed waits while its front part is being picked
    ctrl.set_light("green")
    prepare_scene(env, task, rng)
    home = np.r_[np.zeros(6), 1.0]
    planner = Planner(env, spec["arm"], rng)
    run = CellRun(env, ctrl, planner, home)
    run.hold(int(rng.integers(6, 12)))
    part = spec["part"]
    p = env.data.body(part).xpos.copy()
    run.watch, run.watch_z0 = part, float(p[2])
    sgn = 1.0 if spec["arm"] == "left" else -1.0
    pre_door = np.array([sgn * rng.uniform(0.06, 0.10), rng.uniform(0.06, 0.10), rng.uniform(0.90, 0.94)])
    above_vise = np.r_[VISE, rng.uniform(0.86, 0.88)]  # top-down reach at x = 0 ends near y = -0.1 below z ~ 0.9
    speed = rng.uniform(0.85, 1.2)
    n = lambda base: max(8, int(base * speed))  # noqa: E731
    yaws_belt = (0.0, np.pi / 2)
    yaws_vise = (np.pi / 2, np.pi / 2 + 0.2, np.pi / 2 - 0.2)  # fingers close along y, clear of the jaws
    try:
        if task == "load":
            grasp_yaw = yaws_belt
            h = rng.uniform(0.06, 0.09)
            run.go(planner.reach(run.q, p + [0, 0, h], grasp_yaw), n(35))
            run.go(planner.reach(run.q, p + [0, 0, 0.006], grasp_yaw), n(25))
            run.allow = (part,)
            run.grip(0.0, 18)
            run.go(planner.reach(run.q, p + [0, 0, h + 0.02], grasp_yaw, allow=(part,)), n(25))
            run.go(planner.reach(run.q, pre_door, yaws_vise, allow=(part,)), n(45))
            run.go(planner.reach(run.q, above_vise, yaws_vise, allow=(part,)), n(35))
            seat = np.r_[VISE, SEAT_Z + RAW_HALF[2] + 0.012]
            run.go(planner.reach(run.q, seat, yaws_vise, allow=(part,)), n(30))
            run.grip(1.0, 15)
            run.allow = ()
            run.hold(8)
        else:
            run.go(planner.reach(run.q, pre_door, yaws_vise), n(40))
            run.go(planner.reach(run.q, np.r_[p[:2], above_vise[2]], yaws_vise), n(35))
            run.go(planner.reach(run.q, p + [0, 0, 0.004], yaws_vise), n(30))
            run.allow = (part,)
            run.grip(0.0, 18)
            run.go(planner.reach(run.q, np.r_[p[:2], above_vise[2]], yaws_vise, allow=(part,)), n(30))
            run.go(planner.reach(run.q, pre_door, yaws_vise, allow=(part,)), n(35))
            drop = np.r_[OUT_PLACE + rng.uniform(-0.01, 0.01, size=2), BELT_TOP + FIN_HALF_H + 0.015]
            run.go(planner.reach(run.q, drop + [0, 0, 0.08], yaws_belt, allow=(part,)), n(45))
            run.go(planner.reach(run.q, drop, yaws_belt, allow=(part,)), n(25))
            run.grip(1.0, 15)
            run.allow = ()
            run.hold(8)
        run.go(planner.reach(run.q, run_retreat(env, planner), (0.0, np.pi / 2)), n(30))
        run.hold(10)
    except PlanError as error:
        ep.reason = f"plan: {error}"
    ep.steps = run.steps
    ep.collisions = run.hits
    ep.part_end = np.round(env.data.body(part).xpos, 3).tolist()
    ep.max_lift_m = run.max_lift
    done = task_done(env, task)
    if not ep.reason:
        ep.reason = "ok" if done and not run.hits else ("collision" if run.hits else "goal not reached")
    ep.passed = bool(done and not run.hits and ep.reason == "ok")
    return ep


def run_retreat(env, planner: Planner) -> np.ndarray:
    """Back out to a safe point in front of the machine on the arm's own side."""
    sgn = 1.0 if planner.side == "left" else -1.0
    return np.array([sgn * 0.22, 0.06, 0.97])
