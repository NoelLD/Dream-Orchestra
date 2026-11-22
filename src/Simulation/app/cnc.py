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

MACHINE_FRONT_Y = -0.07  # set back so the forearms clear posts and roof while serving the tray in front
VISE = np.array([0.0, -0.07])  # kept for reference; the arm never reaches into the machine any more
SEAT_Z = 0.80  # top of the transfer tray: parts rest here
# Transfer tray (pallet changer): the robot loads/unloads it in front of the door, the machine pulls it in.
# Reason: the YAM's top-down reach ends near y = -0.10 at x = 0, so the arm cannot work inside the machine.
TRAY_OUT = np.array([0.0, 0.11])  # far enough from the door posts for the gripper
TRAY_IN = np.array([0.0, -0.15])
TRAY_HALF = (0.07, 0.055, 0.006)
PARK = (2.0, 2.0, 0.05)  # off-stage place for parts not used in an episode
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
    # Inside: machine bed, spindle head above the tray's inner position.
    _box(world, "cnc_table", (0, -0.18, 0.772), (0.16, 0.10, 0.008), FRAME)
    _cyl(world, "cnc_spindle", (TRAY_IN[0], TRAY_IN[1], 1.05), (0.032, 0.06), ".7 .72 .75 1", contype="0", conaffinity="0")
    _cyl(world, "cnc_tool", (TRAY_IN[0], TRAY_IN[1], 0.965), (0.006, 0.025), ".9 .75 .3 1", contype="0", conaffinity="0")
    # Transfer tray on a rail through the door opening (mocap: moved by CellController).
    _box(world, "cnc_tray_rail", (0, (TRAY_OUT[1] + TRAY_IN[1]) / 2, 0.781), (0.02, 0.14, 0.004), ".5 .52 .55 1")
    tray = ET.SubElement(world, "body", name="cnc_tray", mocap="true", pos=_n((*TRAY_OUT, SEAT_Z - TRAY_HALF[2])))
    _box(tray, "cnc_tray_plate", (0, 0, 0), TRAY_HALF, ".3 .45 .62 1")
    for side in (-1, 1):  # locating rails on the plate edges
        _box(tray, f"cnc_tray_edge_{side}", (side * (TRAY_HALF[0] - 0.004), 0, TRAY_HALF[2] + 0.004),
             (0.004, TRAY_HALF[1], 0.004), ".2 .3 .42 1")
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
    # The finished part waiting on the tray (unload task); a spare one is swapped in when a cycle completes.
    _finished_part(world, "fin_part_0", (TRAY_OUT[0], TRAY_OUT[1], SEAT_Z + FIN_HALF_H + 0.001))
    _finished_part(world, "fin_part_9", PARK)


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


def _belt_x(world, name, y) -> None:
    """A belt running along x (across the table)."""
    cx, hl = (SORT_X0 + SORT_X1) / 2, (SORT_X1 - SORT_X0) / 2
    _box(world, f"{name}_frame", (cx, y, 0.775), (hl, 0.06, 0.015), ".62 .65 .68 1")
    _box(world, f"{name}_rubber", (cx, y, BELT_TOP - 0.0025), (hl, 0.05, 0.0025), RUBBER)
    for side in (-1, 1):
        _box(world, f"{name}_rail_{side}", (cx, y + side * 0.057, BELT_TOP + 0.003), (hl, 0.004, 0.006), ".7 .73 .76 1")
    for end, x in (("in", SORT_X0), ("out", SORT_X1)):
        _cyl(world, f"{name}_roller_{end}", (x, y, 0.782), (0.017, 0.055), ".5 .52 .55 1",
             euler="1.5708 0 0", contype="0", conaffinity="0")


