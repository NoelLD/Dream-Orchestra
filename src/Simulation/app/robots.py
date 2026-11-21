"""Robot types the simulation offers. A fine-tune belongs to a robot type, not to a task.

Dream Labs (fine-tuning tutorial): "Fine-tuning is for new robots, not for automating a task. It teaches Dream-1
your robot's body." So one dataset holds demos of all of a robot's tasks (each episode with its own prompt), one
fine-tune job is started per robot type, and its checkpoint serves every task of that robot.
"""

from dataclasses import dataclass

from . import config


@dataclass(frozen=True)
class Robot:
    name: str
    description: str
    embodiment: str  # name of the embodiment registered at Dream Labs (account prefix added there)
    cameras: tuple[str, ...]


ROBOTS: dict[str, Robot] = {
    r.name: r
    for r in [
        Robot("yam-sim", "Two YAM arms in the Dream Labs MuJoCo scene (simulation)", config.EMBODIMENT_NAME,
              ("overhead", "wrist_l", "wrist_r")),
    ]
}
DEFAULT_ROBOT = "yam-sim"


def active_checkpoint(robot: str, jobs: dict[str, dict]) -> str | None:
    """The newest finished fine-tune of this robot type, or None (then the base model is used)."""
    done = [j for j in jobs.values() if j.get("robot", DEFAULT_ROBOT) == robot and j.get("fine_tuned_model")]
    done.sort(key=lambda j: j.get("finished_at") or j.get("created_at") or "")
    return done[-1]["fine_tuned_model"] if done else None
