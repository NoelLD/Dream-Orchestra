"""Pydantic-Modelle für Skills, Läufe, Geräte und Status."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.devices.adapter import DeviceKind, DeviceType
from app.schemas.workflow import WorkflowDefinition


class SkillStatus(StrEnum):
    DRAFT = "Entwurf"
    TRAINING = "Training"
    READY = "Bereit"
    ERROR = "Fehler"


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="Im Modus sim/real: Skill-Name des Simulationsdienstes")
    description: str = ""
    status: SkillStatus = SkillStatus.DRAFT
    fine_tuned_model: str | None = None


class SkillOut(SkillIn):
    id: int
    created_at: datetime


class RunStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


class RunStart(BaseModel):
    """Gespeicherten Workflow starten oder eine Momentaufnahme aus dem Editor (dann optional mit Zuordnung)."""

    workflow_id: int | None = None
    definition: WorkflowDefinition | None = Field(default=None, description="Momentaufnahme; sonst gespeicherte")

    @model_validator(mode="after")
    def _needs_source(self) -> "RunStart":
        if self.workflow_id is None and self.definition is None:
            raise ValueError("workflow_id oder definition angeben")
        return self


class LogEntry(BaseModel):
    id: int
    timestamp: datetime
    level: str
    block_id: str | None
    api_status: str | None
    duration_ms: float | None
    message: str


class RunOut(BaseModel):
    id: int
    workflow_id: int | None
    status: RunStatus
    api_mode: str
    active_block_id: str | None = Field(description="F5: aktuell ausgeführter Block, nur während des Laufs")
    started_at: datetime
    finished_at: datetime | None
    credits_estimate: int
    credits_used: int
    error: str | None
    log: list[LogEntry] = Field(description="Einträge mit id > after")
    cursor: int = Field(description="Für die nächste Abfrage als ?after= übergeben")


class DeviceOut(BaseModel):
    id: str
    name: str
    type: DeviceType
    kind: DeviceKind
    adapter: str
    value: bool | float
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    protocol: str = Field(description="virtual | mqtt | opcua")
    config: dict[str, Any] = Field(description="Protokoll-Einstellungen ohne Passwort (stattdessen password_set)")
    simulated: bool = Field(default=True, description="Werte werden simuliert (noch keine echte Verbindung)")
    available: bool = Field(default=True, description="False: Wert gilt gerade nicht (z. B. Zelle getrennt)")
    unavailable_reason: str | None = Field(default=None, description="Grund, wenn available False ist")
    read_only: bool = Field(
        default=False, description="Wert meldet eine Quelle (z. B. die Zelle), nicht von Hand setzbar"
    )


class DeviceValue(BaseModel):
    value: bool | float


class StatusOut(BaseModel):
    version: str
    api_mode: str = Field(description="mock | sim | real")
    banner: str = Field(description="„SIMULIERTE API“ oder „ECHTE API“ (N2)")
    dream_api_key_set: bool = Field(description="Nur ob, nie welcher (N1)")
    simulation_reachable: bool | None = Field(description="None im Modus mock")
    problems: list[str]
