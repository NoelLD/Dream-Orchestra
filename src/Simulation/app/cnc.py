"""CNC machine-tending cell: the YAM scene with a closed machine, an in-feed and an out-feed conveyor.

The fruit scene stays the default; this is a separate scene variant ("cnc"). It is built by editing the example's
MJCF (yam_env.build_xml): the kitchen props are removed, the cell is added. Coordinates are MuJoCo world metres;
the table top is at z = 0.76, the arm bases sit at x = +-0.305, y = 0.24, and the top camera looks from the arms
towards -y.

Process signals (sensors/actuators) are read and set by CellController; they are simulated, not safety functions.
"""

import xml.etree.ElementTree as ET

import numpy as np

TABLE_Z = 0.76
KITCHEN_PROPS = ("apple", "banana", "orange", "water_bottle", "bowl", "plate")

MACHINE_FRONT_Y = -0.01  # the vise must lie inside the arms' top-down reach (x = 0 down to y ~ -0.10)
VISE = np.array([0.0, -0.07])
SEAT_Z = 0.80  # machine table top, parts rest here between the jaws
DOOR_CLOSED = np.array([0.0, MACHINE_FRONT_Y + 0.012, 0.93])
DOOR_OPEN = DOOR_CLOSED + [0.0, 0.0, 0.30]  # lifting door: opens upwards in front of the lintel

BELT_TOP = 0.797
IN_BELT_X, OUT_BELT_X = 0.40, -0.40
BELT_Y0, BELT_Y1 = -0.55, -0.03  # belt ends (far, near the arms)
IN_STOP_Y = -0.08  # first raw part stops here (end stop + light barrier)
RAW_HALF = (0.02, 0.02, 0.0175)  # sawn aluminium blank, 40 x 40 x 35 mm
FIN_R, FIN_HALF_H = 0.021, 0.016  # machined aluminium part, d 42 x 32 mm

STEEL = ".62 .66 .72 1"
ALU = ".8 .82 .85 1"
MACHINE = ".74 .76 .75 1"
FRAME = ".25 .27 .3 1"
RUBBER = ".08 .08 .09 1"


def _box(parent, name, pos, size, rgba, **kw):
    return ET.SubElement(parent, "geom", name=name, type="box", pos=_n(pos), size=_n(size), rgba=rgba, **kw)


def _cyl(parent, name, pos, size, rgba, **kw):
    return ET.SubElement(parent, "geom", name=name, type="cylinder", pos=_n(pos), size=_n(size), rgba=rgba, **kw)


def _n(values) -> str:
    return " ".join(f"{v:.4g}" for v in values)


def _machine(world) -> None:
    fy, by = MACHINE_FRONT_Y, -0.31
    cy, hd = (fy + by) / 2, (fy - by) / 2
    _box(world, "cnc_plinth", (0, cy, TABLE_Z + 0.01), (0.25, hd + 0.01, 0.01), FRAME)
    for side in (-1, 1):
        _box(world, f"cnc_side_{side}", (side * 0.24, cy, 0.95), (0.006, hd, 0.18), MACHINE)
        _box(world, f"cnc_post_{side}", (side * 0.20, fy, 0.95), (0.04, 0.006, 0.18), MACHINE)
    _box(world, "cnc_back", (0, by, 0.95), (0.24, 0.006, 0.18), MACHINE)
    _box(world, "cnc_roof", (0, cy, 1.136), (0.246, hd + 0.006, 0.008), MACHINE)
    _box(world, "cnc_lintel", (0, fy, 1.105), (0.16, 0.006, 0.025), MACHINE)
    _box(world, "cnc_stripe", (0, fy + 0.007, 1.115), (0.24, 0.001, 0.005), ".95 .55 .1 1", contype="0", conaffinity="0")
    _box(world, "cnc_screen", (-0.20, fy + 0.007, 1.0), (0.03, 0.001, 0.035), ".2 .45 .6 1", contype="0", conaffinity="0")
    # Inside: machine table, vise (jaws opened to 66 mm), spindle head.
    _box(world, "cnc_table", (0, -0.13, SEAT_Z - 0.015), (0.16, 0.11, 0.015), FRAME)
    for side in (-1, 1):
        _box(world, f"cnc_jaw_{side}", (side * 0.045, VISE[1], SEAT_Z + 0.018), (0.012, 0.03, 0.018), ".35 .37 .4 1")
    _cyl(world, "cnc_spindle", (0, -0.22, 1.05), (0.032, 0.06), ".7 .72 .75 1", contype="0", conaffinity="0")
    _cyl(world, "cnc_tool", (0, -0.22, 0.97), (0.006, 0.02), ".9 .75 .3 1", contype="0", conaffinity="0")
    # Stack light (red / yellow / green) on the roof.
    light = ET.SubElement(world, "body", name="cnc_stack_light", pos="0.2 -0.27 1.144")
    _cyl(light, "cnc_light_pole", (0, 0, 0.02), (0.005, 0.02), FRAME, contype="0", conaffinity="0")
    for i, (name, rgba) in enumerate([("red", ".35 .08 .08 1"), ("yellow", ".35 .3 .05 1"), ("green", ".06 .3 .1 1")]):
        _cyl(light, f"cnc_light_{name}", (0, 0, 0.05 + i * 0.026), (0.016, 0.012), rgba, contype="0", conaffinity="0")
    # Lifting door (mocap: moved kinematically by CellController) with a window.
    door = ET.SubElement(world, "body", name="cnc_door", mocap="true", pos=_n(DOOR_CLOSED))
    _box(door, "cnc_door_panel", (0, 0, 0), (0.166, 0.004, 0.15), ".78 .8 .78 1")
    _box(door, "cnc_door_window", (0, 0.0045, 0.02), (0.12, 0.001, 0.09), ".55 .7 .8 .55", contype="0", conaffinity="0")
    _box(door, "cnc_door_handle", (0, 0.012, -0.12), (0.06, 0.006, 0.006), FRAME, contype="0", conaffinity="0")
    # The finished part waiting in the vise.
    _finished_part(world, "fin_part_0", (VISE[0], VISE[1], SEAT_Z + FIN_HALF_H + 0.001))


