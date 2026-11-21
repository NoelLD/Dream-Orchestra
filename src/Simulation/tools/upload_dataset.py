"""Register the YAM sim embodiment (once) and upload a local LeRobot dataset; then poll until processed/failed.

    docker compose run --rm simulation python /app/tools/upload_dataset.py datasets/pick-smoke pick-smoke-1
Writes to the Dream Labs account (no credits). Fine-tuning is NOT started here.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dream import datasets  # noqa: E402

from app.embodiment import EMBODIMENT  # noqa: E402

EMBODIMENT_NAME = "yam-sim"


def ensure_embodiment() -> str:
    for body in datasets.list_embodiments():
        name = getattr(body, "name", str(body))
        if name.endswith(f"/{EMBODIMENT_NAME}"):
            print("embodiment exists:", name)
            return name
    body = datasets.add_embodiment(EMBODIMENT_NAME, EMBODIMENT)
    print("embodiment registered:", body.name)
    return body.name


if __name__ == "__main__":
    directory, name = Path(sys.argv[1]), sys.argv[2]
    embodiment = ensure_embodiment()
    dataset = datasets.upload_dataset(directory, name, embodiment)
    print("uploaded:", dataset.id, dataset.status, dataset.episodes, "episodes", dataset.size_bytes, "bytes", flush=True)
    start = time.time()
    while dataset.status not in ("processed", "failed"):
        time.sleep(30)
        dataset = datasets.get_dataset(dataset.id)
        print(f"{time.time() - start:5.0f}s {dataset.status}", flush=True)
    print("final:", dataset.status, getattr(dataset, "error", None), f"after {time.time() - start:.0f}s")
    raise SystemExit(0 if dataset.status == "processed" else 1)
