"""Zellen im Workflow: Prompt-Blöcke mit Zellen-Tasks und Zellen-Geräte gegen einen nachgebauten Dienst, ohne Netz."""

import json
import pathlib

import httpx
import pytest

from app.devices.adapter import DeviceRegistry, VirtualAdapter
from app.dream.cells import CELL_DEVICES, REFILL_NOTE, CellBridge, CellDreamClient, cell_task_for
from app.dream.client import DreamError, DreamRun
from app.dream.simulation import SimulationApi
from app.errors import ConflictError, UpstreamError

CELLS = [
    {
        "cell": "cnc",
        "tasks": [
            {"task": "cnc_load", "arm": "left", "prompt": "put the metal block on the machine tray"},
            {"task": "cnc_unload", "arm": "right", "prompt": "put the finished part in the green box"},
        ],
    },
    {
        "cell": "conveyor",
        "tasks": [{"task": "sort_round", "arm": "right", "prompt": "put the round part in the green box"}],
    },
]


class FakeCells:
    """Eine Sitzung; ein Task braucht `polls_per_task` Abfragen und besteht, außer Entladen ohne Fertigteil."""

    def __init__(self, polls_per_task: int = 2) -> None:
        self.session: dict | None = None
        self.polls_per_task = polls_per_task
        self.left = 0
        self.actions: list[str] = []
        self.finished_part = False
        self.block_cycle = False
        self.cycle_left = 0
        self.deletes = 0
        self.queue_polls = 0  # > 0: ein Task steht so viele Abfragen in der Warteschlange, bevor er „busy“ zeigt
        self.queued: str | None = None
        self.task_posts: list[dict] = []

    def _event(self, text: str, **data: object) -> None:
        assert self.session is not None
        self.session["events"].append({"t": float(len(self.session["events"])), "text": text, **data})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        match request.method, request.url.path:
            case "GET", "/cells":
                return httpx.Response(200, json=CELLS)
            case "POST", path if path.endswith("/session"):
                cell = path.split("/")[2]
                self.session = {
                    "cell": cell,
                    "status": "running",
                    "busy": None,
                    "events": [],
                    "sensors": {
                        "machine_done": False,
                        "door_open": True,
                        "raw_part_on_tray": False,
                        "finished_part_on_tray": False,
                        "machine_running": False,
                    },
                }
                return httpx.Response(202, json={"cell": cell})
            case "GET", "/cells/session":
                if self.session is None:
                    return httpx.Response(409, json={"error": "no_session", "detail": "no cell session"})
                self.session["sim_seconds"] = self.session.get("sim_seconds", 0.0) + 0.5
                if self.queued is not None:
                    self.queue_polls -= 1
                    if self.queue_polls <= 0:
                        self.session["busy"], self.left, self.queued = self.queued, self.polls_per_task, None
                    return httpx.Response(200, json=self.session)  # Warteschlange: noch kein Zeichen in der Sitzung
                if self.cycle_left > 0:
                    self.cycle_left -= 1
                    if self.cycle_left == 0:
                        self.session["sensors"].update(machine_running=False, machine_done=True)
                        self.session["sensors"]["cycles"] = self.session["sensors"].get("cycles", 0) + 1
                        self.finished_part = True
                if self.session["busy"] and self.left > 0:
                    self.left -= 1
                    if self.left == 0:
                        task = self.session["busy"]
                        self.session["busy"] = None
                        self._event(
                            f"Prüfung {task}: bestanden (ok)",
                            gate=True,
                            result={"task": task, "seed": 1000, "passed": True, "reason": "ok"},
                        )
                        self.session["last_result"] = {"task": task, "passed": True}
                        if task == "cnc_load":
                            self.session["sensors"]["raw_part_on_tray"] = True
                return httpx.Response(200, json=self.session)
            case "POST", "/cells/session/task":
                assert self.session is not None
                self.task_posts.append(body)
                if self.queue_polls > 0:  # wie die Simulation vor dem Neustart: erst einreihen, später „busy“
                    self.queued = body["task"]
                    return httpx.Response(202, json={"queued": "task"})
                if self.session["busy"]:
                    return httpx.Response(409, json={"error": "busy", "detail": "busy"})
                if body["task"] == "cnc_unload" and not self.finished_part:
                    self._event("Entladen gesperrt: kein Fertigteil auf der Platte", gate=False)
                    return httpx.Response(202, json={"queued": "task"})
                self.session["busy"], self.left = body["task"], self.polls_per_task
                return httpx.Response(202, json={"queued": "task"})
            case "POST", "/cells/session/action":
                self.actions.append(body["action"])
                if body["action"] == "cycle_start" and self.session:
                    if self.block_cycle or not self.session["sensors"]["raw_part_on_tray"]:
                        self._event("Zyklus gesperrt: kein Rohteil auf der Platte", gate=False)
                    else:
                        self.session["sensors"].update(machine_running=True, machine_done=False)
                        self.cycle_left = 2  # Abfragen bis "fertig"
                return httpx.Response(202, json={"queued": body["action"]})
            case "DELETE", "/cells/session":
                self.deletes += 1
                self.session = None
                return httpx.Response(204)
        return httpx.Response(404, json={"error": "not_found", "detail": request.url.path})


