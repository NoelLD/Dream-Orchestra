"""Zellen im Workflow: Prompt-Blöcke mit Zellen-Tasks und Zellen-Geräte über den Simulationsdienst (`/cells/*`).

`CellDreamClient` legt sich um den eigentlichen Dream-Client. Nennt ein Prompt-Block einen Zellen-Task (Skill-Name wie
`cnc_load` oder genau dessen Prompt), führt der Simulationsdienst ihn mit dem geskripteten Referenz-Controller aus,
aber nur, wenn das ausdrücklich gewählt ist: Backend-Modus `sim` oder Checkpoint `referenz`. Mit einem gelernten
Checkpoint oder im Modus `real` endet der Block mit einer klaren Meldung, statt still geskriptet zu laufen (Dream-1 in
den Zellen läuft bisher nur in der Auswertung, `tools/eval_cells.py`). Die Lauf-ID beginnt mit `geskriptet-`.
Erfolg = Prüfung der Zelle (Teil ruhig im Ziel, kein Kontakt Arm–Zelle). Alles andere geht an den inneren Client.

`CellBridge` spiegelt die Sensoren der Zellen-Sitzung in Geräte (`zelle-…`). Ist die Zelle nicht erreichbar oder die
letzte Abfrage zu alt, melden diese Sensoren „nicht verfügbar“ statt eines alten Werts. Aktor-Werte gehen als
Zellen-Aktion raus; der Aktor-Block wartet auf die Quittung und endet sonst im Fehlerpfad.
"""

import asyncio
import itertools
import time
from typing import Any

from app.devices.adapter import Device, DeviceAdapter, DeviceType
from app.dream.client import DreamClient, DreamError, DreamRun
from app.dream.simulation import SimulationApi
from app.errors import ConflictError, UpstreamError

SESSION_START_S = 90.0  # Zelle bauen + erstes Bild; unter Last antwortet der Dienst währenddessen kurz nicht
BUSY_CODES = frozenset({"busy", "simulation_unavailable"})  # beim Start: weiter warten statt abbrechen
REFERENCE = "referenz"  # Checkpoint-Wert: Zellen-Task ausdrücklich mit dem geskripteten Referenz-Controller
CYCLE_ACK_S = 5.0  # so lange auf "Maschine läuft" oder eine Sperre warten
REFILL_TASKS = frozenset({"cnc_load"})  # brauchen ein frisches Rohteil; die Simulation hat keine Zuführung
REFILL_NOTE = "neues Rohteil: Zellen-Sitzung neu gestartet (Simulation ohne Teilezuführung)"

_SPEC = [  # (ID, Name, Typ, Sensor in der Sitzung oder None für reine Aktoren)
    ("zelle-maschine-fertig", "Zelle: Maschine fertig", DeviceType.SWITCH, "machine_done"),
    ("zelle-rohteil-auf-platte", "Zelle: Rohteil auf Platte", DeviceType.SWITCH, "raw_part_on_tray"),
    ("zelle-fertigteil-auf-platte", "Zelle: Fertigteil auf Platte", DeviceType.SWITCH, "finished_part_on_tray"),
    ("zelle-tuer-offen", "Zelle: Tür offen", DeviceType.SWITCH, "door_open"),
    ("zelle-cnc-maschine", "Zelle: CNC-Maschine", DeviceType.MACHINE, "machine_running"),
    ("zelle-ampel-rot", "Zelle: Ampel rot", DeviceType.LAMP, None),
    ("zelle-ampel-gruen", "Zelle: Ampel grün", DeviceType.LAMP, None),
]
CELL_DEVICES: dict[str, tuple[Device, str | None]] = {
    device_id: (Device(device_id, name, device_type, False), sensor) for device_id, name, device_type, sensor in _SPEC
}
ACTIONS = {  # Aktor -> (Aktion bei an, Aktion bei aus)
    "zelle-cnc-maschine": ("cycle_start", None),
    "zelle-ampel-rot": ("light_red", "light_off"),
    "zelle-ampel-gruen": ("light_green", "light_off"),
}