def _belt(world, name, x) -> None:
    cy, hl = (BELT_Y0 + BELT_Y1) / 2, (BELT_Y1 - BELT_Y0) / 2
    _box(world, f"{name}_frame", (x, cy, 0.775), (0.06, hl, 0.015), ".62 .65 .68 1")
    _box(world, f"{name}_rubber", (x, cy, BELT_TOP - 0.0025), (0.05, hl, 0.0025), RUBBER)
    for side in (-1, 1):
        _box(world, f"{name}_rail_{side}", (x + side * 0.057, cy, BELT_TOP + 0.003), (0.004, hl, 0.006), ".7 .73 .76 1")
    for end, y in (("far", BELT_Y0), ("near", BELT_Y1)):
        _cyl(world, f"{name}_roller_{end}", (x, y, 0.782), (0.017, 0.055), ".5 .52 .55 1",
             euler="0 1.5708 0", contype="0", conaffinity="0")


def _raw_part(world, name, pos) -> None:
    body = ET.SubElement(world, "body", name=name, pos=_n(pos))
    ET.SubElement(body, "freejoint", name=f"{name}_free")
    _box(body, f"{name}_geom", (0, 0, 0), RAW_HALF, STEEL, mass=".15")
    _box(body, f"{name}_saw", (0, 0, RAW_HALF[2]), (RAW_HALF[0] * 0.98, RAW_HALF[1] * 0.98, 0.0004), ".45 .46 .48 1",
         contype="0", conaffinity="0", mass="0")


def _finished_part(world, name, pos) -> None:
    body = ET.SubElement(world, "body", name=name, pos=_n(pos))
    ET.SubElement(body, "freejoint", name=f"{name}_free")
    _cyl(body, f"{name}_geom", (0, 0, 0), (FIN_R, FIN_HALF_H), ALU, mass=".12")
    _cyl(body, f"{name}_bore", (0, 0, FIN_HALF_H), (0.008, 0.0006), ".2 .21 .23 1", contype="0", conaffinity="0", mass="0")
    _cyl(body, f"{name}_chamfer", (0, 0, FIN_HALF_H - 0.001), (FIN_R * 0.88, 0.0012), ".92 .93 .95 1",
         contype="0", conaffinity="0", mass="0")


