"""SimulationDreamClient gegen einen nachgebauten Simulationsdienst (API v0.2), ohne Netz."""

import json

import httpx
import pytest

from app.dream.client import DreamError
from app.dream.simulation import SimulationApi, SimulationDreamClient
from app.engine.engine import Engine, EngineSettings, SkillRef
from app.schemas.workflow import WorkflowDefinition
from tests.test_engine import ListSink, VirtualAdapter


class FakeSimulation:
    """Ein Lauf zur Zeit; nach Stopp/Ende kurz `finalizing` (409 busy) wie im echten Dienst."""

    def __init__(self, busy_polls: int = 0, polls_until_done: int = 2, outcome: str = "succeeded") -> None:
        self.busy_polls = busy_polls
        self.polls_until_done = polls_until_done
        self.outcome = outcome
        self.requests: list[tuple[str, str, dict | None]] = []
        self.polls = 0
        self.stopped = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        match request.method, request.url.path:
            case "POST", "/runs":
                if self.busy_polls > 0:
                    self.busy_polls -= 1
                    return httpx.Response(409, json={"error": "busy", "detail": "another run is active"})
                if body and body["skill"] == "unknown":
                    return httpx.Response(404, json={"error": "unknown_skill", "detail": "no skill 'unknown'"})
                return httpx.Response(202, json={"run_id": "run_abc", "status": "queued", "mode": body["mode"]})
            case "GET", "/runs/run_abc":
                self.polls += 1
                if self.stopped:
                    status = "stopped"
                elif self.polls >= self.polls_until_done:
                    status = self.outcome
                else:
                    status = "warming" if self.polls == 1 else "running"
                return httpx.Response(
                    200,
                    json={
                        "run_id": "run_abc",
                        "status": status,
                        "success": status == "succeeded",
                        "api_calls": 7,
                        "cost_usd": 0.0098,
                        "error": None,
                    },
                )
            case "POST", "/runs/run_abc/stop":
                if self.stopped:
                    return httpx.Response(409, json={"error": "already_finished", "detail": "ended"})
                self.stopped = True
                return httpx.Response(200, json={"run_id": "run_abc", "status": "stopping"})
        return httpx.Response(404, json={"error": "not_found", "detail": request.url.path})


def client_for(sim: FakeSimulation, sim_mode: str = "mock") -> SimulationDreamClient:
    api = SimulationApi("http://sim", transport=httpx.MockTransport(sim))
    return SimulationDreamClient(api, sim_mode=sim_mode, label="sim", busy_wait_s=1, busy_poll_s=0.01)


async def test_start_sends_contract_fields() -> None:
    sim = FakeSimulation()
    client = client_for(sim, sim_mode="dream")
    run_id = await client.start(skill="pick-banana", prompt="pick up", checkpoint="dream-1-ft:x-y", timeout_s=30)
    assert run_id == "run_abc"
    assert sim.requests[0][2] == {
        "skill": "pick-banana",
        "prompt": "pick up",
        "mode": "dream",
        "checkpoint": "dream-1-ft:x-y",
        "timeout_s": 30,
    }


async def test_start_waits_while_simulation_is_busy() -> None:
    sim = FakeSimulation(busy_polls=3)
    assert await client_for(sim).start(skill="pick-banana", prompt="p", checkpoint=None) == "run_abc"
    assert [r[1] for r in sim.requests].count("/runs") == 4


async def test_start_gives_up_after_busy_wait() -> None:
    with pytest.raises(DreamError, match="another run"):
        await client_for(FakeSimulation(busy_polls=10_000)).start(skill="pick-banana", prompt="p", checkpoint=None)


async def test_unknown_skill_becomes_dream_error() -> None:
    with pytest.raises(DreamError, match="no skill"):
        await client_for(FakeSimulation()).start(skill="unknown", prompt="p", checkpoint=None)


async def test_status_and_double_stop() -> None:
    sim = FakeSimulation(polls_until_done=99)
    client = client_for(sim)
    run = await client.status("run_abc")
    assert (run.status, run.terminal, run.api_calls, run.cost_usd) == ("warming", False, 7, 0.0098)
    await client.stop("run_abc")
    await client.stop("run_abc")  # already_finished wird ignoriert
    assert (await client.status("run_abc")).status == "stopped"


async def test_unreachable_simulation() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    api = SimulationApi("http://sim", transport=httpx.MockTransport(refuse))
    with pytest.raises(DreamError, match="nicht erreichbar"):
        await SimulationDreamClient(api, sim_mode="mock", label="sim").start(skill="s", prompt="p", checkpoint=None)


@pytest.mark.parametrize(("outcome", "expected"), [("succeeded", "e"), ("timeout", "err")])
async def test_engine_with_simulation_client(outcome: str, expected: str) -> None:
    definition = WorkflowDefinition.model_validate(
        {
            "blocks": [
                {"id": "s", "type": "start"},
                {"id": "p", "type": "prompt", "params": {"skill_id": 1, "prompt": "pick up the banana"}},
                {"id": "err", "type": "end"},
                {"id": "e", "type": "end"},
            ],
            "edges": [
                {"source": "s", "target": "p"},
                {"source": "p", "target": "e"},
                {"source": "p", "target": "err", "port": "error"},
            ],
        }
    )
    sink = ListSink()
    engine = Engine(
        definition,
        dream=client_for(FakeSimulation(outcome=outcome)),
        devices=VirtualAdapter(),
        skills={1: SkillRef("pick-banana", None)},
        sink=sink,
        settings=EngineSettings(poll_interval_s=0.01),
    )
    await engine.run()
    assert sink.blocks[-1] == expected
    attempt = next(e for e in sink.entries if e.get("api_status"))
    assert attempt["api_status"] == outcome
    assert "run_abc" in attempt["message"] and "0.0098 $" in attempt["message"]
