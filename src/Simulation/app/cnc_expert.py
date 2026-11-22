"""Collision-aware scripted expert for the CNC cell: demonstrations for fine-tuning the robot type.

No fixed trajectory: every episode is planned anew from the randomized scene (part pose, approach heights, speed).
Each waypoint is solved by IK over several grasp orientations; a candidate is accepted only if the joint-space path
from the previous configuration is free of contacts between the arm and the cell (machine, door, belts, table,
other parts). During execution contacts are monitored again; an episode is valid only if the task goal is met in
MuJoCo AND the arm never touched the cell.

Tasks (robot type yam-sim; two separate cells = two experiments):
  sort_round   conveyor cell, right arm: round part stopped at the right station -> green box
  sort_cube    conveyor cell, left arm: cube stopped at the left station -> blue KLT
  cnc_load     cnc cell, left arm: raw part from the staging plate onto the machine's transfer tray
  cnc_unload   cnc cell, right arm: finished part from the transfer tray into the finished-parts box
"""

from dataclasses import dataclass, field

import mujoco
import numpy as np

from .cnc import (FIN_BOX, FIN_HALF_H, KLT_HALF, PARK, RAW_HALF, RAW_STAGE, SEAT_Z, SORT_BOX, STAGE_TOP, TABLE_Z,
                  TRAY_OUT, CellController)

TASKS = {
    "sort_round": {"cell": "conveyor", "arm": "right", "part": "cyl_part_0", "target": SORT_BOX["right"],
                   "rest_z": TABLE_Z + 0.008 + FIN_HALF_H, "radius": 0.045,
                   "prompt": "put the round part from the conveyor in the green box"},
    "sort_cube": {"cell": "conveyor", "arm": "left", "part": "raw_part_0", "target": SORT_BOX["left"],
                  "rest_z": TABLE_Z + 0.008 + RAW_HALF[2], "radius": 0.045,
                  "prompt": "put the metal cube from the conveyor in the blue box"},
    "cnc_load": {"cell": "cnc", "arm": "left", "part": "raw_part_0", "target": TRAY_OUT,
                 "rest_z": SEAT_Z + RAW_HALF[2], "radius": 0.035,
                 "prompt": "put the metal block on the machine tray"},
    "cnc_unload": {"cell": "cnc", "arm": "right", "part": "fin_part_0", "target": FIN_BOX,
                   "rest_z": TABLE_Z + 0.008 + FIN_HALF_H, "radius": 0.04,
                   "prompt": "put the finished part in the green box"},
}
# Transfer test (22.11.): similar but untrained tasks. Kept out of TASKS so recording, the queue's evaluations
# and the reports (which iterate TASKS) stay unchanged; look tasks up by name in ALL_TASKS.
TRANSFER_TASKS = {
    "cnc_return": {"cell": "cnc", "arm": "left", "part": "raw_part_0", "target": RAW_STAGE,
                   "rest_z": STAGE_TOP + RAW_HALF[2], "radius": 0.03,
                   "prompt": "put the metal block from the machine tray on the grey stand"},
}
ALL_TASKS = TASKS | TRANSFER_TASKS
PENETRATION_M = 0.0005  # executed motion: any real contact deeper than this counts as a collision
CLEARANCE_M = 0.006  # planning: poses and paths must keep this distance from the cell


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
    grasp_err_m: float = -1.0  # TCP distance to the planned grasp point after the approach (servo tracking)

    def public(self) -> dict:
        return {"task": self.task, "seed": self.seed, "passed": self.passed, "reason": self.reason,
                "collisions": self.collisions[:5], "steps": self.steps, "part_end": self.part_end,
                "max_lift_m": round(self.max_lift_m, 3), "grasp_err_m": round(self.grasp_err_m, 4)}


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
        flags, margins = m.opt.disableflags, m.geom_margin.copy()
        m.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONSTRAINT  # contacts are detected, no solver arena
        m.geom_margin[:] = CLEARANCE_M  # report near misses too, so the plan keeps a clearance
        try:
            mujoco.mj_forward(m, d)
        finally:
            m.opt.disableflags, m.geom_margin[:] = flags, margins
        return d

    def collisions(self, q, allow=(), clearance: float = CLEARANCE_M) -> list[str]:
        """Arm-vs-cell contacts (closer than `clearance`) at configuration q. `allow`: bodies the arm may touch."""
        m, d = self.env.model, self._forward(q)
        allowed = {m.body(n).id for n in allow}
        hits = []
        for k in range(d.ncon):
            con = d.contact[k]
            b1, b2 = m.geom_bodyid[con.geom1], m.geom_bodyid[con.geom2]
            if (b1 in self.robot) == (b2 in self.robot) or con.dist > clearance:
                continue
            arm, other = (b1, con.geom2) if b1 in self.robot else (b2, con.geom1)
            if m.geom_bodyid[other] in allowed:
                continue
            hits.append(f"{m.body(arm).name}~{m.geom(other).name or m.body(m.geom_bodyid[other]).name}")
        return hits

    def touching(self, allow=()) -> list[str]:
        """Real contacts of the arm with the cell in the live simulation state (executed motion)."""
        m, d = self.env.model, self.env.data
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

    def path_free(self, q0, q1, allow=(), n=28) -> bool:
        return all(not self.collisions(q0 + (q1 - q0) * a, allow) for a in np.linspace(0, 1, n)[1:])

    def reach(self, q_from, target, yaws, allow=(), pitches=(0.0, 0.3, -0.3)) -> np.ndarray:
        """A collision-free IK solution for target whose straight joint path from q_from is also free."""
        best, why = None, {"ik": 0, "pose": 0, "path": 0}
        for yaw in yaws:
            for pitch in pitches:
                m = self.env.model
                flags = m.opt.disableflags
                m.opt.disableflags |= mujoco.mjtDisableBit.mjDSBL_CONSTRAINT  # IK is kinematics: no solver arena
                try:
                    q = self.solve(self.env, self.side, np.asarray(target, float), rotation(yaw, pitch), q_from)
                except ValueError:
                    why["ik"] += 1
                    continue
                finally:
                    m.opt.disableflags = flags
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
        hits = self.planner.touching(self.allow)
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


