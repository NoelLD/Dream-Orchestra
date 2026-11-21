"""Engine ohne FastAPI und ohne Datenbank (N3)."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.devices.adapter import VirtualAdapter
from app.dream.fake import FakeDreamClient
from app.engine.engine import Engine, EngineSettings, RunControl, RunFailed, SkillRef
from app.engine.validation import validate
from app.schemas.workflow import WorkflowDefinition

FAST = EngineSettings(poll_interval_s=0.01, sensor_poll_interval_s=0.01, default_block_timeout_s=2, max_steps=50)
SKILLS = {1: SkillRef(name="pick-banana", checkpoint=None)}


@dataclass
class ListSink:
    blocks: list[str] = field(default_factory=list)
    entries: list[dict[str, Any]] = field(default_factory=list)
    credits: int = 0

    def block_entered(self, block_id: str) -> None:
        self.blocks.append(block_id)

    def log(self, message: str, **kwargs: Any) -> None:
        self.entries.append({"message": message, **kwargs})

    def credits_used(self, amount: int) -> None:
        self.credits += amount


def wf(blocks: list[tuple[str, str, dict[str, Any]]], edges: list[tuple[str, str, str]]) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(
        {
            "blocks": [{"id": i, "type": t, "params": p} for i, t, p in blocks],
            "edges": [{"source": s, "target": t, "port": p} for s, t, p in edges],
        }
    )


def make(
    definition: WorkflowDefinition,
    *,
    dream: FakeDreamClient | None = None,
    settings: EngineSettings = FAST,
    devices: VirtualAdapter | None = None,
) -> tuple[Engine, ListSink, FakeDreamClient, VirtualAdapter]:
    sink, dream, devices = ListSink(), dream or FakeDreamClient(duration_s=0.05), devices or VirtualAdapter()
    engine = Engine(definition, dream=dream, devices=devices, skills=SKILLS, sink=sink, settings=settings)
    return engine, sink, dream, devices


def prompt(text: str = "pick up the banana", **extra: Any) -> dict[str, Any]:
    return {"skill_id": 1, "prompt": text, **extra}


LINEAR = wf(
    [
        ("s", "start", {}),
        ("p", "prompt", prompt()),
        ("a", "set_actuator", {"device": "lampe", "value": True}),
        ("w", "wait_time", {"seconds": 0.01}),
        ("e", "end", {}),
    ],
    [("s", "p", "next"), ("p", "a", "next"), ("a", "w", "next"), ("w", "e", "next")],
)


async def test_linear_flow() -> None:
    engine, sink, _, devices = make(LINEAR)
    await engine.run()
    assert sink.blocks == ["s", "p", "a", "w", "e"]
    assert devices.get("lampe").value is True
    assert sink.credits == 1
    assert any(e.get("api_status") == "succeeded" for e in sink.entries)


@pytest.mark.parametrize(("switch", "expected"), [(True, "yes"), (False, "no")])
async def test_condition_both_paths(switch: bool, expected: str) -> None:
    definition = wf(
        [
            ("s", "start", {}),
            ("c", "condition", {"device": "schalter", "value": True}),
            ("yes", "set_actuator", {"device": "lampe", "value": True}),
            ("no", "set_actuator", {"device": "foerderband", "value": True}),
            ("e", "end", {}),
        ],
        [("s", "c", "next"), ("c", "yes", "true"), ("c", "no", "false"), ("yes", "e", "next"), ("no", "e", "next")],
    )
    devices = VirtualAdapter()
    devices.set("schalter", switch)
    engine, sink, _, _ = make(definition, devices=devices)
    await engine.run()
    assert expected in sink.blocks
    assert ("no" if expected == "yes" else "yes") not in sink.blocks


async def test_loop_ends_when_sensor_changes() -> None:
    # Pick-and-Place: solange „schalter“ an ist, nächstes Objekt greifen.
    definition = wf(
        [
            ("s", "start", {}),
            ("p", "prompt", prompt()),
            ("c", "condition", {"device": "schalter", "value": True}),
            ("e", "end", {}),
        ],
        [("s", "p", "next"), ("p", "c", "next"), ("c", "p", "true"), ("c", "e", "false")],
    )
    devices = VirtualAdapter()
    devices.set("schalter", True)
    engine, sink, _, _ = make(definition, devices=devices)
    third_grab = asyncio.Event()
    record = sink.block_entered

    def watch(block_id: str) -> None:
        record(block_id)
        if sink.blocks.count("p") == 3:
            third_grab.set()

    sink.block_entered = watch  # type: ignore[method-assign]
    task = asyncio.create_task(engine.run())
    await asyncio.wait_for(third_grab.wait(), 2)
    devices.set("schalter", False)
    await asyncio.wait_for(task, 2)
    assert sink.blocks[-1] == "e"
    assert sink.blocks.count("p") >= 3


async def test_wait_sensor_then_continue() -> None:
    definition = wf(
        [("s", "start", {}), ("w", "wait_sensor", {"device": "lichtschranke", "value": True}), ("e", "end", {})],
        [("s", "w", "next"), ("w", "e", "next")],
    )
    engine, sink, _, devices = make(definition)
    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.05)
    assert not task.done()
    devices.set("lichtschranke", True)
    await asyncio.wait_for(task, 1)
    assert sink.blocks == ["s", "w", "e"]


async def test_prompt_timeout_takes_error_path_and_stops_dream_run() -> None:
    definition = wf(
        [
            ("s", "start", {}),
            ("p", "prompt", prompt("#hang", timeout_s=0.1)),
            ("err", "set_actuator", {"device": "lampe", "value": True}),
            ("e", "end", {}),
        ],
        [("s", "p", "next"), ("p", "e", "next"), ("p", "err", "error"), ("err", "e", "next")],
    )
    engine, sink, dream, devices = make(definition)
    await engine.run()
    assert sink.blocks == ["s", "p", "err", "e"]
    assert any(e.get("api_status") == "timeout" for e in sink.entries)
    assert dream.stopped  # laufender Dream-Lauf wurde gestoppt
    assert devices.get("lampe").value is True


async def test_failure_with_retries_then_abort_without_error_path() -> None:
    definition = wf(
        [("s", "start", {}), ("p", "prompt", prompt("#fail", retries=2)), ("e", "end", {})],
        [("s", "p", "next"), ("p", "e", "next")],
    )
    engine, sink, _, _ = make(definition)
    with pytest.raises(RunFailed, match="3 Versuch"):
        await engine.run()
    assert sink.credits == 3
    assert [e["api_status"] for e in sink.entries if e.get("api_status")] == ["failed"] * 3


async def test_api_outage_is_logged_not_raised() -> None:
    definition = wf(
        [("s", "start", {}), ("p", "prompt", prompt("#down")), ("err", "end", {}), ("e", "end", {})],
        [("s", "p", "next"), ("p", "e", "next"), ("p", "err", "error")],
    )
    engine, sink, _, _ = make(definition)
    await engine.run()
    assert sink.blocks[-1] == "err"
    assert any("Ausfall" in e["message"] for e in sink.entries)


async def test_stop_mid_run_cancels_dream_run() -> None:
    definition = wf(
        [("s", "start", {}), ("p", "prompt", prompt("#hang")), ("e", "end", {})],
        [("s", "p", "next"), ("p", "e", "next")],
    )
    engine, _, dream, _ = make(definition)
    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert dream.stopped == ["fake_1"]


async def test_infinite_loop_guard() -> None:
    definition = wf(
        [("s", "start", {}), ("w", "wait_time", {"seconds": 0}), ("e", "end", {})],
        [("s", "w", "next"), ("w", "w", "next")],
    )
    engine, _, _, _ = make(definition, settings=EngineSettings(max_steps=20))
    with pytest.raises(RunFailed, match="Schrittlimit"):
        await engine.run()


async def test_pause_and_single_step() -> None:
    control = RunControl()
    sink, devices = ListSink(), VirtualAdapter()
    engine = Engine(
        LINEAR, dream=FakeDreamClient(0.01), devices=devices, skills=SKILLS, sink=sink, control=control, settings=FAST
    )
    control.pause()
    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.05)
    assert sink.blocks == []
    control.step()
    await asyncio.sleep(0.05)
    assert sink.blocks == ["s"]
    control.resume()
    await asyncio.wait_for(task, 2)
    assert sink.blocks[-1] == "e"


def test_validation_rules() -> None:
    devices = {d.id: d.kind for d in VirtualAdapter().list()}
    assert validate(LINEAR, devices=devices, skill_ids={1}).valid

    bad = wf(
        [
            ("s1", "start", {}),
            ("s2", "start", {}),
            ("p", "prompt", prompt("   ")),
            ("loose", "wait_time", {"seconds": 1}),
            ("c", "condition", {"device": "lampe", "value": True}),
            ("e", "end", {}),
        ],
        [("s1", "p", "next"), ("p", "c", "next"), ("c", "e", "true")],
    )
    result = validate(bad, devices=devices, skill_ids={1})
    messages = {(i.block_id, i.message) for i in result.errors}
    assert not result.valid
    assert (None, "Genau ein Start-Block nötig (gefunden: 2)") in messages
    assert ("p", "Leerer Prompt") in messages
    assert ("loose", "Loser Block: vom Start aus nicht erreichbar") in messages
    assert ("c", "Ausgang 'false' ist nicht verbunden") in messages
    assert ("c", "Gerät 'lampe' ist kein sensor") in messages
    assert result.credits_estimate == 1
