"""Record the Dream Labs scripted pickup (mock_pickups.run_trial) as an MP4: top camera + both wrist cameras.

Run inside the sim container:
    docker compose run --rm simulation python /app/tools/record_pickup.py banana
No API calls, no credits.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import av  # noqa: E402
import numpy as np  # noqa: E402
import mock_pickups  # noqa: E402
from yam_env import YamEnv  # noqa: E402

frames: list[np.ndarray] = []
_original_step = YamEnv.step


def recording_step(self, left, right):
    """Step the sim as usual, then grab one combined camera frame."""
    result = _original_step(self, left, right)
    images = self.images()
    wrists = np.concatenate([images["left"][::2, ::2], images["right"][::2, ::2]], axis=1)
    frames.append(np.concatenate([images["top"], wrists], axis=0))
    return result


def write_mp4(path: Path, images: list[np.ndarray], fps: int = 30) -> None:
    """Encode RGB frames as H.264."""
    with av.open(str(path), "w") as container:
        stream = container.add_stream("h264", rate=fps)
        stream.height, stream.width = images[0].shape[:2]
        stream.pix_fmt = "yuv420p"
        for image in images:
            for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


if __name__ == "__main__":
    fruit = sys.argv[1] if len(sys.argv) > 1 else "banana"
    YamEnv.step = recording_step
    result = mock_pickups.run_trial(fruit, yaw=np.pi / 2 if fruit == "banana" else 0)
    out = config.DATA_DIR
    out.mkdir(exist_ok=True)
    target = out / f"pickup-{fruit}.mp4"
    write_mp4(target, frames)
    print(f"{len(frames)} frames -> {target} passed={result['passed']}")