def prepare_scene(env, task: str, rng: np.random.Generator, ctrl: CellController) -> None:
    """Randomize the start state for this task (seeded)."""
    d = env.data
    spec = ALL_TASKS[task]
    if task in ("cnc_load", "cnc_return"):
        d.joint("fin_part_0_free").qpos[:3] = PARK  # tray empty: the machine waits for a raw part
    q = d.joint(f"{spec['part']}_free").qpos
    if task == "cnc_return":  # reverse of cnc_load: the raw part starts on the tray, the stand is empty
        q[:3] = [TRAY_OUT[0], TRAY_OUT[1], SEAT_Z + RAW_HALF[2] + 0.001]
    if spec["cell"] == "conveyor":  # single-task run: only this arm's kind on the belt, lateral jitter
        own = "cyl_part" if spec["arm"] == "right" else "raw_part"
        x = -0.30
        for i in range(env.model.nbody):
            name = env.model.body(i).name or ""
            if name.startswith(("raw_part", "cyl_part")):
                j = d.joint(f"{name}_free")
                if name.startswith(own):
                    j.qpos[0] = x
                    j.qpos[1] += rng.uniform(-0.01, 0.01)
                    x -= 0.13
                else:
                    j.qpos[:3] = PARK
    else:
        q[0:2] += rng.uniform(-0.008, 0.008, size=2)
    yaw = rng.uniform(-0.25, 0.25)
    q[3:7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
    mujoco.mj_forward(env.model, d)
    if ctrl.has_machine:
        ctrl.door, ctrl.door_target = 1.0, 1.0  # machine finished, door open
        ctrl.set_light("green")


def task_done(env, task: str, ctrl: CellController | None = None, part: str | None = None) -> bool:
    """Part resting inside the target zone at its resting height (released and still)."""
    spec = ALL_TASKS[task]
    body = env.data.body(part or spec["part"])
    p = body.xpos
    if spec["cell"] == "conveyor":  # inside the box's walls (the part may slide to a wall after release)
        d = np.abs(p[:2] - spec["target"])
        inside = bool(d[0] < KLT_HALF[0] - 0.006 and d[1] < KLT_HALF[1] - 0.006)
    else:
        inside = np.linalg.norm(p[:2] - spec["target"]) < spec["radius"]
    still = float(np.linalg.norm(body.cvel[3:])) < 0.05
    if spec["cell"] == "conveyor":  # into a box: anywhere below the rim counts, also on top of earlier parts
        resting = spec["rest_z"] - 0.012 < p[2] < TABLE_Z + 0.07 and still
    else:
        resting = abs(p[2] - spec["rest_z"]) < 0.012 and still
    return bool(inside and resting)


def run_episode(env, task: str, seed: int, ctrl: CellController | None = None, fresh: bool = True,
                part: str | None = None) -> Episode:
    """Plan and execute one demonstration. fresh=True randomizes a freshly reset cell; fresh=False continues the
    current cell state (e.g. unloading the part the machine just finished). The caller records frames via env.step."""
    spec = dict(ALL_TASKS[task])
    if part:
        spec["part"] = part
    rng = np.random.default_rng(seed)
    ep = Episode(task, seed)
    ctrl = ctrl or CellController(env)
    if fresh:
        prepare_scene(env, task, rng, ctrl)
    home = np.r_[np.zeros(6), 1.0]
    planner = Planner(env, spec["arm"], rng)
    run = CellRun(env, ctrl, planner, home)
    if spec["cell"] == "conveyor":  # the belt runs until a part of this arm's kind reaches its station
        ctrl.in_belt_on = True
        for _ in range(600):
            w = ctrl.waiting()
            if w and w[0] == spec["arm"]:
                spec["part"] = w[1]
                break
            run.hold(1)
        else:
            ep.reason = "no part of this kind reached the station"
    run.hold(int(rng.integers(6, 12)))
    if ep.reason:
        return ep
    part = spec["part"]
    p = env.data.body(part).xpos.copy()  # noqa: F841 (re-read below after the hold)
    run.watch, run.watch_z0 = part, float(p[2])
    drop = {"cnc_load": 0.012, "cnc_return": 0.012, "cnc_unload": 0.035}.get(task, 0.05)
    yaws = (0.0, np.pi / 2)  # into a crate: release above the walls' reach of the fingers
    goal_xy = spec["target"] + rng.uniform(-0.008, 0.008, size=2)
    if spec["cell"] == "conveyor":  # pick the free slot in the box (farthest from parts already in it)
        slots = [spec["target"] + np.array(o) for o in ((-0.024, -0.017), (0.024, -0.017), (-0.024, 0.017), (0.024, 0.017))]
        others = [env.data.body(i).xpos[:2].copy() for i in range(env.model.nbody)
                  if (env.model.body(i).name or "").startswith(("raw_part", "cyl_part"))
                  and env.model.body(i).name != part
                  and np.linalg.norm(env.data.body(i).xpos[:2] - spec["target"]) < 0.08]
        goal_xy = max(slots, key=lambda sl: min([float(np.linalg.norm(sl - o)) for o in others] or [1.0]))
    target = np.r_[goal_xy, spec["rest_z"] + drop]
    speed = rng.uniform(0.85, 1.2)
    n = lambda base: max(8, int(base * speed))  # noqa: E731
    yaws = (0.0, np.pi / 2)
    grip_dz = 0.006 if part.startswith("raw") else 0.004
    try:
        h = rng.uniform(0.06, 0.09)
        run.go(planner.reach(run.q, p + [0, 0, h], yaws), n(35))
        grasp = p + [0, 0, grip_dz]
        run.go(planner.reach(run.q, grasp, yaws, allow=(part,)), n(25))
        run.hold(4)
        ep.grasp_err_m = float(np.linalg.norm(env.data.site(f"{spec['arm']}_tcp").xpos - grasp))
        if ep.grasp_err_m > 0.02:  # blocked: list every contact of the arm, however shallow
            m, d = env.model, env.data
            for k in range(d.ncon):
                c = d.contact[k]
                b1, b2 = m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]
                if (b1 in planner.robot) != (b2 in planner.robot) or (b1 in planner.robot and b2 in planner.robot
                                                                       and m.body(b1).name[:4] != m.body(b2).name[:4]):
                    ep.collisions.append(f"touch {m.body(b1).name}~{m.body(b2).name} {c.dist:.4f}")
        run.allow = (part,)
        run.grip(0.0, 18)
        run.go(planner.reach(run.q, p + [0, 0, h + 0.03], yaws, allow=(part,)), n(25))
        above = 0.06 if spec["cell"] == "conveyor" else h + 0.03  # boxes sit close to the base: stay low
        run.go(planner.reach(run.q, target + [0, 0, above], yaws, allow=(part,)), n(45))
        run.go(planner.reach(run.q, target, yaws, allow=(part,)), n(25))
        run.grip(1.0, 15)
        run.allow = ()
        run.hold(6)
        run.go(planner.reach(run.q, target + [0, 0, above], yaws), n(25))
        run.go(planner.reach(run.q, run_retreat(env, planner), yaws), n(30))
        run.hold(10)
    except PlanError as error:
        ep.reason = f"plan: {error}"
    ep.steps = run.steps
    ep.collisions = run.hits + ep.collisions
    ep.part_end = np.round(env.data.body(part).xpos, 3).tolist()
    ep.max_lift_m = run.max_lift
    done = task_done(env, task, ctrl, part)
    if not ep.reason:
        ep.reason = "ok" if done and not run.hits else ("collision" if run.hits else "goal not reached")
    ep.passed = bool(done and not run.hits and ep.reason == "ok")
    return ep


