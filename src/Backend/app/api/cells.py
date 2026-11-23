"""Durchgriff auf die Zellen-Experimente des Simulationsdienstes (Fließband, CNC) für den Leitstand.

Die Tasks laufen im Simulationsdienst mit dem geskripteten Referenz-Controller, nicht mit Dream-1: keine Credits.
Eine Sitzung zur Zeit; eine neue beendet die vorige (src/Simulation/README.md, "Zellen-Experimente").

Im Mock-Modus (kein Simulationsdienst) liefert das Backend eine In-Memory-Session,
damit der Leitstand-Tab im Frontend trotzdem funktioniert.
"""

import time
from typing import Any, Literal

from fastapi import APIRouter, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import Svc
from app.errors import AppError

router = APIRouter(prefix="/cells", tags=["Zellen"])

CellAction = Literal[
    "door_open", "door_close", "belt_on", "belt_off", "cycle_start",
    "light_red", "light_yellow", "light_green", "light_off", "auto_on", "auto_off", "feed",
]  # fmt: skip  # = CELL_ACTIONS in src/Simulation/app/main.py

MOCK_CELLS: list[dict[str, Any]] = [
    {
        "cell": "conveyor",
        "tasks": [
            {"task": "sort_round", "arm": "right", "prompt": "put the round part from the conveyor in the green box"},
            {"task": "sort_cube", "arm": "left", "prompt": "put the metal cube from the conveyor in the blue box"},
        ],
    },
    {
        "cell": "cnc",
        "tasks": [
            {"task": "cnc_load", "arm": "left", "prompt": "put the metal block on the machine tray"},
            {"task": "cnc_unload", "arm": "right", "prompt": "put the finished part in the green box"},
        ],
    },
]

CNC_SENSORS: dict[str, Any] = {
    "door_open": False, "door_closed": True, "tray_out": True, "tray_in": False,
    "raw_part_on_tray": False, "finished_part_on_tray": False,
    "machine_running": False, "machine_done": False, "stack_light": None, "cycles": 0,
}
CONVEYOR_SENSORS: dict[str, Any] = {
    "belt_on": False, "auto": False, "part_at_light_barrier": False, "parts_on_belt": 3,
    "barrier_right": False, "barrier_left": False, "waiting": False,
}

TASK_DURATION_S = 4.0

_mock_session: dict[str, Any] | None = None
_mock_task_end: float | None = None


def _advance_mock() -> None:
    global _mock_session, _mock_task_end
    if not _mock_session or not _mock_task_end:
        return
    if time.monotonic() >= _mock_task_end:
        task = _mock_session["busy"]
        _mock_session["busy"] = None
        _mock_session["last_result"] = {"task": task, "seed": 1000, "passed": True, "reason": "placed (demo)"}
        _mock_session["events"].append({"t": round(time.monotonic() - _mock_session["_started"], 1), "text": f"Task {task}: passed (demo)", "gate": True})
        _mock_task_end = None


def _session_snapshot() -> dict[str, Any] | None:
    if not _mock_session:
        return None
    _advance_mock()
    out = {k: v for k, v in _mock_session.items() if not k.startswith("_")}
    out["sim_seconds"] = round(time.monotonic() - _mock_session["_started"], 1)
    return out


class ActionBody(BaseModel):
    action: CellAction


class TaskBody(BaseModel):
    task: str = Field(min_length=1, description="Task der laufenden Zelle, z. B. cnc_load")
    seed: int | None = Field(default=None, ge=0, description="Szene; gleiche Seeds = gleiche Szene")


def _is_mock(services: Any) -> bool:
    return services.settings.dream_api_mode == "mock"


@router.get("", summary="Zellen und ihre Tasks mit Prompt")
async def list_cells(services: Svc) -> Any:
    if _is_mock(services):
        return MOCK_CELLS
    return await services.simulation.request("GET", "/cells")


@router.get("/session", summary="Live-Sitzung: Status, Sensoren, letztes Ergebnis, Ereignisse")
async def get_session(services: Svc) -> Any:
    if _is_mock(services):
        snap = _session_snapshot()
        if snap is None:
            raise AppError("no_session", "No active cell session.", status_code=409)
        return snap
    return await services.simulation.request("GET", "/cells/session")


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT, summary="Live-Sitzung beenden")
async def end_session(services: Svc) -> None:
    global _mock_session, _mock_task_end
    if _is_mock(services):
        _mock_session = None
        _mock_task_end = None
        return
    await services.simulation.request("DELETE", "/cells/session")


