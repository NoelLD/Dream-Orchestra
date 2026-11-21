"""Show the Dream Labs scripted pickups live in the MuJoCo viewer (needs a display, e.g. tools/gui.sh).

    docker compose up sim-gui
No API calls, no credits. Loops banana -> apple until the viewer window is closed.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

config.import_example()

import mujoco.viewer  # noqa: E402
import numpy as np  # noqa: E402
import mock_pickups  # noqa: E402
from yam_env import YamEnv, aim_viewer  # noqa: E402

_original_step = YamEnv.step
_original_init = YamEnv.__init__
state = {"viewer": None}


def viewer_init(self, *args, **kwargs):
    """Create the env, then (re)attach one passive viewer to its model."""
    _original_init(self, *args, **kwargs)
    if state["viewer"] is not None:
        state["viewer"].close()
    viewer = mujoco.viewer.launch_passive(self.model, self.data, show_left_ui=False, show_right_ui=False)
    with viewer.lock():
        aim_viewer(viewer)
    state["viewer"] = viewer


def viewer_step(self, left, right):
    """Step the sim, push it to the viewer, and pace roughly to real time."""
    result = _original_step(self, left, right)
    viewer = state["viewer"]
    if viewer is None or not viewer.is_running():
        raise SystemExit(0)
    viewer.sync()
    time.sleep(0.02)
    return result


if __name__ == "__main__":
    YamEnv.__init__ = viewer_init
    YamEnv.step = viewer_step
    while True:
        for fruit, yaw in (("banana", np.pi / 2), ("apple", 0.0)):
            print(mock_pickups.run_trial(fruit, yaw=yaw), flush=True)
            time.sleep(1)