def cell_task_for(skill: str, prompt: str, cells: list[dict[str, Any]]) -> tuple[str, str] | None:
    """(Zelle, Task), wenn der Skill-Name ein Zellen-Task ist oder der Prompt genau einem Task-Prompt entspricht."""
    text = prompt.strip().lower()
    for cell in cells:
        for task in cell["tasks"]:
            if skill == task["task"] or text == task["prompt"].strip().lower():
                return cell["cell"], task["task"]
    return None


def _after(events: list[dict[str, Any]], marker: tuple[float, str] | None) -> list[dict[str, Any]]:
    """Ereignisse nach dem gemerkten (Zeit, Text); die Sitzung liefert nur die letzten 20."""
    if marker is None:
        return events
    keys = [(e["t"], e["text"]) for e in events]
    return events[keys.index(marker) + 1 :] if marker in keys else events


def _blank_used(session: dict[str, Any]) -> bool:
    """Das Rohteil dieser Sitzung ist verbraucht: ein Maschinenzyklus lief oder ein Laden war schon erfolgreich."""
    if int((session.get("sensors") or {}).get("cycles") or 0) >= 1:
        return True
    return any(
        (e.get("result") or {}).get("task") in REFILL_TASKS and (e.get("result") or {}).get("passed")
        for e in session.get("events") or []
    )


def _marker(session: dict[str, Any] | None) -> tuple[float, str] | None:
    events = (session or {}).get("events") or []
    return (events[-1]["t"], events[-1]["text"]) if events else None


