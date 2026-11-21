"""Render a preview video of the CNC cell: belts running, machine done, door opening, arm picking a raw part.

    docker compose run --rm --no-deps simulation python /app/tools/cnc_preview.py --out /data/cnc_preview.mp4
    ... --still /data/cnc_still.png   # one overview + robot-camera frame, quick look at the layout
Scripted motion only (IK from the example's mock_pickups.solve); no Dream API calls, no credits.
Left half: overview camera (for people). Right half: the robot's top camera (what Dream-1 sees).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import av  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402
import yam_env  # noqa: E402
from mock_pickups import solve  # noqa: E402

from app.cnc import IN_BELT_X, CellController, cnc_xml  # noqa: E402

W, H = 640, 360
_original = yam_env.build_xml
yam_env.build_xml = lambda: cnc_xml(_original())


class Film:
    def __init__(self, env, ctrl):
        self.env, self.ctrl = env, ctrl
        self.renderer = mujoco.Renderer(env.model, height=H, width=W)
        self.cam = mujoco.MjvCamera()
        self.cam.lookat[:] = [0.05, -0.18, 0.86]
        self.cam.distance, self.cam.azimuth, self.cam.elevation = 1.65, -155.0, -24.0
        self.frames: list[np.ndarray] = []

    def frame(self) -> np.ndarray:
        self.renderer.update_scene(self.env.data, camera=self.cam)
        overview = self.renderer.render().copy()
        top = self.env.images()["top"]
        return np.concatenate([overview, top], axis=1)

    def step(self, left, right, record=True):
        self.ctrl.step()
        self.env.step(left, right)
        if record:
            self.frames.append(self.frame())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/data/cnc_preview.mp4"))
    parser.add_argument("--still", type=Path, help="write one PNG of the start layout and exit")
    args = parser.parse_args()

    env = yam_env.YamEnv()
    ctrl = CellController(env)
    film = Film(env, ctrl)
    home = np.r_[np.zeros(6), 1.0]
    if args.still:
        from PIL import Image

        ctrl.open_door(True)
        for _ in range(30):
            film.step(home, home, record=False)
        Image.fromarray(film.frame()).save(args.still)
        print(args.still)
        return 0

    ctrl.set_light("yellow")  # machining
    for _ in range(50):
        film.step(home, home)
    ctrl.set_light("green")  # machine done
    for _ in range(10):
        film.step(home, home)
    ctrl.open_door(True)
    for _ in range(30):
        film.step(home, home)

    side = "left" if IN_BELT_X > 0 else "right"
    rotation = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1.0]])
    q = env.state()[side][:6].copy()

    def command(qq, opening):
        arm = np.r_[qq, opening]
        return (arm, home) if side == "left" else (home, arm)

    def move(target, opening, steps):
        nonlocal q
        end = solve(env, side, np.asarray(target, dtype=float), rotation, q)
        start = q.copy()
        for alpha in np.linspace(0, 1, steps):
            film.step(*command(start + (end - start) * alpha, opening))
        q = end

    part = env.data.body("raw_part_0").xpos.copy()
    plan = [(part + [0, 0, 0.07], 1.0, 35), (part + [0, 0, 0.006], 1.0, 30), ("close", 0.0, 20),
            (part + [0, 0, 0.09], 0.0, 30), (part + [-0.12, 0.02, 0.10], 0.0, 40)]
    for target, opening, steps in plan:
        if isinstance(target, str):
            for o in np.linspace(1, 0, steps):
                film.step(*command(q, o))
            continue
        try:
            move(target, opening, steps)
        except ValueError as error:
            print(f"IK: {error}")
    for _ in range(25):
        film.step(*command(q, 0.0))
    lift = env.data.body("raw_part_0").xpos[2] - part[2]
    print(f"raw part lifted {lift:.3f} m, door open {ctrl.door_open()}, next part at stop {ctrl.part_at_stop()}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(args.out), "w") as container:
        stream = container.add_stream("h264", rate=20)
        stream.height, stream.width = film.frames[0].shape[:2]
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "23"}
        for f in film.frames:
            for packet in stream.encode(av.VideoFrame.from_ndarray(f, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    print(f"{args.out}: {len(film.frames)} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
