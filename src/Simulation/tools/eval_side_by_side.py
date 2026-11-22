"""Side-by-side video of the same scene: before (base) | after (fine-tune), optionally the expert, with labels.

    python3 src/Simulation/tools/eval_side_by_side.py beta-r20 <ft-label> cnc_unload 0
Runs on the host (numpy, Pillow, PyAV). Reads data/evals/cells/video/<label>/<task>-<seed>.mp4 and the result
lines in data/evals/cells/<label>.jsonl; writes data/evals/cells/side_by_side/<task>-<seed>.mp4.
Each panel shows the overhead camera (left third of the eval video), the label and the measured outcome; when a run
ends early its last frame is held, so both play in the same sim time.
"""

import json
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1] / "data/evals/cells"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
SCALE = 2  # 320x180 overhead -> 640x360 per panel


def frames(path: Path) -> list[np.ndarray]:
    with av.open(str(path)) as c:
        return [f.to_ndarray(format="rgb24") for f in c.decode(video=0)]


def result(label: str, task: str, seed: int) -> dict:
    rows = [json.loads(x) for x in (ROOT / f"{label}.jsonl").read_text().splitlines() if x.strip()]
    hits = [r for r in rows if r["task"] == task and r["seed"] == seed]
    return hits[-1] if hits else {}


def caption(r: dict) -> str:
    if not r:
        return ""
    if r.get("success"):
        text = f"success in {r['done_s']:.0f} s"
    else:
        text = r.get("outcome", "failed").replace("_", " ")
    return text + (f" | {r['contact_steps']} contact steps" if r.get("contact_steps") else " | no contact")


def panel(img: np.ndarray, title: str, sub: str, good: bool, fonts) -> np.ndarray:
    h, w = img.shape[:2]
    top = img[:, : w // 3] if w > 2 * h else img  # eval videos are overhead | wrist_l | wrist_r
    im = Image.fromarray(top).resize((top.shape[1] * SCALE, top.shape[0] * SCALE), Image.BILINEAR)
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle([0, 0, im.width, 58], fill=(0, 0, 0, 160))
    d.text((14, 6), title, font=fonts[0], fill=(255, 255, 255))
    d.text((14, 33), sub, font=fonts[1], fill=(120, 230, 140) if good else (255, 150, 120))
    return np.asarray(im)


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    *labels, task, seed = sys.argv[1:]
    seed = int(seed)
    fonts = (ImageFont.truetype(FONT, 24), ImageFont.truetype(FONT, 18))
    names = {"expert": "Scripted expert", "beta-r20": "Dream-1 base", "beta-main": "Dream-1 base (before)", "ft-main": "Dream-1 + cell fine-tune (after)"}
    clips = []
    for label in labels:
        r = result(label, task, seed)
        title = names.get(label, "Dream-1 + cell fine-tune" if "ft" in label else label)
        clips.append((frames(ROOT / "video" / label / f"{task}-{seed}.mp4"), title, caption(r), bool(r.get("success"))))
    n = max(len(c[0]) for c in clips)
    out = ROOT / "side_by_side" / f"{task}-{seed}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(out), "w") as container:
        stream = None
        for i in range(n):
            row = np.concatenate([panel(c[0][min(i, len(c[0]) - 1)], c[1], c[2], c[3], fonts) for c in clips], axis=1)
            if stream is None:
                stream = container.add_stream("h264", rate=10)  # eval frames are 5 per sim second -> 2x speed
                stream.height, stream.width = row.shape[0] - row.shape[0] % 2, row.shape[1] - row.shape[1] % 2
                stream.pix_fmt = "yuv420p"
            row = row[: stream.height, : stream.width]
            for packet in stream.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(row), format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
