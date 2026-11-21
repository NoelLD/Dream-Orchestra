"""Ablauf-Engine: Zustandsmaschine über die Blöcke eines geprüften Workflows (N3).

Ein Lauf ist ein asyncio-Task. Stopp = `task.cancel()` (stoppt auch den laufenden Dream-Lauf, F7),
Pause/Einzelschritt = `RunControl`. Fehler eines Blocks folgen dem Ausgang `error`, sonst Abbruch (F6).
"""

import asyncio
import operator
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.devices.adapter import DeviceAdapter
from app.dream.client import DreamClient, DreamError, DreamRun
from app.errors import AppError
from app.schemas.workflow import (
    PARAMS,
    Block,
    BlockType,
    ConditionParams,
    Operator,
    Port,
    PromptParams,
    SetActuatorParams,
    WaitSensorParams,
    WaitTimeParams,
    WorkflowDefinition,
)


@dataclass(frozen=True)
class EngineSettings:
    poll_interval_s: float = 1.0
    sensor_poll_interval_s: float = 0.2
    default_block_timeout_s: float = 180.0
    max_steps: int = 1000


@dataclass(frozen=True)
class SkillRef:
    name: str
    checkpoint: str | None


class RunSink(Protocol):
    """Empfängt Fortschritt und Protokoll eines Laufs."""

    def block_entered(self, block_id: str) -> None: ...

    def log(
        self,
        message: str,
        *,
        level: str = "info",
        block_id: str | None = None,
        api_status: str | None = None,
        duration_ms: float | None = None,
    ) -> None: ...

    def credits_used(self, amount: int) -> None: ...


class RunFailed(Exception):
    pass


class BlockError(Exception):
    pass


class RunControl:
    """Pause, Fortsetzen, Einzelschritt (F8)."""

    def __init__(self) -> None:
        self._go = asyncio.Event()
        self._go.set()
        self._single_step = False

    @property
    def paused(self) -> bool:
        return not self._go.is_set()

    def pause(self) -> None:
        self._single_step = False
        self._go.clear()

    def resume(self) -> None:
        self._single_step = False
        self._go.set()

    def step(self) -> None:
        self._single_step = True
        self._go.set()

    async def gate(self) -> None:
        await self._go.wait()
        if self._single_step:
            self._go.clear()


_OPS: dict[Operator, Callable[[Any, Any], bool]] = {
    Operator.EQ: operator.eq,
    Operator.NE: operator.ne,
    Operator.GT: operator.gt,
    Operator.GE: operator.ge,
    Operator.LT: operator.lt,
    Operator.LE: operator.le,
}


def fmt(value: bool | float) -> str:
    """Gerätewert fürs Protokoll: an/aus statt True/False."""
    if isinstance(value, bool):
        return "an" if value else "aus"
    return f"{value:g}"


def holds(actual: bool | float, op: Operator, expected: bool | float) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return op in (Operator.EQ, Operator.NE) and _OPS[op](bool(actual), bool(expected))
    return _OPS[op](float(actual), float(expected))


