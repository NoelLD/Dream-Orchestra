from fastapi import APIRouter, Query, status

from app.api.deps import Svc
from app.db import repo
from app.schemas.models import LogEntry, RunOut, RunStart, RunStarted, RunStatus

router = APIRouter(prefix="/runs", tags=["Läufe"])


def _run_out(services: Svc, run_id: int, after: int) -> RunOut:
    run = repo.get_run(services.db, run_id)
    log = [LogEntry.model_validate(entry) for entry in repo.get_log(services.db, run_id, after)]
    active = services.runs.active(run_id)
    return RunOut(
        **run,
        active_block_id=active.active_block_id if active else None,
        log=log,
        cursor=log[-1].id if log else after,
    )


@router.post("", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED, summary="Ablauf starten (F5, F15)")
async def start_run(services: Svc, data: RunStart) -> RunStarted:
    run_id, estimate = services.runs.start(data.workflow_id)
    return RunStarted(run_id=run_id, status=RunStatus.RUNNING, api_mode=services.dream.mode, credits_estimate=estimate)


@router.get("", response_model=list[RunOut], summary="Letzte Läufe (ohne Protokoll)")
def list_runs(services: Svc, limit: int = Query(50, ge=1, le=500)) -> list[RunOut]:
    return [RunOut(**r, active_block_id=None, log=[], cursor=0) for r in repo.list_runs(services.db, limit)]


@router.get("/{run_id}", response_model=RunOut, summary="Status, aktiver Block, neue Protokolleinträge (F5, F14)")
def get_run(
    services: Svc, run_id: int, after: int = Query(0, ge=0, description="Cursor der letzten Abfrage")
) -> RunOut:
    return _run_out(services, run_id, after)


@router.post("/{run_id}/stop", response_model=RunOut, summary="Stopp (F7), auch des laufenden Dream-Laufs")
async def stop_run(services: Svc, run_id: int) -> RunOut:
    await services.runs.stop(run_id)
    return _run_out(services, run_id, 0)


@router.post("/{run_id}/pause", response_model=RunOut, summary="Pause vor dem nächsten Block (F8)")
def pause_run(services: Svc, run_id: int) -> RunOut:
    services.runs.pause(run_id)
    return _run_out(services, run_id, 0)


@router.post("/{run_id}/resume", response_model=RunOut, summary="Fortsetzen (F8)")
def resume_run(services: Svc, run_id: int) -> RunOut:
    services.runs.resume(run_id)
    return _run_out(services, run_id, 0)


@router.post("/{run_id}/step", response_model=RunOut, summary="Einzelschritt: genau einen Block ausführen (F8)")
def step_run(services: Svc, run_id: int) -> RunOut:
    services.runs.step(run_id)
    return _run_out(services, run_id, 0)
