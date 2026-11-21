"""Prüfung vor dem Start (F4) und Credit-Schätzung (F15). Rein, ohne Datenbank."""

from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from app.devices.adapter import DeviceKind
from app.schemas.workflow import (
    PARAMS,
    PORTS,
    BlockType,
    ConditionParams,
    Issue,
    PromptParams,
    SetActuatorParams,
    ValidationResult,
    WorkflowDefinition,
)


def validate(
    definition: WorkflowDefinition,
    *,
    devices: Mapping[str, DeviceKind],
    skill_ids: set[int],
    require_skill: bool = False,
) -> ValidationResult:
    errors: list[Issue] = []

    def error(message: str, block_id: str | None = None) -> None:
        errors.append(Issue(message=message, block_id=block_id))

    blocks = {}
    for block in definition.blocks:
        if block.id in blocks:
            error(f"Block-ID '{block.id}' ist doppelt", block.id)
        blocks[block.id] = block

    starts = [b.id for b in definition.blocks if b.type == BlockType.START]
    if len(starts) != 1:
        error(f"Genau ein Start-Block nötig (gefunden: {len(starts)})")
    if not any(b.type == BlockType.END for b in definition.blocks):
        error("Kein Ende-Block")

    outgoing: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for edge in definition.edges:
        if edge.source not in blocks or edge.target not in blocks:
            error(f"Pfeil {edge.source} → {edge.target} verweist auf einen unbekannten Block", edge.source)
            continue
        required, optional = PORTS[blocks[edge.source].type]
        if edge.port not in required | optional:
            error(f"Ausgang '{edge.port}' gibt es bei diesem Blocktyp nicht", edge.source)
            continue
        outgoing[edge.source][edge.port].append(edge.target)

    for block in definition.blocks:
        required, _ = PORTS[block.type]
        for port in required:
            if not outgoing[block.id][port]:
                error(f"Ausgang '{port}' ist nicht verbunden", block.id)
        for port_name, targets in outgoing[block.id].items():
            if len(targets) > 1:
                error(f"Ausgang '{port_name}' hat mehrere Pfeile", block.id)
        _check_params(block.type, block.params, block.id, devices, skill_ids, require_skill, error)

    # Keine losen Blöcke: alles muss vom Start aus erreichbar sein.
    seen, stack = set(starts), list(starts)
    while stack:
        for targets in outgoing[stack.pop()].values():
            for target in targets:
                if target not in seen:
                    seen.add(target)
                    stack.append(target)
    for block_id in sorted(blocks.keys() - seen):
        error("Loser Block: vom Start aus nicht erreichbar", block_id)

    return ValidationResult(valid=not errors, errors=errors, credits_estimate=estimate_credits(definition))


def _check_params(
    block_type: BlockType,
    params: dict[str, Any],
    block_id: str,
    devices: Mapping[str, DeviceKind],
    skill_ids: set[int],
    require_skill: bool,
    error: Callable[[str, str | None], None],
) -> None:
    try:
        parsed = PARAMS[block_type].model_validate(params)
    except ValidationError as exc:
        for item in exc.errors():
            field = ".".join(str(p) for p in item["loc"]) or "params"
            message = "Leerer Prompt" if field == "prompt" else f"{field}: {item['msg']}"
            error(message, block_id)
        return
    if isinstance(parsed, PromptParams):
        if not parsed.prompt.strip():
            error("Leerer Prompt", block_id)
        if parsed.skill_id is None:
            if require_skill:
                error("Kein Skill gewählt (der Simulationsdienst misst den Erfolg je Skill)", block_id)
        elif parsed.skill_id not in skill_ids:
            error(f"Skill {parsed.skill_id} existiert nicht", block_id)
    elif isinstance(parsed, ConditionParams | SetActuatorParams):
        expected = DeviceKind.ACTUATOR if isinstance(parsed, SetActuatorParams) else DeviceKind.SENSOR
        kind = devices.get(parsed.device)
        if kind is None:
            error(f"Gerät '{parsed.device}' existiert nicht", block_id)
        elif kind is not expected:
            error(f"Gerät '{parsed.device}' ist kein {expected.value}", block_id)


def estimate_credits(definition: WorkflowDefinition) -> int:
    total = 0
    for block in definition.blocks:
        if block.type == BlockType.PROMPT:
            retries = block.params.get("retries", 0)
            total += 1 + (retries if isinstance(retries, int) and retries >= 0 else 0)
    return total
