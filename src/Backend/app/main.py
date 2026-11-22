"""FastAPI-App. Swagger: /docs, OpenAPI-Schema (Vertrag fürs Frontend): /openapi.json"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import cells, devices, health, results, runs, simulation, skills, training, workflows
from app.api.deps import Services
from app.config import Settings, get_settings
from app.db import repo
from app.db.database import Database
from app.devices.adapter import DeviceRegistry
from app.dream.client import DreamClient
from app.dream.fake import FakeDreamClient
from app.dream.simulation import SimulationApi, SimulationDreamClient
from app.engine.engine import EngineSettings
from app.errors import AppError
from app.runs import RunRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_services(settings: Settings) -> Services:
    sim_api = SimulationApi(settings.simulation_url, settings.simulation_timeout_s)
    dream: DreamClient
    if settings.dream_api_mode == "mock":
        dream = FakeDreamClient(settings.fake_run_duration_s)
    else:
        sim_mode = "dream" if settings.dream_api_mode == "real" else "mock"
        dream = SimulationDreamClient(sim_api, sim_mode=sim_mode, label=settings.dream_api_mode)
    db = Database(settings.database_path)
    devices = DeviceRegistry(db)
    registry = RunRegistry(
        db,
        dream=dream,
        devices=devices,
        settings=EngineSettings(
            poll_interval_s=settings.poll_interval_s,
            sensor_poll_interval_s=settings.sensor_poll_interval_s,
            default_block_timeout_s=settings.default_block_timeout_s,
            max_steps=settings.max_steps_per_run,
        ),
    )
    return Services(settings=settings, db=db, dream=dream, devices=devices, simulation=sim_api, runs=registry)


def create_app(settings: Settings | None = None, factory: Callable[[Settings], Services] = build_services) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services = factory(settings)
        services.db.init_schema(settings.schema_path)
        services.devices.load()
        repo.fail_open_runs(services.db)
        app.state.services = services
        logger.info("Dream-Modus: %s (%s)", settings.dream_api_mode, settings.api_banner)
        try:
            yield
        finally:
            await services.runs.shutdown()
            await services.dream.aclose()
            await services.simulation.aclose()

    app = FastAPI(
        title="DreamOrchestra Backend",
        version=settings.version,
        description="Skills, Workflows, Läufe und virtuelle Geräte. Modus und Banner: `GET /api/status`.",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        body: dict[str, object] = {"error": exc.code, "detail": exc.detail}
        if exc.details is not None:
            body["details"] = exc.details
        return JSONResponse(body, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def request_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        """Gleiches Fehlerformat wie AppError, damit das Frontend nur eine Form lesen muss."""
        errors = jsonable_encoder(exc.errors())
        first = errors[0] if errors else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        detail = f"{where}: {first.get('msg', 'ungültig')}" if where else str(first.get("msg", "ungültig"))
        return JSONResponse({"error": "invalid_request", "detail": detail, "details": errors}, status_code=422)

    app.include_router(health.root)
    api = APIRouter(prefix="/api")
    api.include_router(health.api)
    for module in (skills, workflows, runs, devices, training, simulation, cells, results):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
