"""Durchgriff auf den Simulationsdienst: Skills, Laufdetails, Video und Livebild (F16).

Die Lauf-ID eines Prompt-Versuchs (`run_…`) steht im Ablaufprotokoll.
"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import Svc

router = APIRouter(prefix="/simulation", tags=["Simulation"])


@router.get("/skills", summary="Skills des Simulationsdienstes (Name = Skill-Name im Backend)")
async def list_skills(services: Svc) -> Any:
    return await services.simulation.request("GET", "/skills")


@router.get("/robots", summary="Robotertypen: Embodiment, Skills, aktiver Checkpoint, Fine-Tune-Jobs")
async def list_robots(services: Svc) -> Any:
    return await services.simulation.request("GET", "/robots")


@router.get("/robots/{name}", summary="Ein Robotertyp mit seinen Fine-Tune-Jobs")
async def get_robot(services: Svc, name: str) -> Any:
    return await services.simulation.request("GET", f"/robots/{name}")


@router.get("/budget", summary="Budget-Grenze, bisherige und verbleibende Ausgaben (Schätzung)")
async def get_budget(services: Svc) -> Any:
    return await services.simulation.request("GET", "/budget")


@router.get("/evals", summary="Evaluationen (nur lesen; Start kostet Credits und läuft über die Simulation)")
async def list_evals(services: Svc) -> Any:
    return await services.simulation.request("GET", "/evals")


@router.get("/evals/{eval_id}", summary="Fortschritt und Erfolgsquoten einer Evaluation")
async def get_eval(services: Svc, eval_id: str) -> Any:
    return await services.simulation.request("GET", f"/evals/{eval_id}")


@router.get("/runs/{run_id}", summary="Details eines Simulationslaufs (Erfolgsmessung, Dauer, Kosten)")
async def get_run(services: Svc, run_id: str) -> Any:
    return await services.simulation.request("GET", f"/runs/{run_id}")


@router.get(
    "/runs/{run_id}/video",
    response_class=Response,
    responses={200: {"content": {"video/mp4": {}}}},
    summary="MP4 eines beendeten Simulationslaufs",
)
async def get_video(services: Svc, run_id: str) -> Response:
    upstream = await services.simulation.send("GET", f"/runs/{run_id}/video")
    return Response(upstream.content, media_type="video/mp4")


@router.get(
    "/frame.jpg",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
    summary="Neuestes Kamerabild für eine Live-Kachel",
)
async def get_frame(services: Svc) -> Response:
    upstream = await services.simulation.send("GET", "/frame.jpg")
    return Response(upstream.content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
