"""Zellen im Workflow: Prompt-Blöcke mit Zellen-Tasks und Zellen-Geräte gegen einen nachgebauten Dienst, ohne Netz."""

import json

import httpx
import pytest

from app.devices.adapter import DeviceRegistry
from app.dream.cells import CELL_DEVICES, CellBridge, CellDreamClient, cell_task_for
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
                        self.session["sensors"].update(machine_running=True, machine_done=True)
                        self.finished_part = True
                return httpx.Response(202, json={"queued": body["action"]})
            case "DELETE", "/cells/session":
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
    assert registry.read("zelle-ampel-rot").value is False  # actuators have no freshness


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
