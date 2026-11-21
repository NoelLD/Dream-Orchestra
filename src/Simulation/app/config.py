"""Paths and settings of the simulation service, all overridable by environment variables."""

import os
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]  # src/Simulation (or /app in the container)
REPO_DIR = SERVICE_DIR.parents[1] if SERVICE_DIR.parent.name == "src" else SERVICE_DIR

# The Dream Labs YAM MuJoCo example: baked into the image, or the local clone in Dream-Orchestra/vendor/ on a host.
EXAMPLE_DIR = Path(
    os.environ.get("DREAM_YAM_EXAMPLE", REPO_DIR / "vendor/dreamlabs/dream_library/examples/yam_mujoco")
)
DATA_DIR = Path(os.environ.get("SIM_DATA_DIR", SERVICE_DIR / "data"))
RUNS_DIR = DATA_DIR / "runs"
DATASETS_DIR = DATA_DIR / "datasets"
WORK_DIR = DATA_DIR / "work"  # cwd for the example's scripts, which write relative files (mock_results/)

DEFAULT_TIMEOUT_S = float(os.environ.get("SIM_DEFAULT_TIMEOUT_S", "60"))
DEFAULT_MOCK_TIMEOUT_S = float(os.environ.get("SIM_DEFAULT_MOCK_TIMEOUT_S", "60"))  # simulated seconds
MIN_CALL_INTERVAL_S = float(os.environ.get("SIM_MIN_CALL_INTERVAL_S", "0.7"))
RENDER_SHADOWS = os.environ.get("SIM_RENDER_SHADOWS", "0") == "1"  # off: ~3x faster software rendering

# Price per get_action call (Dream Labs fine-tuning tutorial, 21.11.2026; to be checked against billing).
PRICE_PER_CALL_USD = {"base": 0.0014, "fine_tuned": 0.0028}
PRICE_PER_FINETUNE_STEP_USD = 0.20

BASE_CHECKPOINTS = ("dreamlabs/dream-1-beta", "dreamlabs/dream-1-beta-flash")
DEFAULT_CHECKPOINT = BASE_CHECKPOINTS[0]
EMBODIMENT_NAME = "yam-sim"


def ensure_dirs() -> None:
    for path in (RUNS_DIR, DATASETS_DIR, WORK_DIR):
        path.mkdir(parents=True, exist_ok=True)


def import_example() -> None:
    """Make the example's modules (yam_env, mock_pickups, dream_control) importable."""
    if not (EXAMPLE_DIR / "yam_env.py").exists():
        raise RuntimeError(f"Dream YAM example not found at {EXAMPLE_DIR}; set DREAM_YAM_EXAMPLE.")
    if str(EXAMPLE_DIR) not in sys.path:
        sys.path.insert(0, str(EXAMPLE_DIR))


def dream_key_set() -> bool:
    return bool(os.environ.get("DREAM_API_KEY"))


def price_per_call(checkpoint: str) -> float:
    return PRICE_PER_CALL_USD["fine_tuned" if checkpoint.startswith("dream-1-ft:") else "base"]
