"""Demo video of the two cell experiments with live process signals (scripted expert, no Dream API, no credits).

    docker compose run --rm --no-deps simulation python /app/tools/cell_demo_video.py --out /data/cell_demo.mp4
Part 1, conveyor cell: the belt brings raw parts to the light barrier, the belt stops, the arm puts the part in the KLT.
Part 2, CNC cell: load the tray -> verified -> door closes, tray in, machining, door opens, tray out -> unload.
Left: overview camera; right: the robot's top camera (what Dream-1 sees). Bottom bar: live signals.
Motion source is shown on screen: scripted reference controller, not Dream-1 inference.
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
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.cnc import CellController, cell_xml  # noqa: E402
from app.cnc_expert import run_cnc_demo, run_episode  # noqa: E402

_original = yam_env.build_xml
W, H, BAR = 640, 360, 56


def font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


F_BIG, F_SMALL = font(19), font(15)


class Writer:
    """Streams frames to the MP4 (holding ~1,200 frames in RAM would exceed the 3 GB VM)."""

    def __init__(self, path):
        self.container = av.open(str(path), "w")
        self.stream = None
        self.count = 0

    def add(self, frame: np.ndarray) -> None:
        if self.stream is None:
            self.stream = self.container.add_stream("h264", rate=20)
            self.stream.height, self.stream.width = frame.shape[:2]
            self.stream.pix_fmt = "yuv420p"
        for packet in self.stream.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
            self.container.mux(packet)
        self.count += 1

    def close(self) -> None:
        for packet in self.stream.encode():
            self.container.mux(packet)
        self.container.close()


class Filmer:
    def __init__(self, env, ctrl, title, azimuth, writer):
        self.env, self.ctrl, self.title = env, ctrl, title
        self.renderer = mujoco.Renderer(env.model, height=H, width=W)
        self.cam = mujoco.MjvCamera()
        self.cam.lookat[:] = [0.05, -0.05, 0.86]
        self.cam.distance, self.cam.azimuth, self.cam.elevation = 1.45, azimuth, -27.0
        self.writer = writer
        self.note = ""

    def signals(self) -> list[tuple[str, bool | str]]:
        c = self.ctrl
        if not c.has_machine:
            return [("Lichtschranke", c.part_at_stop()), ("Band", "läuft" if c.in_belt_on else "steht")]
        light = next((k for k, i in c._light_ids.items() if np.allclose(self.env.model.geom_rgba[i][:3],
                      {"red": [0.95, 0.15, 0.12], "yellow": [1, 0.8, 0.1], "green": [0.2, 0.9, 0.3]}[k])), "aus")
        return [("Tür", "offen" if c.door_open() else ("zu" if c.door < 0.02 else "fährt")),
                ("Platte", "draußen" if c.tray_out() else ("drin" if c.tray > 0.99 else "fährt")),
                ("Ampel", {"green": "grün", "yellow": "gelb", "red": "rot"}.get(light, "aus")),
                ("Rohteil auf Platte", bool(c.part_on_tray("raw_part"))), ("Fertigteil auf Platte", bool(c.part_on_tray("fin_part")))]

    def frame(self):
        self.renderer.update_scene(self.env.data, camera=self.cam)
        img = np.concatenate([self.renderer.render().copy(), self.env.images()["top"]], axis=1)
        canvas = Image.new("RGB", (2 * W, H + BAR + 34), (24, 26, 30))
        canvas.paste(Image.fromarray(img), (0, 34))
        d = ImageDraw.Draw(canvas)
        d.text((12, 7), self.title, font=F_BIG, fill=(240, 240, 240))
        d.text((2 * W - 12, 9), "Bewegung: geskripteter Referenz-Controller (kein Dream-1)", font=F_SMALL,
               fill=(170, 175, 185), anchor="ra")
        x = 12
        for name, value in self.signals():
            on = value if isinstance(value, bool) else value in ("offen", "läuft", "grün", "draußen")
            text = f"{name}: {'ja' if value is True else 'nein' if value is False else value}"
            d.rounded_rectangle([x, H + 46, x + 18, H + 64], 4, fill=(60, 200, 90) if on else (90, 94, 100))
            d.text((x + 26, H + 46), text, font=F_SMALL, fill=(230, 230, 230))
            x += 30 + int(d.textlength(text, font=F_SMALL)) + 18
        if self.note:
            d.text((2 * W - 12, H + 46), self.note, font=F_SMALL, fill=(255, 210, 90), anchor="ra")
        self.writer.add(np.array(canvas))

    def wrap(self):
        original = self.env.step

        def step(left, right):
            out = original(left, right)
            self.frame()
            return out

        self.env.step = step


def make(cell):
    yam_env.build_xml = lambda: cell_xml(_original(), cell)
    env = yam_env.YamEnv()
    return env, CellController(env)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("/data/cell_demo.mp4"))
    parser.add_argument("--seed", type=int, default=1000)
    args = parser.parse_args()
    writer = Writer(args.out)

    env, ctrl = make("conveyor")
    film = Filmer(env, ctrl, "Experiment 1: Fließband mit Lichtschranke → KLT", -150.0, writer)
    film.wrap()
    film.note = "Band fördert bis zur Lichtschranke"
    ep = run_episode(env, "belt_to_klt", args.seed, ctrl)
    film.note = "geprüft: Teil in der KLT, kein Kontakt" if ep.passed else f"nicht bestanden: {ep.reason}"
    for _ in range(25):
        film.frame()
    print("conveyor:", ep.public())
    env.close()

    env, ctrl = make("cnc")
    film = Filmer(env, ctrl, "Experiment 2: CNC-Maschine – Tür auf, Tür zu", -150.0, writer)
    film.wrap()
    film.note = "Beladen: Rohteil auf die Übergabeplatte"
    log = run_cnc_demo(env, ctrl, args.seed)
    for entry in log:
        print("cnc:", entry)
    film.note = "Zyklus fertig, Fertigteil in der Ablage" if any(e.get("task") == "cnc_unload" and e.get("passed")
                                                                 for e in log) else "Prozess gestoppt"
    for _ in range(25):
        film.frame()
    env.close()
    writer.close()
    print(f"{args.out}: {writer.count} frames, {writer.count / 20:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