class NoDream:
    mode = "sim"

    async def start(self, **_: object) -> str:
        return "run_fruit"

    async def status(self, run_id: str) -> DreamRun:
        return DreamRun(run_id, "succeeded", True)

    async def stop(self, run_id: str) -> None: ...

    async def aclose(self) -> None: ...


def client(fake: FakeCells) -> CellDreamClient:
    return CellDreamClient(
        NoDream(), SimulationApi("http://sim", transport=httpx.MockTransport(fake)), allow_scripted=True
    )


async def finish(dream: CellDreamClient, run_id: str) -> DreamRun:
    for _ in range(20):
        run = await dream.status(run_id)
        if run.terminal:
            return run
    raise AssertionError("not terminal")


def test_task_lookup_by_skill_name_or_prompt() -> None:
    assert cell_task_for("cnc_load", "irgendwas", CELLS) == ("cnc", "cnc_load")
    assert cell_task_for("dream-1-base", "put the metal block on the machine tray", CELLS) == ("cnc", "cnc_load")
    assert cell_task_for("pick-banana", "pick up the banana", CELLS) is None


@pytest.mark.asyncio
async def test_cell_task_runs_scripted_and_succeeds() -> None:
    fake = FakeCells()
    dream = client(fake)
    run_id = await dream.start(skill="dream-1-base", prompt="put the metal block on the machine tray", checkpoint=None)
    assert run_id.startswith("geskriptet-cnc_load-")
    assert fake.session and fake.session["cell"] == "cnc"  # session started on demand
    run = await finish(dream, run_id)
    assert (run.status, run.success) == ("succeeded", True)


@pytest.mark.asyncio
async def test_blocked_task_fails_with_reason() -> None:
    dream = client(FakeCells())
    run = await finish(dream, await dream.start(skill="cnc_unload", prompt="", checkpoint=None))
    assert run.status == "failed"
    assert run.error and "kein Fertigteil" in run.error


@pytest.mark.asyncio
async def test_other_skills_go_to_the_inner_client() -> None:
    dream = client(FakeCells())
    assert await dream.start(skill="pick-banana", prompt="pick up the banana", checkpoint=None) == "run_fruit"