def _finished_part(world, name, pos) -> None:
    body = ET.SubElement(world, "body", name=name, pos=_n(pos))
    ET.SubElement(body, "freejoint", name=f"{name}_free")
    _cyl(body, f"{name}_geom", (0, 0, 0), (FIN_R, FIN_HALF_H), ALU, mass=".12")
    _cyl(body, f"{name}_bore", (0, 0, FIN_HALF_H), (0.008, 0.0006), ".2 .21 .23 1", contype="0", conaffinity="0", mass="0")
    _cyl(body, f"{name}_chamfer", (0, 0, FIN_HALF_H - 0.001), (FIN_R * 0.88, 0.0012), ".92 .93 .95 1",
         contype="0", conaffinity="0", mass="0")


# Sorting conveyor (cell "conveyor"): one belt across the table in front of both arms, parts travel +x.
SORT_BELT_Y = -0.03
SORT_X0, SORT_X1 = -0.62, 0.62
SORT_END_X = 0.55  # end stop: parts nobody sorted queue up here
SORT_GAP = 0.13  # centre distance in the queue: room for the open gripper (95 mm) between neighbours
SORT_ZONE = {"right": -0.20, "left": 0.20}  # pick stations (light barriers); right arm first, then left
SORT_KIND = {"right": "cyl_part", "left": "raw_part"}  # right arm: round parts, left arm: cubes
SORT_BOX = {"right": np.array([-0.31, 0.095]), "left": np.array([0.31, 0.095])}
KLT = SORT_BOX["left"]  # blue KLT for the cubes
KLT_HALF = (0.075, 0.06, 0.03)  # inner clearance for the open gripper (95 mm) plus margin
RAW_STAGE = np.array([0.32, 0.10])  # CNC cell: raw part on a staging pedestal at belt height (left arm)
STAGE_TOP = 0.797
FIN_BOX = np.array([-0.30, 0.10])  # CNC cell: box for finished parts (right arm)
FIN_BOX_HALF = (0.07, 0.06, 0.02)
CELLS = ("conveyor", "cnc")


def _crate(world, name, xy, half, rgba):
    """Open-top box (KLT): floor + four walls, static."""
    body = ET.SubElement(world, "body", name=name, pos=_n((*xy, TABLE_Z)))
    hx, hy, hz = half
    t = 0.004
    _box(body, f"{name}_floor", (0, 0, t), (hx, hy, t), rgba)
    for side in (-1, 1):
        _box(body, f"{name}_wall_x{side}", (side * (hx - t), 0, hz), (t, hy, hz), rgba)
        _box(body, f"{name}_wall_y{side}", (0, side * (hy - t), hz), (hx, t, hz), rgba)


