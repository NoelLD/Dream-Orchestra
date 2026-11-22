"""A live cell session for the control-room UI: one persistent scene (conveyor or CNC) stepping in real time.

Unlike /runs (a fresh scene per run), the session keeps its state: the door stays open, the tray stays in, parts
stay where they were put. The UI switches actuators, starts tasks and reads sensors and camera frames.
One session at a time; all MuJoCo work (physics, rendering) happens on the session's own thread.
Tasks run the scripted reference controller (mode "mock"); the motion source is reported with every result.
"""

import io
import logging
import queue
import threading
import time

import numpy as np
from PIL import Image

from . import config

log = logging.getLogger("simulation.cells")
STEP_S = 0.05  # one control step = 50 ms of simulated time
FRAME_EVERY = 4  # render every 4th step (5 fps): software rendering is the bottleneck


class CellSession:
    def __init__(self, cell: str):
        self.cell = cell
        self.started_at = time.time()
        self.commands: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.state: dict = {"cell": cell, "status": "starting"}
        self.frames: dict[str, bytes] = {}
        self.events: list[dict] = []
        self.busy: str | None = None
        self.auto = False  # conveyor: sort automatically whenever a part waits at its station
        self.thread = threading.Thread(target=self._loop, name=f"cell-{cell}", daemon=True)
        self.thread.start()

    # ---- API side (any thread) ------------------------------------------------------------------------------
    def submit(self, kind: str, **args) -> None:
        self.commands.put((kind, args))

    def public(self) -> dict:
        with self.lock:
            return dict(self.state) | {"busy": self.busy, "events": self.events[-20:]}

    def frame(self, view: str) -> bytes | None:
        with self.lock:
            return self.frames.get(view)

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=10)

    # ---- session thread -------------------------------------------------------------------------------------
    def _event(self, text: str, **data) -> None:
        with self.lock:
            self.events.append({"t": round(time.time() - self.started_at, 1), "text": text} | data)

    def _loop(self) -> None:
        config.import_example()
        import mujoco
        import yam_env

        from .cnc import CellController, cell_xml
        from .render import RENDER_CROP, RENDER_H, RENDER_W

        original = yam_env.build_xml
        yam_env.build_xml = lambda: cell_xml(original(), self.cell)
        try:
            env = yam_env.YamEnv()
        finally:
            yam_env.build_xml = original
        ctrl = CellController(env)
        if ctrl.has_machine:  # start state: machine idle and open, tray empty, raw part waiting on the stage
            from .cnc import PARK

            env.data.joint("fin_part_0_free").qpos[:3] = PARK
            mujoco.mj_forward(env.model, env.data)
            ctrl.door, ctrl.door_target = 1.0, 1.0
            ctrl.set_light("green")
        overview = mujoco.Renderer(env.model, height=288, width=512)
        robot = mujoco.Renderer(env.model, height=RENDER_H, width=RENDER_W)  # top camera only, like the run time
        for r in (overview, robot):
            r.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
            r.scene.flags[mujoco.mjtRndFlag.mjRND_REFLECTION] = False
        cam = mujoco.MjvCamera()
        cam.lookat[:] = [0.05, -0.05, 0.86]
        cam.distance, cam.azimuth, cam.elevation = 1.45, -150.0, -27.0
        home = np.r_[np.zeros(6), 1.0]
        steps = 0
        original_step = env.step

        def step(left, right):  # every env.step (idle or inside a task) publishes state and frames, paced
            nonlocal steps
            started = time.monotonic()
            out = original_step(left, right)
            steps += 1
            self._publish(ctrl, env, steps)
            if steps % FRAME_EVERY == 0:
                overview.update_scene(env.data, camera=cam)
                self._store("overview", overview.render())
                robot.update_scene(env.data, camera="top")
                self._store("robot", robot.render()[RENDER_CROP])
            time.sleep(max(0.0, STEP_S - (time.monotonic() - started)))  # real time for the viewer
            if self.stop_event.is_set():
                raise SessionClosed()
            return out

        env.step = step
        self._event(f"Zelle {self.cell} gestartet")
        try:
            while not self.stop_event.is_set():
                try:
                    kind, args = self.commands.get_nowait()
                except queue.Empty:
                    if self.auto and ctrl.sorting:
                        waiting = ctrl.waiting()
                        if waiting:
                            task = {"right": "sort_round", "left": "sort_cube"}[waiting[0]]
                            self._handle("task", {"task": task, "seed": 1000 + steps}, env, ctrl, home)
                            continue
                        if steps % 20 == 0 and ctrl.feed():
                            self._event("Neues Teil auf das Band gelegt")
                    ctrl.step()
                    env.step(home, home)
                    continue
                self._handle(kind, args, env, ctrl, home)
        except SessionClosed:
            pass
        except Exception as error:  # keep the API alive; report the failure in the state
            log.exception("cell session failed")
            with self.lock:
                self.state["status"] = "error"
                self.state["error"] = f"{type(error).__name__}: {error}"
        finally:
            overview.close()
            robot.close()
            env.close()

    def _handle(self, kind, args, env, ctrl, home) -> None:
        from .cnc_expert import TASKS, run_episode

        if kind == "action":
            action = args["action"]
            if action in ("door_open", "door_close") and ctrl.has_machine:
                ctrl.open_door(action == "door_open")
            elif action in ("belt_on", "belt_off"):
                ctrl.in_belt_on = action == "belt_on"
            elif action == "cycle_start" and ctrl.has_machine:
                if not ctrl.part_on_tray("raw_part"):
                    ctrl.set_light("red")
                    self._event("Zyklus gesperrt: kein Rohteil auf der Platte", gate=False)
                    return
                if not ctrl.start_cycle():
                    self._event("Zyklus nicht gestartet: Tür zu oder Platte nicht draußen", gate=False)
                    return
            elif action in ("auto_on", "auto_off"):
                self.auto = action == "auto_on" and ctrl.sorting
                ctrl.in_belt_on = ctrl.in_belt_on or self.auto
            elif action == "feed" and ctrl.sorting:
                ctrl.feed()
            elif action in ("light_red", "light_yellow", "light_green", "light_off") and ctrl.has_machine:
                ctrl.set_light(None if action == "light_off" else action.split("_")[1])
            self._event(f"Aktion: {action}")
            return
        if kind == "task":
            task = args["task"]
            if TASKS[task]["cell"] != self.cell:
                self._event(f"Task {task} gehört nicht zu dieser Zelle", gate=False)
                return
            self.busy = task
            part = None
            if task == "cnc_unload":
                part = ctrl.part_on_tray("fin_part")
                if not part:
                    self.busy = None
                    self._event("Entladen gesperrt: kein Fertigteil auf der Platte", gate=False)
                    return
            elif TASKS[task]["cell"] == "conveyor":
                ctrl.in_belt_on = True  # run_episode waits for a part of this arm's kind at its station
            self._event(f"Task {task} gestartet (geskripteter Referenz-Controller)")
            try:
                ep = run_episode(env, task, int(args.get("seed", 1000)), ctrl, fresh=False, part=part)
            finally:
                self.busy = None
            result = ep.public() | {"motion": "scripted reference controller (not Dream-1)"}
            gate = bool(ep.passed)
            if ctrl.has_machine:
                ctrl.set_light("green" if gate else "red")
            elif not gate:
                ctrl.in_belt_on = False
            self._event(f"Prüfung {task}: {'bestanden' if gate else 'NICHT bestanden'} ({ep.reason})",
                        gate=gate, result=result)
            with self.lock:
                self.state["last_result"] = result

    def _publish(self, ctrl, env, steps) -> None:
        if ctrl.sorting:
            waiting = ctrl.waiting()
            sensors = {"belt_on": bool(ctrl.in_belt_on) and not waiting, "auto": self.auto,
                       "barrier_right": bool(ctrl.at_barrier("right")), "barrier_left": bool(ctrl.at_barrier("left")),
                       "waiting": {"arm": waiting[0], "part": waiting[1]} if waiting else None,
                       "parts_on_belt": len(ctrl._sort_parts())}
        else:
            sensors = {"part_at_light_barrier": bool(ctrl.part_at_stop()), "belt_on": bool(ctrl.in_belt_on)}
        if ctrl.has_machine:
            light = None
            for name, i in ctrl._light_ids.items():
                if not np.allclose(env.model.geom_rgba[i], ctrl._light_rgba[name]):
                    light = name
            sensors |= {"door_open": bool(ctrl.door_open()), "door_closed": bool(ctrl.door < 0.02),
                        "tray_out": bool(ctrl.tray_out()), "tray_in": bool(ctrl.tray > 0.99),
                        "raw_part_on_tray": bool(ctrl.part_on_tray("raw_part")),
                        "finished_part_on_tray": bool(ctrl.part_on_tray("fin_part")),
                        "machine_running": bool(ctrl.phases), "machine_done": bool(ctrl.machine_done),
                        "stack_light": light, "cycles": ctrl.cycles}
        with self.lock:
            self.state.update({"status": "running", "sim_seconds": round(steps * STEP_S, 1), "sensors": sensors})

    def _store(self, view: str, rgb: np.ndarray) -> None:
        buffer = io.BytesIO()
        Image.fromarray(rgb).save(buffer, format="JPEG", quality=80)
        with self.lock:
            self.frames[view] = buffer.getvalue()


class SessionClosed(Exception):
    pass


def _front_raw_part(env) -> str | None:
    """The raw part nearest to the belt's end stop (the next one to pick)."""
    from .cnc import IN_BELT_X, IN_STOP_Y

    m, d = env.model, env.data
    best = None
    for i in range(m.nbody):
        name = m.body(i).name or ""
        if name.startswith("raw_part"):
            p = d.body(i).xpos
            if abs(p[0] - IN_BELT_X) < 0.06:
                dist = abs(p[1] - IN_STOP_Y)
                if best is None or dist < best[0]:
                    best = (dist, name)
    return best[1] if best else None
