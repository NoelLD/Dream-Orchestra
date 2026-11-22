"""Run-Registry: der einzige globale Zustand. Startet Läufe als asyncio-Tasks und schickt ihnen Signale."""

import asyncio
import logging
from dataclasses import dataclass, field

from app.db import repo
from app.db.database import Database
from app.devices.adapter import DeviceAdapter
from app.dream.client import DreamClient
from app.engine.engine import Engine, EngineSettings, RunControl, RunFailed, SkillRef
from app.engine.validation import validate
from app.errors import ConflictError, InvalidError
from app.schemas.workflow import ValidationResult, WorkflowDefinition

logger = logging.getLogger(__name__)


class DbSink:
    def __init__(self, db: Database, run_id: int, state: "ActiveRun") -> None:
        self.db, self.run_id, self.state = db, run_id, state

    def block_entered(self, block_id: str) -> None:
        self.state.active_block_id = block_id

    def log(
        self,
        message: str,
        *,
        level: str = "info",
        block_id: str | None = None,
        api_status: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        repo.add_log(
            self.db,
            self.run_id,
            message,
            level=level,
            block_id=block_id,
            api_status=api_status,
            duration_ms=duration_ms,
        )

    def credits_used(self, amount: int) -> None:
        repo.add_credits(self.db, self.run_id, amount)


@dataclass
class ActiveRun:
    control: RunControl = field(default_factory=RunControl)
    active_block_id: str | None = None
    task: asyncio.Task[None] | None = None


class RunRegistry:
    def __init__(self, db: Database, *, dream: DreamClient, devices: DeviceAdapter, settings: EngineSettings) -> None:
        self.db, self.dream, self.devices, self.settings = db, dream, devices, settings
        self._active: dict[int, ActiveRun] = {}

    def active(self, run_id: int) -> ActiveRun | None:
        return self._active.get(run_id)

    def check(self, definition: WorkflowDefinition) -> ValidationResult:
        """Prüfung vor dem Start (F4) mit den aktuellen Geräten und Skills."""
        return validate(
            definition,
            devices={d.id: d.kind for d in self.devices.list()},
            skill_ids={s["id"] for s in repo.list_skills(self.db)},
            require_skill=self.dream.mode != "mock",
            skill_free_prompts=getattr(self.dream, "cell_prompts", frozenset()),
        )

    def start(self, workflow_id: int | None, definition: WorkflowDefinition | None = None) -> int:
        """Prüft und startet einen gespeicherten Workflow oder eine Momentaufnahme. Gibt die run_id zurück."""
        if self._active:
            raise ConflictError(f"Lauf {next(iter(self._active))} ist noch aktiv; erst stoppen")
        if workflow_id is not None:
            stored = repo.get_workflow(self.db, workflow_id)  # 404, falls unbekannt
            definition = definition or WorkflowDefinition.model_validate(stored["definition"])
        if definition is None:
            raise InvalidError("workflow_id oder definition angeben")
        skills = {
            s["id"]: SkillRef(name=s["name"], checkpoint=s["fine_tuned_model"]) for s in repo.list_skills(self.db)
        }
        result = self.check(definition)
        if not result.valid:
            raise InvalidError("Workflow ist nicht startbereit", details=result.model_dump(mode="json"))

        run_id = repo.create_run(self.db, workflow_id, self.dream.mode, result.credits_estimate)
        state = ActiveRun()
        engine = Engine(
            definition,
            dream=self.dream,
            devices=self.devices,
            skills=skills,
            sink=DbSink(self.db, run_id, state),
            control=state.control,
            settings=self.settings,
        )
        state.task = asyncio.create_task(self._execute(run_id, engine), name=f"run-{run_id}")
        self._active[run_id] = state
        return run_id

    async def stop(self, run_id: int) -> None:
        state = self._require(run_id)
        assert state.task is not None
        state.control.resume()
        state.task.cancel()
        await asyncio.wait({state.task}, timeout=15)

    def pause(self, run_id: int) -> None:
        self._require(run_id).control.pause()
        repo.set_run_status(self.db, run_id, "paused")

    def resume(self, run_id: int) -> None:
        self._require(run_id).control.resume()
        repo.set_run_status(self.db, run_id, "running")

    def step(self, run_id: int) -> None:
        self._require(run_id).control.step()
        repo.set_run_status(self.db, run_id, "paused")

    async def shutdown(self) -> None:
        for run_id in list(self._active):
            await self.stop(run_id)

    def _require(self, run_id: int) -> ActiveRun:
        state = self._active.get(run_id)
        if state is None:
            repo.get_run(self.db, run_id)  # 404, falls es ihn gar nicht gibt
            raise ConflictError(f"Lauf {run_id} ist nicht aktiv")
        return state

    async def _execute(self, run_id: int, engine: Engine) -> None:
        repo.add_log(self.db, run_id, f"Lauf gestartet ({self.dream.mode})")
        status, error = "succeeded", None
        try:
            await engine.run()
        except asyncio.CancelledError:
            status = "stopped"
        except RunFailed as exc:
            status, error = "failed", str(exc)
        except Exception as exc:  # N4
            logger.exception("Lauf %s abgestürzt", run_id)
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            self._active.pop(run_id, None)
            repo.finish_run(self.db, run_id, status, error)
            repo.add_log(
                self.db,
                run_id,
                f"Lauf beendet: {status}" + (f" – {error}" if error else ""),
                level={"succeeded": "info", "stopped": "warning"}.get(status, "error"),
            )