def run_retreat(env, planner: Planner) -> np.ndarray:
    """Back out to a safe point in front of the machine on the arm's own side."""
    sgn = 1.0 if planner.side == "left" else -1.0
    return np.array([sgn * 0.22, 0.06, 0.92])


def run_cnc_demo(env, ctrl: CellController, seed: int) -> list[dict]:
    """One continuous CNC process in a single scene: load, machine cycle (door, tray, light), unload.

    The cycle only starts if the load was verified (part resting on the tray, arm clear); otherwise the light
    turns red and the process stops: the success gate the orchestrator relies on.
    """
    log = []
    load = run_episode(env, "cnc_load", seed, ctrl)
    log.append(load.public())
    if not load.passed or not ctrl.part_on_tray("raw_part"):
        ctrl.set_light("red")
        log.append({"event": "gate", "passed": False, "reason": "load not verified: machine stays locked"})
        return log
    log.append({"event": "gate", "passed": True, "reason": "raw part on tray, arm clear: cycle released"})
    home = np.r_[np.zeros(6), 1.0]
    ctrl.start_cycle()
    for _ in range(400):
        ctrl.step()
        env.step(home, home)
        if ctrl.machine_done:
            break
    finished = ctrl.part_on_tray("fin_part")
    log.append({"event": "cycle", "done": ctrl.machine_done, "finished_part": finished})
    if finished:
        log.append(run_episode(env, "cnc_unload", seed, ctrl, fresh=False, part=finished).public())
    return log
