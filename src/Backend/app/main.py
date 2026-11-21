"""FastAPI-App. Swagger: /docs, OpenAPI-Schema (Vertrag fürs Frontend): /openapi.json"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import devices, health, runs, skills, training, workflows
from app.api.deps import Services
from app.config import Settings, get_settings
from app.db import repo
from app.db.database import Database
from app.devices.adapter import VirtualAdapter
from app.dream.client import DreamClient
from app.dream.fake import FakeDreamClient
from app.dream.simulation import SimulationApi, SimulationDreamClient
from app.engine.engine import EngineSettings
from app.errors import AppError
from app.runs import RunRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_services(settings: Settings) -> Services:
    simulation = SimulationApi(settings.simulation_url, settings.simulation_timeout_s)
    dream: DreamClient
    if settings.dream_api_mode == "mock":
        dream = FakeDreamClient(settings.fake_run_duration_s)
    else:
        sim_mode = "dream" if settings.dream_api_mode == "real" else "mock"
        dream = SimulationDreamClient(simulation, sim_mode=sim_mode, label=settings.dream_api_mode)
    db = Database(settings.database_path)
    devices = VirtualAdapter()
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
    return Services(settings=settings, db=db, dream=dream, devices=devices, simulation=simulation, runs=registry)


def create_app(settings: Settings | None = None, factory: Callable[[Settings], Services] = build_services) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services = factory(settings)
        services.db.init_schema(settings.schema_path)
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

    app.include_router(health.root)
    api = APIRouter(prefix="/api")
    api.include_router(health.api)
    for module in (skills, workflows, runs, devices, training):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
