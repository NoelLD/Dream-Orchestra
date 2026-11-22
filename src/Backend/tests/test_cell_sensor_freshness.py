"""A reachable cell must still provide current, valid sensor readings."""

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

        snapshot = {"status": "running", "sensors": {"machine_done": False}}
        await bridge.poll_once()
        assert registry.read("zelle-maschine-fertig").value is False
        assert bridge.unavailable("zelle-ampel-rot") is None
    finally:
        await api.aclose()
