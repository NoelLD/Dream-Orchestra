"""Durchgriff auf die Zellen-Experimente des Simulationsdienstes (Fließband, CNC) für den Leitstand.

Die Tasks laufen im Simulationsdienst mit dem geskripteten Referenz-Controller, nicht mit Dream-1: keine Credits.
Eine Sitzung zur Zeit; eine neue beendet die vorige (src/Simulation/README.md, "Zellen-Experimente").
"""

from typing import Any, Literal

from fastapi import APIRouter, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import Svc

router = APIRouter(prefix="/cells", tags=["Zellen"])

CellAction = Literal[
    "door_open", "door_close", "belt_on", "belt_off", "cycle_start",
    "light_red", "light_yellow", "light_green", "light_off", "auto_on", "auto_off", "feed",
]  # fmt: skip  # = CELL_ACTIONS in src/Simulation/app/main.py


class ActionBody(BaseModel):
    action: CellAction


class TaskBody(BaseModel):
    task: str = Field(min_length=1, description="Task der laufenden Zelle, z. B. cnc_load")
    seed: int | None = Field(default=None, ge=0, description="Szene; gleiche Seeds = gleiche Szene")


@router.get("", summary="Zellen und ihre Tasks mit Prompt")
async def list_cells(services: Svc) -> Any:
    return await services.simulation.request("GET", "/cells")


@router.get("/session", summary="Live-Sitzung: Status, Sensoren, letztes Ergebnis, Ereignisse")
async def get_session(services: Svc) -> Any:
    return await services.simulation.request("GET", "/cells/session")


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT, summary="Live-Sitzung beenden")
async def end_session(services: Svc) -> None:
    await services.simulation.request("DELETE", "/cells/session")


@router.post("/session/action", summary="Zellen-Aktion: Tür, Band, Zyklus, Ampel")
async def session_action(services: Svc, body: ActionBody) -> Any:
    return await services.simulation.request("POST", "/cells/session/action", body.model_dump())


@router.post("/session/task", summary="Task mit dem Referenz-Controller ausführen (409 busy, 400 wrong_cell)")
async def session_task(services: Svc, body: TaskBody) -> Any:
    return await services.simulation.request("POST", "/cells/session/task", body.model_dump(exclude_none=True))


@router.get(
    "/session/frame.jpg",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
    summary="Live-Bild der Zelle: Übersicht oder Roboterkamera",
)
async def session_frame(services: Svc, view: Literal["overview", "robot"] = Query("overview")) -> Response:
    upstream = await services.simulation.send("GET", f"/cells/session/frame.jpg?view={view}")
    return Response(upstream.content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/{cell}/session", summary="Live-Sitzung einer Zelle starten (beendet die vorige)")
async def start_session(services: Svc, cell: str) -> Any:
    return await services.simulation.request("POST", f"/cells/{cell}/session")