def cell_xml(base_xml: str, cell: str) -> str:
    """The example scene with the kitchen props replaced by one of two cells (two separate experiments).

    conveyor: in-feed belt with raw parts queued at a light barrier and end stop; a KLT crate to put them in.
    cnc:      closed machine with lifting door, transfer tray and stack light; a staging plate with a raw part
              (left arm) and a tray for finished parts (right arm).
    """
    if cell not in CELLS:
        raise ValueError(f"unknown cell {cell!r}")
    root = ET.fromstring(base_xml)
    world = root.find("worldbody")
    for body in list(world.findall("body")):
        if body.get("name") in KITCHEN_PROPS:
            world.remove(body)
    visual = root.find("visual/global")
    if visual is not None:  # room for 1280x720 overview renders (trailer, control room)
        visual.set("offwidth", "1280")
        visual.set("offheight", "720")
    ET.SubElement(world, "light", pos="0 -.2 1.6", dir="0 .2 -1", diffuse=".35 .35 .35", castshadow="false")
    if cell == "conveyor":
        _belt_x(world, "sort_belt", SORT_BELT_Y)
        # mixed parts queued at the feed end: cubes (raw blanks) and round turned parts, alternating
        x = -0.30  # front part; the rest queue behind it on the belt (all supported by the belt)
        for k in range(3):
            if k % 2 == 0:
                _finished_part(world, f"cyl_part_{k // 2}", (x, SORT_BELT_Y, BELT_TOP + FIN_HALF_H + 0.001))
            else:
                _raw_part(world, f"raw_part_{k // 2}", (x, SORT_BELT_Y, BELT_TOP + RAW_HALF[2] + 0.001))
            x -= SORT_GAP
        for k in range(4):  # spares off stage: the feeder puts them on the belt (sorted parts stay in the boxes)
            spare = (PARK[0] + 0.1 * k, PARK[1], PARK[2])
            if k % 2 == 0:
                _finished_part(world, f"cyl_part_{3 + k // 2}", spare)
            else:
                _raw_part(world, f"raw_part_{3 + k // 2}", spare)
        for side, zx in SORT_ZONE.items():  # light barrier posts at both stations
            for dy in (-0.075, 0.075):
                _box(world, f"barrier_{side}_{dy:+.2f}", (zx, SORT_BELT_Y + dy, BELT_TOP + 0.02),
                     (0.006, 0.006, 0.03), ".95 .8 .1 1", contype="0", conaffinity="0")
        _box(world, "sort_end_stop", (SORT_END_X + RAW_HALF[0] + 0.03, SORT_BELT_Y, BELT_TOP + 0.012),
             (0.004, 0.05, 0.012), FRAME)
        _crate(world, "klt", SORT_BOX["left"], KLT_HALF, ".15 .35 .75 1")
        _crate(world, "round_box", SORT_BOX["right"], KLT_HALF, ".2 .55 .3 1")
    else:
        _machine(world)
        _box(world, "raw_stage", (*RAW_STAGE, (TABLE_Z + STAGE_TOP) / 2), (0.04, 0.04, (STAGE_TOP - TABLE_Z) / 2),
             ".55 .57 .6 1")
        _raw_part(world, "raw_part_0", (*RAW_STAGE, STAGE_TOP + RAW_HALF[2] + 0.001))
        _crate(world, "fin_box", FIN_BOX, FIN_BOX_HALF, ".2 .55 .3 1")
    return ET.tostring(root, encoding="unicode")


