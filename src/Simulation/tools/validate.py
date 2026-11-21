"""Validate a dataset folder (one session or a folder of sessions) against the YAM sim embodiment, offline.

    docker compose run --rm simulation python /app/tools/validate.py datasets/pick-v1
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dream import datasets  # noqa: E402

from app.embodiment import EMBODIMENT  # noqa: E402

if __name__ == "__main__":
    report = datasets.validate_dataset(Path(sys.argv[1]), EMBODIMENT)
    print("validate_dataset:", "OK" if report.ok else "FAILED")
    print(report)
    raise SystemExit(0 if report.ok else 1)
