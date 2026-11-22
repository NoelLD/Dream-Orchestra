"""Workflow-JSON (F1–F4): Blöcke und Pfeile, so wie der Editor sie speichert und lädt."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BlockType(StrEnum):
    START = "start"
    PROMPT = "prompt"  # Dream-1-Prompt
    WAIT_SENSOR = "wait_sensor"  # Warte auf Sensor
    SET_ACTUATOR = "set_actuator"  # Aktor setzen
    WAIT_TIME = "wait_time"  # Warte (Zeit)
    CONDITION = "condition"  # Bedingung
    END = "end"


class Port(StrEnum):
    NEXT = "next"
    TRUE = "true"  # „wahr“
    FALSE = "false"  # „sonst“
    ERROR = "error"  # Fehlerpfad


class Operator(StrEnum):
    EQ = "=="
    NE = "!="
    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="


class Block(BaseModel):
    id: str = Field(min_length=1)
    type: BlockType
    params: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] | None = Field(default=None, description="Nur für den Editor, z. B. {x, y}")


class Edge(BaseModel):
    id: str | None = Field(default=None, description="Nur für den Editor")
    source: str
    target: str
    port: Port = Port.NEXT


class WorkflowDefinition(BaseModel):
    blocks: list[Block] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "blocks": [
                    {"id": "start", "type": "start"},
                    {"id": "grab", "type": "prompt", "params": {"skill_id": 1, "prompt": "pick up the banana"}},
                    {"id": "wait", "type": "wait_sensor", "params": {"device": "lichtschranke", "value": True}},
                    {"id": "more", "type": "condition", "params": {"device": "schalter", "value": True}},
                    {"id": "end", "type": "end"},
                ],
                "edges": [
                    {"source": "start", "target": "grab"},
                    {"source": "grab", "target": "wait"},
                    {"source": "wait", "target": "more"},
                    {"source": "more", "target": "grab", "port": "true"},
                    {"source": "more", "target": "end", "port": "false"},
                ],
            }
        }
    )


# --- Parameter je Blocktyp ---------------------------------------------------


class PromptParams(BaseModel):
    skill_id: int | None = Field(default=None, description="None = Dream-1-Basismodell (nur im Modus mock)")
    prompt: str = Field(min_length=1)
    checkpoint: str | None = Field(default=None, description="Sonst fine_tuned_model des Skills bzw. Basismodell")
    timeout_s: float | None = Field(default=None, gt=0, description="Harte Wanduhr-Grenze pro Versuch (F6)")
    sim_timeout_s: float | None = Field(
        default=None,
        ge=5,
        le=600,
        description="Zeitlimit des Simulationsdienstes in simulierten Sekunden (Standard 60)",
    )
    retries: int = Field(default=0, ge=0, le=10, description="Wiederholungen bei Fehlschlag (F9)")


class ConditionParams(BaseModel):
    device: str
    operator: Operator = Operator.EQ
    value: bool | float


class WaitSensorParams(ConditionParams):
    timeout_s: float | None = Field(default=None, gt=0, description="Eigenes Zeitlimit (F12); None = ohne Zeitlimit")


class SetActuatorParams(BaseModel):
    device: str
    value: bool | float


class WaitTimeParams(BaseModel):
    seconds: float = Field(ge=0)


class NoParams(BaseModel):
    model_config = ConfigDict(extra="allow")


PARAMS: dict[BlockType, type[BaseModel]] = {
    BlockType.START: NoParams,
    BlockType.END: NoParams,
    BlockType.PROMPT: PromptParams,
    BlockType.WAIT_SENSOR: WaitSensorParams,
    BlockType.SET_ACTUATOR: SetActuatorParams,
    BlockType.WAIT_TIME: WaitTimeParams,
    BlockType.CONDITION: ConditionParams,
}

# Ausgänge je Blocktyp: (Pflicht, optional)
PORTS: dict[BlockType, tuple[set[Port], set[Port]]] = {
    BlockType.START: ({Port.NEXT}, set()),
    BlockType.END: (set(), set()),
    BlockType.PROMPT: ({Port.NEXT}, {Port.ERROR}),
    BlockType.WAIT_SENSOR: ({Port.NEXT}, {Port.ERROR}),
    BlockType.SET_ACTUATOR: ({Port.NEXT}, {Port.ERROR}),
    BlockType.WAIT_TIME: ({Port.NEXT}, set()),
    BlockType.CONDITION: ({Port.TRUE, Port.FALSE}, set()),
}


# --- API ---------------------------------------------------------------------


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    definition: WorkflowDefinition = Field(default_factory=WorkflowDefinition)


class WorkflowSummary(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime


class WorkflowOut(WorkflowSummary):
    definition: WorkflowDefinition


class Issue(BaseModel):
    message: str
    block_id: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    errors: list[Issue] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    credits_estimate: int = Field(description="F15: Σ Prompt-Blöcke × (1 + Wiederholungen), Schleifen einmal gezählt")