def cnc_xml(base_xml: str) -> str:
    """The example scene with the kitchen props replaced by the CNC cell."""
    root = ET.fromstring(base_xml)
    world = root.find("worldbody")
    for body in list(world.findall("body")):
        if body.get("name") in KITCHEN_PROPS:
            world.remove(body)
    ET.SubElement(world, "light", pos="0 -.2 1.6", dir="0 .2 -1", diffuse=".35 .35 .35", castshadow="false")
    _machine(world)
    _belt(world, "in_belt", IN_BELT_X)
    _belt(world, "out_belt", OUT_BELT_X)
    z_raw = BELT_TOP + RAW_HALF[2] + 0.001
    for i, y in enumerate((IN_STOP_Y, IN_STOP_Y - 0.1, IN_STOP_Y - 0.2, IN_STOP_Y - 0.3)):
        _raw_part(world, f"raw_part_{i}", (IN_BELT_X, y - 0.04, z_raw))  # start a bit back: the belt brings them in
    _finished_part(world, "fin_part_1", (OUT_BELT_X, -0.10, BELT_TOP + FIN_HALF_H + 0.001))
    _finished_part(world, "fin_part_2", (OUT_BELT_X, -0.26, BELT_TOP + FIN_HALF_H + 0.001))
    for x in (IN_BELT_X - 0.075, IN_BELT_X + 0.075):  # light barrier posts at the in-feed end stop
        _box(world, f"barrier_post_{x:+.2f}", (x, IN_STOP_Y, BELT_TOP + 0.02), (0.006, 0.006, 0.03), ".95 .8 .1 1",
             contype="0", conaffinity="0")
    _box(world, "in_belt_stop", (IN_BELT_X, IN_STOP_Y + RAW_HALF[1] + 0.006, BELT_TOP + 0.012), (0.05, 0.004, 0.012),
         FRAME)
    return ET.tostring(root, encoding="unicode")


class CellController:
    """Simulated process signals of the cell: belts, door, stack light; sensors read from the physics state."""

    BELT_SPEED = 0.06  # m/s

    def __init__(self, env):
        self.env = env
        self.door_target = 0.0  # 0 closed .. 1 open
        self.door = 0.0
        self.in_belt_on = True
        self.out_belt_on = True
        self.machine_done = False
        self._light_ids = {c: env.model.geom(f"cnc_light_{c}").id for c in ("red", "yellow", "green")}
        self._light_rgba = {c: env.model.geom_rgba[i].copy() for c, i in self._light_ids.items()}
        self.set_light(None)

    # actuators
    def set_light(self, color: str | None) -> None:
        bright = {"red": [0.95, 0.15, 0.12, 1], "yellow": [1, 0.8, 0.1, 1], "green": [0.2, 0.9, 0.3, 1]}
        for c, i in self._light_ids.items():
            self.env.model.geom_rgba[i] = bright[c] if c == color else self._light_rgba[c]

    def open_door(self, is_open: bool = True) -> None:
        self.door_target = 1.0 if is_open else 0.0

    # sensors
    def door_open(self) -> bool:
        return self.door > 0.98

    def part_at_stop(self) -> bool:
        return any(abs(p[0] - IN_BELT_X) < 0.05 and abs(p[1] - IN_STOP_Y) < 0.015 for p in self._parts("raw_part"))

    def _parts(self, prefix):
        m, d = self.env.model, self.env.data
        return [d.body(i).xpos for i in range(m.nbody) if (m.body(i).name or "").startswith(prefix)]

    def step(self, dt: float = 0.05) -> None:
        """Advance belts and door by one control step (call before env.step)."""
        d = self.env.data
        self.door += np.clip(self.door_target - self.door, -dt / 1.2, dt / 1.2)  # full stroke in 1.2 s
        d.mocap_pos[self.env.model.body("cnc_door").mocapid[0]] = DOOR_CLOSED + (DOOR_OPEN - DOOR_CLOSED) * self.door
        self._convey("raw_part", IN_BELT_X, +1, self.in_belt_on, dt)
        self._convey("fin_part", OUT_BELT_X, -1, self.out_belt_on, dt)

    def _convey(self, prefix, x, direction, on, dt):
        """Carry the parts lying on a belt; the in-feed queues them at the end stop."""
        if not on:
            return
        m, d = self.env.model, self.env.data
        rest_z = BELT_TOP + (RAW_HALF[2] if prefix == "raw_part" else FIN_HALF_H)
        on_belt = []
        for i in range(m.nbody):
            name = m.body(i).name or ""
            if not name.startswith(prefix):
                continue
            joint = d.joint(f"{name}_free")
            q = joint.qpos
            # Only parts lying on the belt; a part lifted even slightly (gripped) is left to the physics.
            if abs(q[0] - x) < 0.055 and abs(q[2] - rest_z) < 0.004 and BELT_Y0 < q[1] < BELT_Y1 + 0.02:
                on_belt.append(joint)
        on_belt.sort(key=lambda j: -direction * j.qpos[1])  # front part first
        limit = IN_STOP_Y if direction > 0 else BELT_Y0 + 0.03
        for joint in on_belt:
            q = joint.qpos
            if direction > 0:
                q[1] = min(q[1] + self.BELT_SPEED * dt, limit)
                limit = q[1] - 2 * RAW_HALF[1] - 0.01  # queue up behind the part in front
            else:
                q[1] = max(q[1] - self.BELT_SPEED * dt, limit)
            joint.qvel[:2] = 0.0