def unreachable(_: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused")


@pytest.mark.asyncio
async def test_learned_checkpoint_is_not_silently_scripted() -> None:
    fake = FakeCells()
    dream = client(fake)
    with pytest.raises(DreamError, match="Checkpoint dream-1-ft:x"):
        await dream.start(skill="cnc_load", prompt="", checkpoint="dream-1-ft:x")
    real = CellDreamClient(
        NoDream(), SimulationApi("http://sim", transport=httpx.MockTransport(fake)), allow_scripted=False
    )
    with pytest.raises(DreamError, match="referenz"):
        await real.start(skill="cnc_load", prompt="", checkpoint=None)
    assert (await real.start(skill="cnc_load", prompt="", checkpoint="referenz")).startswith("geskriptet-")
    assert fake.session is not None and fake.session["busy"] == "cnc_load"


def registry_with(bridge_api: SimulationApi) -> tuple[DeviceRegistry, CellBridge]:
    import pathlib
    import tempfile

    from app.db.database import Database

    db = Database(pathlib.Path(tempfile.mkdtemp()) / "t.sqlite3")
    db.init_schema(pathlib.Path(__file__).resolve().parents[1] / "models" / "schema.sql")
    registry = DeviceRegistry(db)
    registry.load()
    registry.ensure(d for d, _ in CELL_DEVICES.values())
    bridge = CellBridge(bridge_api, registry, poll_s=0.01)
    registry.guards.append(bridge.unavailable)
    registry.apply_hooks.append(bridge.apply)
    return registry, bridge


@pytest.mark.asyncio
async def test_machine_command_failure_reaches_the_workflow() -> None:
    registry, _ = registry_with(SimulationApi("http://sim", transport=httpx.MockTransport(unreachable)))
    with pytest.raises(UpstreamError):
        await registry.apply("zelle-cnc-maschine", True)


@pytest.mark.asyncio
async def test_blocked_cycle_start_raises() -> None:
    fake = FakeCells()
    fake.block_cycle = True
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    registry, _ = registry_with(api)
    with pytest.raises(ConflictError, match="kein Rohteil"):
        await registry.apply("zelle-cnc-maschine", True)


@pytest.mark.asyncio
async def test_stale_sensor_is_unavailable_not_old() -> None:
    fake = FakeCells()
    calls = {"down": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if calls["down"]:
            raise httpx.ConnectError("refused")
        return fake(request)

    api = SimulationApi("http://sim", transport=httpx.MockTransport(handler))
    await api.request("POST", "/cells/cnc/session")
    registry, bridge = registry_with(api)
    with pytest.raises(UpstreamError):  # before the first poll: no value yet
        registry.read("zelle-maschine-fertig")
    fake.session["sensors"]["machine_done"] = True  # type: ignore[index]
    await bridge.poll_once()
    assert registry.read("zelle-maschine-fertig").value is True
    calls["down"] = True
    await bridge.poll_once()
    with pytest.raises(UpstreamError, match="nicht verfügbar"):
        registry.read("zelle-maschine-fertig")
    with pytest.raises(UpstreamError, match="nicht verfügbar"):  # Codex #3: Ampel ohne Zelle gilt nicht
        registry.read("zelle-ampel-rot")


@pytest.mark.asyncio
async def test_workflow_takes_error_path_when_machine_does_not_start() -> None:
    from app.engine.engine import Engine, EngineSettings
    from tests.test_engine import ListSink, wf

    fake = FakeCells()
    fake.block_cycle = True
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    registry, _ = registry_with(api)
    definition = wf(
        [
            ("s", "start", {}),
            ("m", "set_actuator", {"device": "zelle-cnc-maschine", "value": True}),
            ("ok", "end", {}),
            ("rot", "set_actuator", {"device": "zelle-ampel-rot", "value": True}),
            ("err", "end", {}),
        ],
        [("s", "m", "next"), ("m", "ok", "next"), ("m", "rot", "error"), ("rot", "err", "next")],
    )
    sink = ListSink()
    await Engine(
        definition,
        dream=NoDream(),
        devices=registry,
        skills={},
        sink=sink,
        settings=EngineSettings(poll_interval_s=0.01),
    ).run()
    assert sink.blocks[-1] == "err"
    assert fake.actions == ["cycle_start", "light_red"]
    assert any("kein Rohteil" in e["message"] for e in sink.entries)


@pytest.mark.asyncio
async def test_bridge_mirrors_sensors_and_sends_actions() -> None:
    fake = FakeCells()
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    registry, bridge = registry_with(api)
    fake.session["sensors"]["raw_part_on_tray"] = True  # type: ignore[index]
    await registry.apply("zelle-cnc-maschine", True)
    assert fake.actions == ["cycle_start"]
    await bridge.poll_once()
    assert registry.read("zelle-maschine-fertig").value is True
    await registry.apply("zelle-ampel-rot", True)
    await registry.apply("zelle-ampel-rot", False)
    assert fake.actions[1:] == ["light_red", "light_off"]


@pytest.mark.asyncio
async def test_cell_prompts_need_no_skill_in_sim_mode() -> None:
    from app.engine.validation import validate
    from tests.test_engine import wf

    dream = client(FakeCells())
    await dream.prime()
    definition = wf(
        [("s", "start", {}), ("p", "prompt", {"prompt": "Put the metal block on the machine tray"}), ("e", "end", {})],
        [("s", "p", "next"), ("p", "e", "next")],
    )
    ok = validate(definition, devices={}, skill_ids=set(), require_skill=True, skill_free_prompts=dream.cell_prompts)
    assert ok.valid
    other = wf(
        [("s", "start", {}), ("p", "prompt", {"prompt": "pick up the banana"}), ("e", "end", {})],
        [("s", "p", "next"), ("p", "e", "next")],
    )
    assert not validate(
        other, devices={}, skill_ids=set(), require_skill=True, skill_free_prompts=dream.cell_prompts
    ).valid


@pytest.mark.asyncio
async def test_cell_tasks_cost_no_credits_and_error_path_is_reported() -> None:
    from app.engine.engine import Engine, EngineSettings
    from app.engine.validation import validate
    from tests.test_engine import ListSink, wf

    dream = client(FakeCells(polls_per_task=1))
    await dream.prime()
    definition = wf(
        [
            ("s", "start", {}),
            ("u", "prompt", {"prompt": "put the finished part in the green box"}),
            ("ok", "end", {}),
            ("err", "end", {}),
        ],
        [("s", "u", "next"), ("u", "ok", "next"), ("u", "err", "error")],
    )
    assert (
        validate(definition, devices={}, skill_ids=set(), skill_free_prompts=dream.cell_prompts).credits_estimate == 0
    )
    sink = ListSink()
    engine = Engine(
        definition,
        dream=dream,
        devices=VirtualAdapter(),
        skills={},
        sink=sink,
        settings=EngineSettings(poll_interval_s=0.01),
    )
    await engine.run()
    assert sink.blocks[-1] == "err" and engine.handled_errors == 1 and sink.credits == 0


@pytest.mark.asyncio
async def test_repeated_cycle_does_not_reuse_previous_done() -> None:
    fake = FakeCells()
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    registry, bridge = registry_with(api)
    fake.session["sensors"]["raw_part_on_tray"] = True  # type: ignore[index]
    await registry.apply("zelle-cnc-maschine", True)
    await bridge.poll_once()
    assert registry.read("zelle-maschine-fertig").value is True  # first cycle done
    await registry.apply("zelle-cnc-maschine", True)  # second cycle, no poll in between
    assert registry.read("zelle-maschine-fertig").value is False  # the ack refreshed the sensor
    assert registry.read("zelle-cnc-maschine").value is True  # machine_running


@pytest.mark.asyncio
async def test_older_snapshot_does_not_overwrite_newer() -> None:
    fake = FakeCells()
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    registry, bridge = registry_with(api)
    sensors = {"machine_done": False, "machine_running": True}
    bridge._mirror({"status": "running", "sim_seconds": 10.0, "sensors": sensors})
    bridge._mirror({"status": "running", "sim_seconds": 9.5, "sensors": {**sensors, "machine_done": True}})
    assert registry.read("zelle-maschine-fertig").value is False
    bridge._mirror({"status": "running", "sim_seconds": 0.5, "sensors": {**sensors, "machine_done": True}})
    assert registry.read("zelle-maschine-fertig").value is True  # much older = new session, accepted


def test_devices_api_reports_unavailable_cell_sensor(tmp_path: pathlib.Path) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    settings = Settings(dream_api_mode="sim", database_path=tmp_path / "d.sqlite3", simulation_url="http://127.0.0.1:9")
    with TestClient(create_app(settings)) as client:
        devices = {d["id"]: d for d in client.get("/api/devices").json()}
        # Codex: Zellen-Sensoren meldet die Zelle; Handeingabe darf kein „Maschine fertig“ vortäuschen
        assert client.put("/api/devices/zelle-maschine-fertig/value", json={"value": True}).status_code == 409
        assert client.put("/api/devices/lichtschranke/value", json={"value": True}).status_code == 200
    assert devices["zelle-maschine-fertig"]["read_only"] is True and devices["lichtschranke"]["read_only"] is False
    sensor = devices["zelle-maschine-fertig"]
    assert sensor["available"] is False and "nicht verfügbar" in sensor["unavailable_reason"]
    assert devices["zelle-ampel-rot"]["available"] is False  # Codex #3: auch Aktoren der Zelle
    assert devices["lichtschranke"]["available"] is True


@pytest.mark.asyncio
async def test_stop_while_waiting_for_machine_halts_the_cell() -> None:
    """Codex #1: STOP während „Maschine läuft“ beendet die Zellen-Sitzung, statt die Maschine weiterlaufen zu lassen."""
    import asyncio

    from app.engine.engine import Engine, EngineSettings
    from tests.test_engine import ListSink, wf

    fake = FakeCells()
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    fake.session["sensors"]["raw_part_on_tray"] = True  # type: ignore[index]
    registry, _ = registry_with(api)
    definition = wf(
        [
            ("s", "start", {}),
            ("m", "set_actuator", {"device": "zelle-cnc-maschine", "value": True}),
            ("w", "wait_sensor", {"device": "zelle-maschine-fertig", "operator": "==", "value": True}),
            ("e", "end", {}),
        ],
        [("s", "m", "next"), ("m", "w", "next"), ("w", "e", "next")],
    )
    sink = ListSink()
    engine = Engine(
        definition,
        dream=client(fake),
        devices=registry,
        skills={},
        sink=sink,
        settings=EngineSettings(poll_interval_s=0.01, sensor_poll_interval_s=0.01),
    )
    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.2)
    assert sink.blocks[-1] == "w" and fake.session["sensors"]["machine_running"]  # type: ignore[index]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.deletes == 1 and fake.session is None
    assert any("Zelle angehalten" in e["message"] for e in sink.entries)


@pytest.mark.asyncio
async def test_stop_without_cell_use_leaves_the_cell_alone() -> None:
    import asyncio

    from app.engine.engine import Engine
    from tests.test_engine import ListSink, wf

    fake = FakeCells()
    dream = client(fake)
    await dream.api.request("POST", "/cells/cnc/session")
    definition = wf(
        [("s", "start", {}), ("t", "wait_time", {"seconds": 5}), ("e", "end", {})],
        [("s", "t", "next"), ("t", "e", "next")],
    )
    engine = Engine(definition, dream=dream, devices=VirtualAdapter(), skills={}, sink=ListSink())
    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.deletes == 0 and fake.session is not None


@pytest.mark.asyncio
async def test_second_load_gets_a_new_blank() -> None:
    """Codex #4: nach einem Zyklus ist das Rohteil verbraucht; der nächste Ladeauftrag startet die Sitzung neu."""
    fake = FakeCells(polls_per_task=1)
    dream = client(fake)
    first = await finish(dream, await dream.start(skill="cnc_load", prompt="", checkpoint=None))
    assert first.success and first.note is None and fake.deletes == 0
    fake.session["sensors"]["cycles"] = 1  # type: ignore[index]  # Maschine lief, Rohteil verbraucht
    second = await finish(dream, await dream.start(skill="cnc_load", prompt="", checkpoint=None))
    assert second.success and second.note == REFILL_NOTE and fake.deletes == 1


@pytest.mark.asyncio
async def test_session_start_survives_a_slow_simulation() -> None:
    """Live 22.11.: Zellenaufbau unter Last, der Dienst antwortet > 10 s nicht -> weiter warten, nicht Fehlerpfad."""
    fake = FakeCells(polls_per_task=1)
    hiccups = {"left": 3}

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/cells/") and hiccups["left"] > 0 and fake.session is not None:
            hiccups["left"] -= 1
            raise httpx.ReadError("slow", request=request)
        return fake(request)

    dream = CellDreamClient(
        NoDream(), SimulationApi("http://sim", transport=httpx.MockTransport(flaky)), allow_scripted=True, poll_s=0.01
    )
    run = await finish(dream, await dream.start(skill="cnc_load", prompt="", checkpoint=None))
    assert run.success and hiccups["left"] == 0


@pytest.mark.asyncio
async def test_lamps_mirror_the_cell_and_go_unavailable_without_it() -> None:
    """Codex #3: Ampel und Maschine zeigen bei Ausfall „nicht verfügbar“ statt eines alten Zustands."""
    fake = FakeCells()
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    registry, bridge = registry_with(api)
    fake.session["sensors"]["stack_light"] = "green"  # type: ignore[index]
    await bridge.poll_once()
    assert registry.get("zelle-ampel-gruen").value is True and registry.get("zelle-ampel-rot").value is False
    assert bridge.unavailable("zelle-ampel-gruen") is None
    await api.request("DELETE", "/cells/session")
    await bridge.poll_once()
    for device_id in ("zelle-ampel-gruen", "zelle-ampel-rot", "zelle-cnc-maschine"):
        assert "nicht verfügbar" in (bridge.unavailable(device_id) or "")


@pytest.mark.asyncio
async def test_late_answer_with_equal_sim_time_does_not_overwrite() -> None:
    """Codex #2: gleiche Sim-Zeit (Simulation rundet auf 0,1 s), aber früher abgeschickte Abfrage -> verwerfen."""
    fake = FakeCells()
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    registry, bridge = registry_with(api)
    sensors = {"machine_done": False, "machine_running": True}
    old_seq, new_seq = next(bridge._seq), next(bridge._seq)
    bridge._mirror({"status": "running", "sim_seconds": 10.0, "sensors": sensors}, new_seq)
    bridge._mirror({"status": "running", "sim_seconds": 10.0, "sensors": {**sensors, "machine_done": True}}, old_seq)
    assert registry.read("zelle-maschine-fertig").value is False


@pytest.mark.asyncio
async def test_frozen_simulation_goes_stale() -> None:
    """Codex #2: Antworten ohne Fortschritt der Sim-Zeit verlängern die Frische nicht."""
    import time as _time

    fake = FakeCells()
    api = SimulationApi("http://sim", transport=httpx.MockTransport(fake))
    await api.request("POST", "/cells/cnc/session")
    _registry, bridge = registry_with(api)
    frozen = {"status": "running", "sim_seconds": 3.0, "sensors": {"machine_done": False}}
    bridge._mirror(frozen, next(bridge._seq))
    assert bridge._last_ok is not None
    bridge._last_ok -= bridge.max_age_s + 1  # so tun, als sei die letzte echte Bewegung lange her
    bridge._mirror(frozen, next(bridge._seq))  # gleiche Sim-Zeit: keine neue Frische
    assert "nicht verfügbar" in (bridge.unavailable("zelle-maschine-fertig") or "")
    bridge._mirror({**frozen, "sim_seconds": 3.5}, next(bridge._seq))
    assert bridge.unavailable("zelle-maschine-fertig") is None
    assert _time.monotonic() - bridge._last_ok < 1


@pytest.mark.asyncio
async def test_lost_task_response_does_not_run_the_task_twice() -> None:
    """Codex: der Dienst nimmt den Task an, die Antwort geht verloren -> kein zweites Absenden."""
    fake = FakeCells(polls_per_task=3)
    posts = {"n": 0, "lost": 0}

    def lossy(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cells/session/task":
            posts["n"] += 1
            response = fake(request)  # der Dienst nimmt an ...
            if posts["lost"] == 0:
                posts["lost"] = 1
                raise httpx.ReadError("lost", request=request)  # ... aber die Antwort kommt nie an
            return response
        if request.url.path == "/cells/session" and request.method == "GET" and posts["lost"] == 1:
            posts["lost"] = 2
            raise httpx.ReadError("still slow", request=request)  # auch die erste Kontrollabfrage scheitert
        return fake(request)

    dream = CellDreamClient(
        NoDream(), SimulationApi("http://sim", transport=httpx.MockTransport(lossy)), allow_scripted=True, poll_s=0.01
    )
    await dream.api.request("POST", "/cells/cnc/session")
    run = await finish(dream, await dream.start(skill="cnc_load", prompt="", checkpoint=None))
    assert run.success
    assert posts["n"] == 1  # genau einmal abgeschickt


@pytest.mark.asyncio
async def test_lost_response_while_task_is_queued_is_not_resent() -> None:
    """Codex Review 5: der Dienst reiht ein, zeigt den Task aber erst später als „busy“; die Antwort geht verloren."""
    fake = FakeCells(polls_per_task=1)
    fake.queue_polls = 3
    lost = {"done": False}

    def lossy(request: httpx.Request) -> httpx.Response:
        response = fake(request)
        if request.url.path == "/cells/session/task" and not lost["done"]:
            lost["done"] = True
            raise httpx.ReadError("lost", request=request)
        return response

    dream = CellDreamClient(
        NoDream(), SimulationApi("http://sim", transport=httpx.MockTransport(lossy)), allow_scripted=True, poll_s=0.01
    )
    await dream.api.request("POST", "/cells/cnc/session")
    run = await finish(dream, await dream.start(skill="cnc_load", prompt="", checkpoint=None))
    assert run.success and len(fake.task_posts) == 1
    assert fake.task_posts[0]["request_id"]  # Idempotenz-Schlüssel für die Simulation
