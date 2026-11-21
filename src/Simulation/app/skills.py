"""Skills the simulation can run, each with a default prompt and a success check measured in the simulator.

Success is decided here from MuJoCo state, never from a Dream API reply.
"""

from dataclasses import dataclass, field

import numpy as np

TABLE_LIFT_M = 0.08  # an object counts as lifted 8 cm above where it started
PLACE_RADIUS_M = {"plate": 0.08, "bowl": 0.07}


@dataclass
class Skill:
    name: str
    description: str
    default_prompt: str
    obj: str
    target: str | None = None  # body the object must end on/in; None = lift only
    mock_yaw: float | None = None  # scripted pickup available (mock mode) when set
    robot: str = "yam-sim"  # the robot type this task runs on; its fine-tune is the robot's (app/robots.py)
    extra: dict = field(default_factory=dict)

    @property
    def mock_available(self) -> bool:
        return self.mock_yaw is not None

    @property
    def success_check(self) -> str:
        if self.target is None:
            return f"{self.obj} lifted >= {TABLE_LIFT_M} m above its start"
        return f"{self.obj} resting within {PLACE_RADIUS_M[self.target]} m of the {self.target} centre"

    def public(self, fine_tuned_model: str | None = None) -> dict:
        """fine_tuned_model: the active checkpoint of this skill's robot (None = base model)."""
        return {
            "name": self.name,
            "description": self.description,
            "default_prompt": self.default_prompt,
            "robot": self.robot,
            "fine_tuned_model": fine_tuned_model,
            "success_check": self.success_check,
            "mock_available": self.mock_available,
        }


SKILLS: dict[str, Skill] = {
    s.name: s
    for s in [
        Skill("pick-banana", "Pick up the banana", "pick up the banana", "banana", mock_yaw=float(np.pi / 2)),
        Skill("pick-apple", "Pick up the apple", "pick up the apple", "apple", mock_yaw=0.0),
        Skill("banana-to-plate", "Put the banana on the plate", "put the banana on the plate", "banana", "plate"),
        Skill("apple-to-bowl", "Put the apple into the bowl", "put the apple into the bowl", "apple", "bowl"),
    ]
}


class SuccessTracker:
    """Watches one object during a run and says when the skill's goal is reached."""

    def __init__(self, skill: Skill, env):
        self.skill = skill
        self.start_z = float(env.data.body(skill.obj).xpos[2])
        self.max_lift = 0.0
        self.settled_steps = 0

    def update(self, env) -> bool:
        pos = env.data.body(self.skill.obj).xpos
        self.max_lift = max(self.max_lift, float(pos[2]) - self.start_z)
        if self.skill.target is None:
            return self.max_lift >= TABLE_LIFT_M
        target = env.data.body(self.skill.target).xpos
        inside = np.linalg.norm(pos[:2] - target[:2]) <= PLACE_RADIUS_M[self.skill.target]
        speed = float(np.linalg.norm(env.data.body(self.skill.obj).cvel[3:]))
        self.settled_steps = self.settled_steps + 1 if inside and speed < 0.05 else 0
        return self.settled_steps >= 10  # resting in the target for 0.5 s of sim time

    def detail(self, env) -> dict:
        pos = env.data.body(self.skill.obj).xpos
        out = {"max_lift_m": round(self.max_lift, 4)}
        if self.skill.target is not None:
            target = env.data.body(self.skill.target).xpos
            out["distance_to_target_m"] = round(float(np.linalg.norm(pos[:2] - target[:2])), 4)
        return out
