"""The YAM sim embodiment: 14 values, right arm first, three cameras (Dream Labs fine-tuning tutorial, step 3)."""

CAMERAS = {"overhead": "top", "wrist_l": "left", "wrist_r": "right"}  # Dream video role -> sim camera

EMBODIMENT = {
    "state": {"right_arm": [0, 6], "right_gripper": [6, 7], "left_arm": [7, 13], "left_gripper": [13, 14]},
    "action": {"right_arm": [0, 6], "right_gripper": [6, 7], "left_arm": [7, 13], "left_gripper": [13, 14]},
    "video": {role: f"observation.images.{role}" for role in CAMERAS},
    "head_camera": "overhead",
}