class CellDreamClient:
    def __init__(self, inner: DreamClient, api: SimulationApi, *, allow_scripted: bool, poll_s: float = 0.5) -> None:
        self.inner = inner
        self.api = api
        self.mode = inner.mode
        self.allow_scripted = allow_scripted  # Modus sim: Zellen-Tasks ohne weitere Angabe geskriptet
        self.poll_s = poll_s
        self._cells: list[dict[str, Any]] | None = None
        self._runs: dict[str, tuple[str, tuple[float, str] | None]] = {}  # run_id -> (task, letztes Ereignis davor)
        self._notes: dict[str, str] = {}  # run_id -> Hinweis fürs Protokoll
        self._ids = itertools.count(1)

    @property
    def cell_prompts(self) -> frozenset[str]:
        """Prompts der Zellen-Tasks (klein geschrieben); die Prüfung vor dem Start verlangt dafür keinen Skill."""
        return frozenset(t["prompt"].strip().lower() for c in self._cells or [] for t in c["tasks"])

    @property
    def cell_devices(self) -> frozenset[str]:
        """Geräte-IDs der Zelle; die Engine merkt sich daran, dass ein Lauf die Zelle benutzt."""
        return frozenset(CELL_DEVICES)

    async def halt_cell(self) -> bool:
        """STOP: Zellen-Sitzung beenden, damit Arm und Maschine anhalten. True, wenn eine Sitzung lief."""
        if await self._session() is None:
            return False
        try:
            await self.api.request("DELETE", "/cells/session")
        except UpstreamError as exc:
            raise DreamError(exc.detail) from exc
        return True

    async def prime(self, retry_s: float = 5.0) -> None:
        """Zellen-Liste laden, bis der Simulationsdienst antwortet (beim Start des Backends, im Hintergrund)."""
        while not await self._cell_list():  # noqa: ASYNC110 (externer Dienst, kein Ereignis zum Warten)
            await asyncio.sleep(retry_s)

    async def _cell_list(self) -> list[dict[str, Any]]:
        if self._cells is None:
            try:
                self._cells = await self.api.request("GET", "/cells")
            except UpstreamError:
                return []  # Dienst ohne Zellen: alles an den inneren Client
        return self._cells or []

    async def _session(self) -> dict[str, Any] | None:
        try:
            data: dict[str, Any] = await self.api.request("GET", "/cells/session")
            return data
        except UpstreamError as exc:
            if exc.code == "no_session":
                return None
            raise DreamError(exc.detail) from exc

    async def _ensure_session(self, cell: str) -> dict[str, Any]:
        session = await self._session()
        if session is None or session.get("cell") != cell:
            deadline = time.monotonic() + SESSION_START_S
            try:
                await self.api.request("POST", f"/cells/{cell}/session")
            except UpstreamError as exc:
                if exc.code != "simulation_unavailable":  # Zeitüberschreitung beim Aufbau: Sitzung entsteht trotzdem
                    raise DreamError(exc.detail) from exc
            while True:
                try:
                    session = await self._session()
                except DreamError:
                    session = None  # Dienst baut die Zelle und antwortet kurz nicht
                if session is not None and session.get("status") == "running":
                    break
                if time.monotonic() > deadline:
                    raise DreamError(f"Zelle {cell} startet nicht innerhalb von {SESSION_START_S:g} s")
                await asyncio.sleep(self.poll_s)
        return session

    async def start(self, *, skill: str, prompt: str, checkpoint: str | None, timeout_s: float | None = None) -> str:
        found = cell_task_for(skill, prompt, await self._cell_list())
        if found is None:
            return await self.inner.start(skill=skill, prompt=prompt, checkpoint=checkpoint, timeout_s=timeout_s)
        cell, task = found
        if checkpoint and checkpoint != REFERENCE:
            raise DreamError(
                f"Zellen-Task {task} mit Checkpoint {checkpoint}: Dream-1 in der Zelle ist im Workflow noch nicht "
                f"angebunden (nur in der Auswertung). Checkpoint '{REFERENCE}' wählt den geskripteten "
                "Referenz-Controller."
            )
        if not self.allow_scripted and checkpoint != REFERENCE:
            raise DreamError(
                f"Modus {self.mode}: Zellen-Task {task} würde geskriptet laufen, nicht mit Dream-1. "
                f"Checkpoint '{REFERENCE}' setzen, um den Referenz-Controller ausdrücklich zu wählen."
            )
        session = await self._ensure_session(cell)
        note = None
        if task in REFILL_TASKS and _blank_used(session):
            try:
                await self.api.request("DELETE", "/cells/session")
            except UpstreamError as exc:
                raise DreamError(exc.detail) from exc
            session, note = await self._ensure_session(cell), REFILL_NOTE
        marker = _marker(session)
        deadline = time.monotonic() + SESSION_START_S
        while True:
            try:
                await self.api.request("POST", "/cells/session/task", {"task": task})
                break
            except UpstreamError as exc:
                if exc.code in BUSY_CODES and time.monotonic() < deadline:
                    await asyncio.sleep(self.poll_s)
                    continue
                raise DreamError(exc.detail) from exc
        run_id = f"geskriptet-{task}-{next(self._ids)}"
        self._runs[run_id] = (task, marker)
        if note:
            self._notes[run_id] = note
        return run_id

    async def status(self, run_id: str) -> DreamRun:
        if run_id not in self._runs:
            return await self.inner.status(run_id)
        task, marker = self._runs[run_id]
        session = await self._session()
        if session is None:
            return DreamRun(run_id, "error", False, error="Zellen-Sitzung beendet")
        for event in _after(session.get("events") or [], marker):
            result = event.get("result")
            if result and result.get("task") == task:
                ok = bool(result.get("passed"))
                error = None if ok else f"Referenz-Controller: {result.get('reason')}"
                note = self._notes.pop(run_id, None)
                return DreamRun(run_id, "succeeded" if ok else "failed", ok, error=error, note=note)
            text = event["text"]  # vom Task selbst gesperrt (z. B. Entladen ohne Fertigteil, falsche Zelle)
            if event.get("gate") is False and (task in text or text.startswith("Entladen gesperrt")):
                return DreamRun(run_id, "failed", False, error=text)
        return DreamRun(run_id, "running")

    async def stop(self, run_id: str) -> None:
        if run_id not in self._runs:
            await self.inner.stop(run_id)
            return
        try:  # ein geskripteter Task lässt sich nicht anhalten: die Sitzung wird beendet
            await self.api.request("DELETE", "/cells/session")
        except UpstreamError as exc:
            raise DreamError(exc.detail) from exc

    async def aclose(self) -> None:
        await self.inner.aclose()


