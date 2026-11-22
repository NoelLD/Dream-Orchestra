from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import Svc
from app.errors import UpstreamError
from app.schemas.models import StatusOut

root = APIRouter(tags=["System"])
api = APIRouter(tags=["System"])


@root.get("/health", summary="Lebenszeichen (Compose, README)")
@api.get("/health", summary="Lebenszeichen")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend"}


@root.get("/health/database", summary="SQLite erreichbar?")
def health_database(services: Svc) -> JSONResponse:
    ok = services.db.ping()
    return JSONResponse(
        {"status": "ok" if ok else "unavailable", "service": "database"}, status_code=200 if ok else 503
    )


@api.get("/status", response_model=StatusOut, summary="API-Modus für das Banner „SIMULIERTE API“ (N2)")
async def status(services: Svc) -> StatusOut:
    settings = services.settings
    problems: list[str] = []
    reachable: bool | None = None
    if settings.dream_api_mode != "mock":
        try:
            health = await services.simulation.request("GET", "/health")
            reachable = True
            if settings.dream_api_mode == "real" and not health.get("dream_key_set"):
                problems.append("Simulationsdienst hat keinen DREAM_API_KEY; echte Läufe schlagen fehl")
        except UpstreamError as exc:
            reachable = False
            problems.append(exc.detail)
    key_set = settings.dream_api_key is not None and bool(settings.dream_api_key.get_secret_value())
    if settings.dream_api_mode == "real" and not key_set:
        problems.append("DREAM_API_KEY fehlt in .env")
    return StatusOut(
        version=settings.version,
        api_mode=settings.dream_api_mode,
        banner=settings.api_banner,
        dream_api_key_set=key_set,
        simulation_reachable=reachable,
        problems=problems,
    )