@router.post("/session/action", summary="Zellen-Aktion: Tür, Band, Zyklus, Ampel")
async def session_action(services: Svc, body: ActionBody) -> Any:
    global _mock_session
    if _is_mock(services):
        if not _mock_session:
            raise AppError("no_session", "No active cell session.", status_code=409)
        s = _mock_session.get("sensors", {})
        a = body.action
        if a in ("door_open", "door_close"):
            s["door_open"] = a == "door_open"
            s["door_closed"] = a == "door_close"
        elif a in ("belt_on", "belt_off"):
            s["belt_on"] = a == "belt_on"
        elif a.startswith("light_"):
            s["stack_light"] = None if a == "light_off" else a[6:]
        _mock_session["events"].append({"t": round(time.monotonic() - _mock_session["_started"], 1), "text": f"Action: {a}"})
        return _session_snapshot()
    return await services.simulation.request("POST", "/cells/session/action", body.model_dump())


@router.post("/session/task", summary="Task mit dem Referenz-Controller ausführen (409 busy, 400 wrong_cell)")
async def session_task(services: Svc, body: TaskBody) -> Any:
    global _mock_task_end
    if _is_mock(services):
        if not _mock_session:
            raise AppError("no_session", "No active cell session.", status_code=409)
        _advance_mock()
        if _mock_session["busy"]:
            raise AppError("busy", f"Cell is busy ({_mock_session['busy']}).", status_code=409)
        cell_tasks = next((c["tasks"] for c in MOCK_CELLS if c["cell"] == _mock_session["cell"]), [])
        if not any(t["task"] == body.task for t in cell_tasks):
            raise AppError("wrong_cell", f"Task \"{body.task}\" does not belong to this cell.", status_code=400)
        _mock_session["busy"] = body.task
        _mock_task_end = time.monotonic() + TASK_DURATION_S
        _mock_session["events"].append({"t": round(time.monotonic() - _mock_session["_started"], 1), "text": f"Task {body.task} started (demo)"})
        return _session_snapshot()
    return await services.simulation.request("POST", "/cells/session/task", body.model_dump(exclude_none=True))


def _mock_frame_svg(cell: str, view: str) -> bytes:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">'
        '<rect width="640" height="360" fill="#1e293b"/>'
        '<text x="320" y="140" font-family="sans-serif" font-size="32" font-weight="bold" text-anchor="middle" fill="#94a3b8">'
        f'{"CNC Cell" if cell == "cnc" else "Conveyor Belt"}</text>'
        '<text x="320" y="185" font-family="sans-serif" font-size="18" text-anchor="middle" fill="#64748b">'
        f'{view} — demo mode (no simulation)</text>'
        '<text x="320" y="230" font-family="sans-serif" font-size="14" text-anchor="middle" fill="#475569">'
        'Start a task to see it complete after 4 seconds</text>'
        '</svg>'
    ).encode()


@router.get(
    "/session/frame.jpg",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
    summary="Live-Bild der Zelle: Übersicht oder Roboterkamera",
)
async def session_frame(services: Svc, view: Literal["overview", "robot"] = Query("overview")) -> Response:
    if _is_mock(services):
        cell = _mock_session["cell"] if _mock_session else "none"
        return Response(_mock_frame_svg(cell, view), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})
    upstream = await services.simulation.send("GET", f"/cells/session/frame.jpg?view={view}")
    return Response(upstream.content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{cell}/session", summary="Live-Sitzung einer Zelle starten (beendet die vorige)")
async def start_session(services: Svc, cell: str) -> Any:
    global _mock_session, _mock_task_end
    if _is_mock(services):
        if not any(c["cell"] == cell for c in MOCK_CELLS):
            raise AppError("unknown_cell", f"Unknown cell \"{cell}\".", status_code=404)
        sensors = dict(CNC_SENSORS) if cell == "cnc" else dict(CONVEYOR_SENSORS)
        _mock_session = {
            "cell": cell, "status": "running", "busy": None, "sim_seconds": 0,
            "sensors": sensors, "events": [], "last_result": None, "_started": time.monotonic(),
        }
        _mock_task_end = None
        return _session_snapshot()
    return await services.simulation.request("POST", f"/cells/{cell}/session")
