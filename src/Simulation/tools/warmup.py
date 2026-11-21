"""Warm up fine-tuned checkpoints in parallel before an evaluation (a cold model can take up to 1 h to start).

    docker compose exec simulation python /app/tools/warmup.py dream-1-ft:aaaa-yam-r500 dream-1-ft:bbbb-yam-a500-own
Each checkpoint gets its own thread: one observation from a fresh YAM scene, get_action() retried while Dream
answers pool_warming, stopped after the first real answer (one paid call, ~0.003 $) or after --cap-min minutes.
Prints one JSON line per checkpoint: ready / not_ready / error, and the minutes it took.
"""

import argparse
import json
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402
from app.runner import _is_warming  # noqa: E402

config.import_example()


def warm(checkpoint: str, cap_s: float, out: dict) -> None:
    import base64
    import io

    import dream_control as dc
    from PIL import Image
    from yam_env import YamEnv

    started = time.monotonic()
    env, policy = YamEnv(), None
    try:
        windows = {name: deque(maxlen=dc.FRAMES) for name in dc.VIDEO_ROLES}
        steps = 0
        while any(len(w) < dc.FRAMES for w in windows.values()):
            s = env.state()
            env.step(s["left"], s["right"])
            steps += 1
            if steps % dc.FRAME_EVERY_STEPS == 0:
                for name, rgb in env.images().items():
                    buf = io.BytesIO()
                    Image.fromarray(rgb).resize(dc.FRAME_SIZE, Image.BILINEAR).save(buf, "JPEG", quality=85)
                    windows[name].append(base64.b64encode(buf.getvalue()).decode("ascii"))
        gateway = os.environ.get("DREAM_GATEWAY_URL", "https://api.dreamlabs.ai")
        poses = checkpoint in dc.POSE_MODELS
        policy = dc.open_policy(dc.policy_config(checkpoint, gateway, poses), os.environ["DREAM_API_KEY"])
        dc.feed(policy, env, windows, "pick up the banana", checkpoint, steps, every=0, station=poses)
        while time.monotonic() - started < cap_s:
            try:
                policy.get_action()
                out[checkpoint] = {"status": "ready", "minutes": round((time.monotonic() - started) / 60, 1)}
                return
            except Exception as error:
                if not _is_warming(error):
                    raise
                time.sleep(min(float(getattr(error, "retry_after_s", 15) or 15), 30))
        out[checkpoint] = {"status": "not_ready", "minutes": round(cap_s / 60, 1)}
    except Exception as error:
        out[checkpoint] = {"status": "error", "error": f"{type(error).__name__}: {str(error)[:200]}"}
    finally:
        if policy is not None:
            try:
                policy.close()
            except Exception:
                pass
        env.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoints", nargs="+")
    parser.add_argument("--cap-min", type=float, default=60)
    args = parser.parse_args()
    if not os.environ.get("DREAM_API_KEY"):
        print("DREAM_API_KEY is not set", file=sys.stderr)
        return 2
    out: dict = {}
    threads = [threading.Thread(target=warm, args=(c, args.cap_min * 60, out)) for c in args.checkpoints]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for c in args.checkpoints:
        print(json.dumps({"checkpoint": c} | out.get(c, {"status": "error", "error": "no result"})))
    return 0 if all(out.get(c, {}).get("status") == "ready" for c in args.checkpoints) else 1


if __name__ == "__main__":
    raise SystemExit(main())
