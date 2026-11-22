"""A reachable cell must still provide current, valid sensor readings."""

import asyncio

import httpx
import pytest

from app.devices.adapter import DeviceRegistry
from app.dream.cells import CELL_DEVICES, CellBridge
from app.dream.simulation import SimulationApi
from app.errors import UpstreamError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_snapshot",
    [
        {"status": "error", "sensors": {"machine_done": True}},
        {"status": "starting", "sensors": {"machine_done": True}},
        {"status": "running", "sensors": {}},
        {"status": "running", "sensors": {"machine_done": "false"}},
    ],
)
async def test_invalid_snapshot_cannot_reuse_completed_machine(invalid_snapshot: dict) -> None:
    snapshot = {"status": "running", "sensors": {"machine_done": True}}

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=snapshot)

    api = SimulationApi("http://sim", transport=httpx.MockTransport(respond))
    # No database operations are needed for the device read/bridge contract.
    registry = DeviceRegistry(None)  # type: ignore[arg-type]
    registry._devices = {key: device for key, (device, _) in CELL_DEVICES.items()}
    bridge = CellBridge(api, registry)
    registry.guards.append(bridge.unavailable)
    try:
        await bridge.poll_once()
        assert registry.read("zelle-maschine-fertig").value is True

        snapshot = invalid_snapshot
        await bridge.poll_once()
        with pytest.raises(UpstreamError, match="nicht verfügbar"):
            registry.read("zelle-maschine-fertig")

        snapshot = {"status": "running", "sensors": {"machine_done": False, "stack_light": None}}
        await bridge.poll_once()
        assert registry.read("zelle-maschine-fertig").value is False
        assert bridge.unavailable("zelle-ampel-rot") is None  # Ampel aus, aber gültig
    finally:
        await api.aclose()


@pytest.mark.asyncio
async def test_new_cycle_waits_for_new_completion() -> None:
    from app.engine.engine import Engine, EngineSettings
    from tests.test_cells import NoDream
    from tests.test_engine import ListSink, wf

    snapshot = {
        "status": "running",
        "events": [],
        "sensors": {"machine_done": True, "machine_running": False},
    }

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            snapshot["sensors"].update(machine_done=False, machine_running=True)
            return httpx.Response(202, json={"queued": "action"})
        return httpx.Response(200, json=snapshot)

    api = SimulationApi("http://sim", transport=httpx.MockTransport(respond))
    registry = DeviceRegistry(None)  # type: ignore[arg-type]
    registry._devices = {key: device for key, (device, _) in CELL_DEVICES.items()}
    bridge = CellBridge(api, registry)
    registry.guards.append(bridge.unavailable)
    registry.apply_hooks.append(bridge.apply)
    await bridge.poll_once()  # completion from the previous cycle
    definition = wf(
        [
            ("s", "start", {}),
            ("m", "set_actuator", {"device": "zelle-cnc-maschine", "value": True}),
            ("w", "wait_sensor", {"device": "zelle-maschine-fertig", "value": True, "timeout_s": 1}),
            ("e", "end", {}),
        ],
        [("s", "m", "next"), ("m", "w", "next"), ("w", "e", "next")],
    )
    sink = ListSink()
    engine = Engine(
        definition,
        dream=NoDream(),
        devices=registry,
        skills={},
        sink=sink,
        settings=EngineSettings(sensor_poll_interval_s=0.001),
    )
    task = asyncio.create_task(engine.run())
    try:
        await asyncio.sleep(0.03)
        assert sink.blocks == ["s", "m", "w"]
        assert not task.done()
        snapshot["sensors"].update(machine_done=True, machine_running=False)
        await bridge.poll_once()
        await asyncio.wait_for(task, 1)
        assert sink.blocks[-1] == "e"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await api.aclose()