class CellBridge:
    """Zellen-Sensoren -> Geräte (Abfrage, mit Frische), Geräte-Aktoren -> Zellen-Aktionen (mit Quittung)."""

    def __init__(self, api: SimulationApi, devices: DeviceAdapter, *, poll_s: float = 0.5) -> None:
        self.api = api
        self.devices = devices
        self.poll_s = poll_s
        self.max_age_s = max(3 * poll_s, 2.0)
        self._last_ok: float | None = None
        self._fresh_sensors: set[str] = set()
        self._last_sim_s = -1.0  # Simulationszeit des zuletzt gespiegelten Schnappschusses
        self._last_error = "noch keine Verbindung zur Zelle"
        self._task: asyncio.Task[None] | None = None

    async def poll_once(self) -> None:
        try:
            session = await self.api.request("GET", "/cells/session")
        except UpstreamError as exc:
            self._last_ok = None
            self._last_error = "keine Zellen-Sitzung" if exc.code == "no_session" else exc.detail
            return
        self._mirror(session)

    def _mirror(self, session: Any) -> None:
        """Sensoren eines Schnappschusses in die Geräte schreiben. Ein älterer Schnappschuss (z. B. eine Abfrage, die
        vor einem Maschinenstart losging und danach ankommt) überschreibt keinen neueren."""
        if not isinstance(session, dict) or session.get("status") != "running":
            self._last_ok = None
            self._last_error = "Zellen-Sitzung ist nicht bereit"
            return
        sim_s = session.get("sim_seconds")
        if isinstance(sim_s, int | float):
            if self._last_sim_s - 5.0 < sim_s < self._last_sim_s:  # leicht älter: verwerfen (viel älter = neue Sitzung)
                return
            self._last_sim_s = float(sim_s)
        sensors = session.get("sensors") or {}
        if not isinstance(sensors, dict):
            sensors = {}
        self._fresh_sensors = {name for name, value in sensors.items() if isinstance(value, bool)}
        for device_id, (_, sensor) in CELL_DEVICES.items():
            if sensor and sensor in self._fresh_sensors:
                try:
                    current = self.devices.get(device_id)
                except Exception:  # Gerät gelöscht oder (noch) als nicht verfügbar gemeldet
                    current = None
                value = bool(sensors[sensor])
                if current is None or current.value != value:
                    self.devices.set(device_id, value)
        self._last_ok = time.monotonic()

    def unavailable(self, device_id: str) -> str | None:
        """Grund, warum ein Zellen-Sensor gerade keinen gültigen Wert hat, sonst None (Wächter im Gerätestamm)."""
        if CELL_DEVICES.get(device_id, (None, None))[1] is None:
            return None
        if self._last_ok is None:
            return f"Sensor {device_id} nicht verfügbar: {self._last_error}"
        if CELL_DEVICES[device_id][1] not in self._fresh_sensors:
            return f"Sensor {device_id} nicht verfügbar: kein gültiger Wert in der letzten Abfrage"
        age = time.monotonic() - self._last_ok
        if age > self.max_age_s:
            return f"Sensor {device_id} nicht verfügbar: letzter Wert {age:.1f} s alt"
        return None

    async def _loop(self) -> None:
        while True:
            await self.poll_once()
            await asyncio.sleep(self.poll_s)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def apply(self, device: Device) -> None:
        """Schickt die Zellen-Aktion zum neuen Aktor-Wert und wartet auf die Quittung; Fehler -> Exception."""
        on_off = ACTIONS.get(device.id)
        action = None if on_off is None else (on_off[0] if device.value else on_off[1])
        if action is None:
            return
        session = await self.api.request("GET", "/cells/session")  # UpstreamError, wenn keine Sitzung/kein Dienst
        marker = _marker(session)
        await self.api.request("POST", "/cells/session/action", {"action": action})
        if action != "cycle_start":
            return
        deadline = time.monotonic() + CYCLE_ACK_S
        while time.monotonic() < deadline:
            session = await self.api.request("GET", "/cells/session")
            if ((session or {}).get("sensors") or {}).get("machine_running"):
                # Quittung: die Geräte sofort auf diesen Stand bringen, damit ein "fertig" vom vorigen Zyklus
                # nicht als frisch gilt, bevor die nächste Abfrage kommt
                self._mirror(session)
                return
            for event in _after((session or {}).get("events") or [], marker):
                if event.get("gate") is False:
                    raise ConflictError(f"Maschine nicht gestartet: {event['text']}")
            await asyncio.sleep(self.poll_s / 2)
        raise ConflictError(f"Maschine nicht gestartet: keine Rückmeldung in {CYCLE_ACK_S:g} s")