class Engine:
    def __init__(
        self,
        definition: WorkflowDefinition,
        *,
        dream: DreamClient,
        devices: DeviceAdapter,
        skills: Mapping[int, SkillRef],
        sink: RunSink,
        control: RunControl | None = None,
        settings: EngineSettings | None = None,
    ) -> None:
        self.dream = dream
        self.devices = devices
        self.skills = skills
        self.sink = sink
        self.control = control or RunControl()
        self.settings = settings or EngineSettings()
        self.blocks = {block.id: block for block in definition.blocks}
        self.edges = {(edge.source, edge.port): edge.target for edge in definition.edges}
        self._dream_run: str | None = None

    async def run(self) -> None:
        current = next((b for b in self.blocks.values() if b.type == BlockType.START), None)
        if current is None:
            raise RunFailed("Kein Start-Block")
        try:
            for _ in range(self.settings.max_steps):
                await self.control.gate()
                self.sink.block_entered(current.id)
                if current.type == BlockType.END:
                    self.sink.log("Ende erreicht", block_id=current.id)
                    return
                port = await self._execute(current)
                target = self.edges.get((current.id, port))
                if target is None:
                    raise RunFailed(f"Block '{current.id}': Ausgang '{port}' ist nicht verbunden")
                current = self.blocks[target]
            raise RunFailed(f"Schrittlimit von {self.settings.max_steps} Blöcken erreicht (Endlosschleife?)")
        except asyncio.CancelledError:
            await self._stop_dream_run()
            raise

    async def _execute(self, block: Block) -> Port:
        started = time.monotonic()
        try:
            params = PARAMS[block.type].model_validate(block.params)
            return await self._dispatch(block, params)
        except (BlockError, DreamError, AppError, ValidationError) as exc:
            message = exc.detail if isinstance(exc, AppError) else str(exc)
        except Exception as exc:  # N4: kein Fehler beendet mehr als diesen Lauf
            message = f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"
        has_error_path = (block.id, Port.ERROR) in self.edges
        self.sink.log(
            message + (" → Fehlerpfad" if has_error_path else ""),
            level="error",
            block_id=block.id,
            duration_ms=(time.monotonic() - started) * 1000,
        )
        if has_error_path:
            return Port.ERROR
        raise RunFailed(f"Block '{block.id}': {message}")

    async def _dispatch(self, block: Block, params: BaseModel) -> Port:
        if isinstance(params, PromptParams):
            return await self._prompt(block, params)
        if isinstance(params, WaitSensorParams):
            return await self._wait_sensor(block, params)
        if isinstance(params, ConditionParams):
            value = self.devices.get(params.device).value
            result = holds(value, params.operator, params.value)
            self.sink.log(f"{params.device} = {fmt(value)} → {'wahr' if result else 'sonst'}", block_id=block.id)
            return Port.TRUE if result else Port.FALSE
        if isinstance(params, SetActuatorParams):
            self.devices.set(params.device, params.value)
            self.sink.log(f"{params.device} := {fmt(params.value)}", block_id=block.id)
            return Port.NEXT
        if isinstance(params, WaitTimeParams):
            await asyncio.sleep(params.seconds)
            return Port.NEXT
        return Port.NEXT  # Start

    async def _prompt(self, block: Block, params: PromptParams) -> Port:
        skill = self.skills.get(params.skill_id)
        if skill is None:
            raise BlockError(f"Skill {params.skill_id} existiert nicht")
        checkpoint = params.checkpoint or skill.checkpoint
        timeout = params.timeout_s or self.settings.default_block_timeout_s
        attempts = params.retries + 1
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                await self.control.gate()
            started = time.monotonic()
            self.sink.credits_used(1)
            try:
                run = await asyncio.wait_for(self._run_skill(skill.name, params.prompt, checkpoint), timeout)
                status, ok = run.status, run.status == "succeeded"
                detail = f"{run.api_calls} API-Aufrufe" + (f", {run.error}" if run.error else "")
            except TimeoutError:
                await self._stop_dream_run()
                status, ok, detail = "timeout", False, f"Zeitlimit {timeout:g} s überschritten"
            except DreamError as exc:
                status, ok, detail = "error", False, str(exc)
            self.sink.log(
                f"Versuch {attempt}/{attempts}: {skill.name} – {detail}",
                level="info" if ok else "warning",
                block_id=block.id,
                api_status=status,
                duration_ms=(time.monotonic() - started) * 1000,
            )
            if ok:
                return Port.NEXT
        raise BlockError(f"Skill '{skill.name}' nach {attempts} Versuch(en) nicht erfolgreich")

    async def _run_skill(self, skill: str, prompt: str, checkpoint: str | None) -> DreamRun:
        self._dream_run = await self.dream.start(skill=skill, prompt=prompt, checkpoint=checkpoint)
        try:
            while True:
                await asyncio.sleep(self.settings.poll_interval_s)  # N5
                run = await self.dream.status(self._dream_run)
                if run.terminal:
                    self._dream_run = None
                    return run
        except DreamError:
            await self._stop_dream_run()
            raise

    async def _wait_sensor(self, block: Block, params: WaitSensorParams) -> Port:
        timeout = params.timeout_s or self.settings.default_block_timeout_s
        started = time.monotonic()
        while not holds(self.devices.get(params.device).value, params.operator, params.value):
            if time.monotonic() - started >= timeout:
                raise BlockError(
                    f"Zeitlimit {timeout:g} s: {params.device} {params.operator} {fmt(params.value)} nicht erfüllt"
                )
            await asyncio.sleep(self.settings.sensor_poll_interval_s)
        self.sink.log(
            f"{params.device} {params.operator} {fmt(params.value)} erfüllt",
            block_id=block.id,
            duration_ms=(time.monotonic() - started) * 1000,
        )
        return Port.NEXT

    async def _stop_dream_run(self) -> None:
        run_id, self._dream_run = self._dream_run, None
        if run_id is None:
            return
        try:
            await asyncio.shield(self.dream.stop(run_id))
            self.sink.log(f"Dream-Lauf {run_id} gestoppt", level="warning")
        except Exception as exc:
            self.sink.log(f"Dream-Lauf {run_id} ließ sich nicht stoppen: {exc}", level="error")