def cnc_xml(base_xml: str) -> str:
    """Backward-compatible name: the CNC cell."""
    return cell_xml(base_xml, "cnc")


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
        self.tray = 0.0  # 0 out (robot side) .. 1 in (under the spindle)
        self.tray_target = 0.0
        self.phases: list[list] = []  # machining cycle: [name, remaining seconds]
        self.cycles = 0
        names = {env.model.body(i).name for i in range(env.model.nbody)}
        self.has_machine = "cnc_door" in names
        self.sorting = "sort_belt_frame" in {env.model.geom(i).name for i in range(env.model.ngeom)}
        self._light_ids = ({c: env.model.geom(f"cnc_light_{c}").id for c in ("red", "yellow", "green")}
                           if self.has_machine else {})
        self._light_rgba = {c: env.model.geom_rgba[i].copy() for c, i in self._light_ids.items()}
        self.set_light(None)

    # actuators
    def set_light(self, color: str | None) -> None:
        bright = {"red": [0.95, 0.15, 0.12, 1], "yellow": [1, 0.8, 0.1, 1], "green": [0.2, 0.9, 0.3, 1]}
        for c, i in self._light_ids.items():
            self.env.model.geom_rgba[i] = bright[c] if c == color else self._light_rgba[c]

    def open_door(self, is_open: bool = True) -> None:
        self.door_target = 1.0 if is_open else 0.0

    def start_cycle(self) -> bool:
        """Machine cycle: tray in, door closes, machining, raw part becomes a finished part, door opens, tray out."""
        if self.phases or not self.door_open() or self.tray > 0.01:
            return False
        self.machine_done = False
        self.phases = [["tray_in", 1.6], ["close", 1.3], ["machining", 3.0], ["open", 1.3], ["tray_out", 1.6]]
        return True

    # sensors
    def door_open(self) -> bool:
        return self.door > 0.98

    def tray_out(self) -> bool:
        return self.tray < 0.01

    def part_on_tray(self, prefix: str) -> str | None:
        """Name of a part of this kind lying on the tray, if any."""
        m, d = self.env.model, self.env.data
        centre = self._tray_xy()
        for i in range(m.nbody):
            name = m.body(i).name or ""
            if name.startswith(prefix):
                p = d.body(i).xpos
                if abs(p[0] - centre[0]) < TRAY_HALF[0] and abs(p[1] - centre[1]) < TRAY_HALF[1] \
                        and SEAT_Z < p[2] < SEAT_Z + 0.05:
                    return name
        return None

    def _tray_xy(self) -> np.ndarray:
        return TRAY_OUT + (TRAY_IN - TRAY_OUT) * self.tray

    def waiting(self) -> tuple[str, str] | None:
        """(arm, part) when a part sits at the pick station of the arm that sorts its kind (belt stopped)."""
        if not self.sorting:
            return None
        for name, joint in self._sort_parts():
            q = joint.qpos
            for arm, zx in SORT_ZONE.items():
                if name.startswith(SORT_KIND[arm]) and abs(q[0] - zx) < 0.004:
                    return arm, name
        return None

    def at_barrier(self, arm: str) -> bool:
        """Light barrier of a station: any part between its posts."""
        return any(abs(j.qpos[0] - SORT_ZONE[arm]) < 0.03 for _, j in self._sort_parts())

    def _sort_parts(self):
        m, d = self.env.model, self.env.data
        out = []
        for i in range(m.nbody):
            name = m.body(i).name or ""
            if name.startswith(("raw_part", "cyl_part")):
                joint = d.joint(f"{name}_free")
                q = joint.qpos
                rest = BELT_TOP + (RAW_HALF[2] if name.startswith("raw") else FIN_HALF_H)
                if abs(q[1] - SORT_BELT_Y) < 0.055 and abs(q[2] - rest) < 0.004 and SORT_X0 - 0.5 < q[0] < SORT_X1:
                    out.append((name, joint))
        return out

    def _convey_sort(self, dt) -> None:
        """Belt along +x. It stops while a part waits at the station of its arm; parts never overlap."""
        if not self.in_belt_on or self.waiting():
            return
        parts = sorted(self._sort_parts(), key=lambda nj: -nj[1].qpos[0])  # front (largest x) first
        ahead = None
        for name, joint in parts:
            q = joint.qpos
            limit = SORT_END_X
            for arm, zx in SORT_ZONE.items():
                if name.startswith(SORT_KIND[arm]) and q[0] <= zx + 1e-6:
                    limit = min(limit, zx)
            if ahead is not None:
                limit = min(limit, ahead - SORT_GAP)
            q[0] = min(q[0] + self.BELT_SPEED * dt, limit) if q[0] < limit else q[0]
            joint.qvel[:] = 0.0
            ahead = q[0]

    def feed(self, rng=None) -> str | None:
        """Put one sorted (or parked) part back at the feed end if there is room: an endless demo stream."""
        m, d = self.env.model, self.env.data
        on_belt = self._sort_parts()
        if any(j.qpos[0] < SORT_X0 + 0.06 + SORT_GAP for _, j in on_belt):
            return None
        names = [n for n, _ in on_belt]
        free = [m.body(i).name for i in range(m.nbody)  # only parked spares, never parts already sorted
                if (m.body(i).name or "").startswith(("raw_part", "cyl_part")) and m.body(i).name not in names
                and np.linalg.norm(d.body(i).xpos[:2] - np.array(PARK[:2])) < 1.0]
        if not free:
            return None
        rng = rng or np.random.default_rng()
        name = free[int(rng.integers(len(free)))]
        j = d.joint(f"{name}_free")
        rest = BELT_TOP + (RAW_HALF[2] if name.startswith("raw") else FIN_HALF_H) + 0.001
        j.qpos[:7] = [SORT_X0 + 0.06, SORT_BELT_Y, rest, 1, 0, 0, 0]
        j.qvel[:] = 0.0
        return name

    def _held(self, name: str) -> bool:
        return self.env.data.body(name).xpos[2] > BELT_TOP + 0.06  # lifted by a gripper right now

    def part_at_stop(self) -> bool:
        return any(abs(p[0] - IN_BELT_X) < 0.05 and abs(p[1] - IN_STOP_Y) < 0.015 for p in self._parts("raw_part"))

    def _parts(self, prefix):
        m, d = self.env.model, self.env.data
        return [d.body(i).xpos for i in range(m.nbody) if (m.body(i).name or "").startswith(prefix)]

    def step(self, dt: float = 0.05) -> None:
        """Advance belts and door by one control step (call before env.step)."""
        d = self.env.data
        if self.sorting:
            self._convey_sort(dt)
            return
        if not self.has_machine:
            self._convey("raw_part", IN_BELT_X, +1, self.in_belt_on, dt)
            return
        self.door += np.clip(self.door_target - self.door, -dt / 1.2, dt / 1.2)  # full stroke in 1.2 s
        d.mocap_pos[self.env.model.body("cnc_door").mocapid[0]] = DOOR_CLOSED + (DOOR_OPEN - DOOR_CLOSED) * self.door
        self._run_cycle(dt)
        before = self._tray_xy()
        self.tray += np.clip(self.tray_target - self.tray, -dt / 1.6, dt / 1.6)
        after = self._tray_xy()
        d.mocap_pos[self.env.model.body("cnc_tray").mocapid[0]] = [*after, SEAT_Z - TRAY_HALF[2]]
        if np.any(after != before):  # parts lying on the tray ride along
            for prefix in ("raw_part", "fin_part"):
                for name in self._parts_on_tray(prefix, before):
                    j = d.joint(f"{name}_free")
                    j.qpos[0:2] += after - before
                    j.qvel[:] = 0.0

    def _parts_on_tray(self, prefix, centre):
        m, d = self.env.model, self.env.data
        out = []
        for i in range(m.nbody):
            name = m.body(i).name or ""
            p = d.body(i).xpos
            if name.startswith(prefix) and abs(p[0] - centre[0]) < TRAY_HALF[0] and \
                    abs(p[1] - centre[1]) < TRAY_HALF[1] and SEAT_Z < p[2] < SEAT_Z + 0.03:
                out.append(name)
        return out

    def _run_cycle(self, dt):
        if not self.phases:
            return
        phase = self.phases[0]
        name = phase[0]
        if name == "tray_in":
            self.tray_target = 1.0
        elif name == "close":
            self.open_door(False)
        elif name == "machining":
            self.set_light("yellow")
        elif name == "open":
            self.open_door(True)
        elif name == "tray_out":
            self.tray_target = 0.0
        phase[1] -= dt
        if phase[1] > 0:
            return
        self.phases.pop(0)
        if name == "machining":  # the raw part comes out machined: swap the bodies on the tray
            raw = self._parts_on_tray("raw_part", self._tray_xy())
            spare = next((n for n in ("fin_part_9", "fin_part_0")
                          if np.linalg.norm(self.env.data.body(n).xpos[:2] - PARK[:2]) < 0.5), None)
            if raw and spare:
                d = self.env.data
                pos = d.body(raw[0]).xpos.copy()
                d.joint(f"{raw[0]}_free").qpos[:3] = PARK
                d.joint(f"{spare}_free").qpos[:3] = [pos[0], pos[1], SEAT_Z + FIN_HALF_H + 0.001]
                d.joint(f"{spare}_free").qpos[3:7] = [1, 0, 0, 0]
                d.joint(f"{spare}_free").qvel[:] = 0.0
            self.set_light(None)
        if not self.phases:
            self.machine_done = True
            self.cycles += 1
            self.set_light("green")

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
