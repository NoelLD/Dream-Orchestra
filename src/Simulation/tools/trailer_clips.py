"""Record clean simulation clips for the trailer (no burned-in text) plus per-frame signals for overlays.

    docker compose run --rm --no-deps simulation python /app/tools/trailer_clips.py --out /data/trailer
Writes <out>/<clip>.mp4 (1280x720, 20 fps, overview camera), <clip>-robot.mp4 where useful (the robot's top camera,
what the model sees), and <clip>.jsonl (one line per frame: sensors, events). Scripted reference controller only;
no Dream API calls, no credits.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import av  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402
import yam_env  # noqa: E402

from app.cnc import cell_xml, CellController, PARK  # noqa: E402
from app.cnc_expert import run_episode  # noqa: E402

_original = yam_env.build_xml
W, H = 1280, 720


class Clip:
    def __init__(self, out: Path, name: str, env, ctrl, cam: dict, robot: bool = False):
        self.env, self.ctrl, self.name = env, ctrl, name
        self.renderer = mujoco.Renderer(env.model, height=H, width=W)
        self.cam = mujoco.MjvCamera()
        self.cam.lookat[:] = cam["lookat"]
        self.cam.distance, self.cam.azimuth, self.cam.elevation = cam["dist"], cam["az"], cam["el"]
        self.video = _Writer(out / f"{name}.mp4")
        self.robot = _Writer(out / f"{name}-robot.mp4") if robot else None
        self.robot_r = mujoco.Renderer(env.model, height=360, width=640) if robot else None
        self.log = (out / f"{name}.jsonl").open("w")
        self.frame_no = 0
        self.event: str | None = None

    def mark(self, event: str) -> None:
        self.event = event  # written with the next frame

    def shoot(self) -> None:
        self.renderer.update_scene(self.env.data, camera=self.cam)
        self.video.add(self.renderer.render())
        if self.robot:
            self.robot_r.update_scene(self.env.data, camera="top")
            self.robot.add(self.robot_r.render())
        c = self.ctrl
        sig = {"f": self.frame_no, "t": round(self.frame_no / 20, 2)}
        if c.sorting:
            w = c.waiting()
            sig |= {"belt_on": bool(c.in_belt_on) and not w, "barrier_right": c.at_barrier("right"),
                    "barrier_left": c.at_barrier("left"), "waiting": w[0] if w else None}
        if c.has_machine:
            light = next((k for k, i in c._light_ids.items()
                          if not np.allclose(self.env.model.geom_rgba[i], c._light_rgba[k])), None)
            sig |= {"door": round(float(c.door), 2), "tray": round(float(c.tray), 2), "light": light,
                    "raw_on_tray": bool(c.part_on_tray("raw_part")), "fin_on_tray": bool(c.part_on_tray("fin_part"))}
        if self.event:
            sig["event"], self.event = self.event, None
        self.log.write(json.dumps(sig) + "\n")
        self.frame_no += 1

    def hook(self) -> None:
        original = self.env.step
        self._unhooked = original

        def step(left, right):
            out = original(left, right)
            self.shoot()
            return out

        self.env.step = step

    def idle(self, n: int) -> None:
        home = np.r_[np.zeros(6), 1.0]
        for _ in range(n):
            self.ctrl.step()
            self.env.step(home, home)

    def close(self) -> None:
        self.env.step = self._unhooked  # the next clip films this scene, not this writer
        self.video.close()
        if self.robot:
            self.robot.close()
        self.log.close()
        print(f"{self.name}: {self.frame_no} frames ({self.frame_no / 20:.1f} s)", flush=True)


class _Writer:
    def __init__(self, path):
        self.c = av.open(str(path), "w")
        self.s = None

    def add(self, rgb):
        if self.s is None:
            self.s = self.c.add_stream("h264", rate=20)
            self.s.height, self.s.width = rgb.shape[:2]
            self.s.pix_fmt = "yuv420p"
            self.s.options = {"crf": "16", "g": "10"}
        for p in self.s.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format="rgb24")):
            self.c.mux(p)

    def close(self):
        for p in self.s.encode():
            self.c.mux(p)
        self.c.close()


def make(cell):
    yam_env.build_xml = lambda: cell_xml(_original(), cell)
    env = yam_env.YamEnv()
    yam_env.build_xml = _original
    return env, CellController(env)


def cnc_start(env, ctrl):
    env.data.joint("fin_part_0_free").qpos[:3] = PARK
    mujoco.mj_forward(env.model, env.data)
    ctrl.door, ctrl.door_target = 1.0, 1.0
    ctrl.set_light("green")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/data/trailer"))
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    want = set(filter(None, args.only.split(",")))
    near = {"lookat": [0.03, 0.02, 0.86], "dist": 1.05, "az": -138.0, "el": -24.0}
    front = {"lookat": [0.0, -0.08, 0.92], "dist": 1.15, "az": -112.0, "el": -16.0}
    light = {"lookat": [0.12, -0.15, 1.02], "dist": 0.75, "az": -125.0, "el": -14.0}
    wide = {"lookat": [0.0, 0.0, 0.84], "dist": 1.55, "az": -118.0, "el": -32.0}

    if not want or "cnc_load" in want:  # 01/02/03: the arm puts the raw part on the tray, robot camera beside
        env, ctrl = make("cnc")
        cnc_start(env, ctrl)
        clip = Clip(args.out, "cnc_load", env, ctrl, near, robot=True)
        clip.hook()
        clip.idle(10)
        ep = run_episode(env, "cnc_load", 1000, ctrl, fresh=False)
        clip.mark(f"check:{'pass' if ep.passed else 'fail'}")
        clip.idle(30)
        clip.close()
        print("cnc_load", ep.public(), flush=True)
        # 04: the cycle, continuing the same scene
        clip = Clip(args.out, "cnc_cycle", env, ctrl, front)
        clip.hook()
        clip.idle(8)
        clip.mark("cycle_start")
        ctrl.start_cycle()
        for _ in range(260):
            clip.idle(1)
            if ctrl.machine_done:
                break
        clip.mark("cycle_done")
        clip.idle(25)
        clip.close()
        env.close()

    if not want or "gate_fail" in want:  # 05: cycle requested with an empty tray -> red, locked
        env, ctrl = make("cnc")
        cnc_start(env, ctrl)
        clip = Clip(args.out, "gate_fail", env, ctrl, light)
        clip.hook()
        clip.idle(30)
        clip.mark("cycle_requested_empty_tray")
        ctrl.set_light("red")  # the session's gate does exactly this when no raw part is on the tray
        clip.idle(50)
        clip.close()
        env.close()

    if not want or "sort" in want:  # 06/07: two arms sort round parts and cubes, belt stops at the stations
        env, ctrl = make("conveyor")
        clip = Clip(args.out, "sort", env, ctrl, wide, robot=True)
        clip.hook()
        sorted_n, step = 0, 0
        while sorted_n < 4 and step < 3000:
            w = ctrl.waiting()
            if w:
                task = {"right": "sort_round", "left": "sort_cube"}[w[0]]
                clip.mark(f"pick:{w[0]}")
                ep = run_episode(env, task, 2000 + step, ctrl, fresh=False, part=w[1])
                clip.mark(f"check:{w[0]}:{'pass' if ep.passed else 'fail'}")
                sorted_n += 1
                print("sort", task, ep.passed, ep.reason, flush=True)
                continue
            if step % 20 == 0:
                ctrl.feed()
            clip.idle(1)
            step += 1
        clip.idle(20)
        clip.close()
        env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
