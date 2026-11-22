"""FastAPI app of the simulation service (port 3001). API contract: src/Simulation/README.md and GET /docs."""

import logging
import random
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from . import config
from .evals import EvalManager

log = logging.getLogger("simulation.api")
from .robots import DEFAULT_ROBOT, ROBOTS, active_checkpoint
from .runner import AlreadyFinishedError, BusyError, RunManager, RunSpec
from .skills import SKILLS
from .training import ConflictError, NotFoundError, TrainingState, modal_available

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Dream Orchestra – Simulation",
    version="0.3.0",
    description="Runs skills on two YAM arms in MuJoCo (mock = scripted, dream = Dream-1) with retries and a "
    "budget, evaluates prompt/checkpoint/retry variants, builds demo datasets and starts Dream Labs fine-tunes. "
    "Success is measured by the simulator.",
)
# The frontend (nginx, :8080) may call this API straight from the browser, e.g. for /frame.jpg.
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])
runs = RunManager()
evals = EvalManager(runs)
DEMO_PAGE = Path(__file__).resolve().parent / "static/demo.html"
training = TrainingState()


class ApiError(Exception):
    def __init__(self, status: int, error: str, detail: str, **extra):
        self.status, self.error, self.detail, self.extra = status, error, detail, extra


@app.exception_handler(ApiError)
async def api_error(_: Request, exc: ApiError):
    return JSONResponse({"error": exc.error, "detail": exc.detail, **exc.extra}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return JSONResponse({"error": "invalid_request", "detail": f"{where}: {first.get('msg', 'invalid')}"},
                        status_code=400)


# ---- models ---------------------------------------------------------------------------------------------------
class RunRequest(BaseModel):
    skill: str
    prompt: str | None = None
    checkpoint: str = config.DEFAULT_CHECKPOINT
    mode: Literal["dream", "mock"] = "dream"
    timeout_s: float | None = Field(None, ge=5, le=600)  # simulated seconds; None: 60
    seed: int | None = None
    record_video: bool = True
    max_attempts: int = Field(1, ge=1, le=5)  # >1: re-prompt after a failed attempt (F9)
    recovery: Literal["rehome", "continue"] = "rehome"  # before a new attempt: arms home, or carry on
    recovery_prompts: list[str] = Field(default_factory=list, max_length=4)  # prompts for attempts 2, 3, ...

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("prompt must not be empty")
        return value

    @field_validator("recovery_prompts")
    @classmethod
    def recovery_prompts_not_blank(cls, value):
        if any(not p.strip() for p in value):
            raise ValueError("recovery prompts must not be empty")
        return value


class EvalVariant(BaseModel):
    label: str = Field(pattern=r"^[A-Za-z0-9 _.+-]{1,40}$")
    prompt: str | None = None
    checkpoint: str | None = None
    max_attempts: int = Field(1, ge=1, le=5)
    recovery: Literal["rehome", "continue"] = "rehome"
    recovery_prompts: list[str] = Field(default_factory=list, max_length=4)


class EvalRequest(BaseModel):
    skill: str
    variants: list[EvalVariant] = Field(min_length=1, max_length=6)
    trials: int = Field(10, ge=1, le=100)
    seed_start: int = Field(0, ge=0, le=999)  # evaluation seeds stay below 1000 (training data uses >= 1000)
    timeout_s: float = Field(30, ge=5, le=600)
    mode: Literal["dream", "mock"] = "dream"


class DatasetRequest(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    episodes: int = Field(10, ge=1, le=500)
    randomize: bool = True
    seed: int = 0
    backend: Literal["local", "modal"] = "local"


class FinetuneRequest(BaseModel):
    dataset: str
    suffix: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    steps: int = Field(500, ge=500, le=10000, multiple_of=100)
    lr_schedule: Literal["constant", "cosine"] = "cosine"
    confirm_cost_usd: float = Field(gt=0, allow_inf_nan=False)
    robot: str = DEFAULT_ROBOT  # fine-tunes belong to a robot type (GET /robots)
    base_share: Literal[0.0, 0.5] | None = None  # share of Dream Labs' own data per batch; Dream default 0.5
    learning_rate: float | None = Field(None, ge=1e-6, le=1e-4)  # Dream default 1e-5
    resume_from: str | None = Field(None, pattern=r"^dream-1-ft:[A-Za-z0-9-]+$")  # continue a finished model


# ---- health & skills ------------------------------------------------------------------------------------------
@app.get("/health")
def health():
    active = runs.active.public() if runs.active and runs.active.status not in ("succeeded", "failed", "timeout",
                                                                                 "stopped", "error") else None
    return {"status": "ok", "service": "simulation", "dream_key_set": config.dream_key_set(),
            "modes": ["mock", "dream"] if config.dream_key_set() else ["mock"],
            "active_run_id": active["run_id"] if active else None, "version": app.version}


@app.get("/demo", include_in_schema=False)
def demo():
    """Test console of the simulation service (not the product frontend)."""
    return FileResponse(DEMO_PAGE, media_type="text/html")


@app.get("/skills")
def list_skills():
    return [s.public(active_checkpoint(s.robot, training.jobs)) for s in SKILLS.values()]


def robot_public(robot) -> dict:
    jobs = [j for j in training.jobs.values() if j.get("robot", DEFAULT_ROBOT) == robot.name]
    return {"name": robot.name, "description": robot.description, "embodiment": robot.embodiment,
            "cameras": list(robot.cameras), "skills": [s.name for s in SKILLS.values() if s.robot == robot.name],
            "fine_tuned_model": active_checkpoint(robot.name, training.jobs),
            "cell_fine_tuned_model": active_checkpoint(robot.name, training.jobs, cells=True),
            "finetune_jobs": [{k: j.get(k) for k in ("job_id", "status", "dataset", "suffix", "steps", "price_usd",
                                                     "fine_tuned_model", "created_at")} for j in jobs]}


@app.get("/robots")
def list_robots():
    """Robot types; a fine-tune is started per robot type and its checkpoint serves all of the robot's skills."""
    return [robot_public(r) for r in ROBOTS.values()]


@app.get("/robots/{name}")
def get_robot(name: str):
    robot = ROBOTS.get(name)
    if robot is None:
        raise ApiError(404, "unknown_robot", f"no robot {name!r}; see GET /robots")
    return robot_public(robot)


# ---- runs -----------------------------------------------------------------------------------------------------
@app.post("/runs", status_code=202)
def start_run(req: RunRequest):
    skill = SKILLS.get(req.skill)
    if skill is None:
        raise ApiError(404, "unknown_skill", f"no skill {req.skill!r}; see GET /skills")
    if req.mode == "mock" and not skill.mock_available:
        raise ApiError(400, "mock_unavailable", f"skill {req.skill} has no scripted (mock) version")
    if req.mode == "dream" and not config.dream_key_set():
        raise ApiError(503, "no_api_key", "DREAM_API_KEY is not set in the simulation container")
    if req.mode == "dream" and not (req.checkpoint in config.BASE_CHECKPOINTS
                                    or req.checkpoint.startswith("dream-1-ft:")):
        raise ApiError(400, "invalid_checkpoint", f"unknown checkpoint {req.checkpoint!r}")
    if req.mode == "dream" and runs.budget()["remaining_usd"] <= 0:
        raise ApiError(402, "budget_exhausted", f"service budget of {config.BUDGET_USD} USD is used up")
    seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)
    timeout_s = req.timeout_s or (config.DEFAULT_TIMEOUT_S if req.mode == "dream" else config.DEFAULT_MOCK_TIMEOUT_S)
    spec = RunSpec(skill=skill, mode=req.mode, prompt=req.prompt or skill.default_prompt, checkpoint=req.checkpoint,
                   timeout_s=timeout_s, seed=seed, record_video=req.record_video, max_attempts=req.max_attempts,
                   recovery=req.recovery, recovery_prompts=req.recovery_prompts)
    try:
        run = runs.start(spec)
    except BusyError as busy:
        raise ApiError(409, "busy", "another run is active", active_run_id=busy.active_run_id)
    return {"run_id": run.run_id, "status": run.status, "mode": req.mode}


@app.get("/runs")
def list_runs(limit: int = 50):
    return runs.list(limit)


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run = runs.get(run_id)
    if run is None:
        raise ApiError(404, "unknown_run", f"no run {run_id}")
    return run


@app.post("/runs/{run_id}/stop")
def stop_run(run_id: str):
    try:
        run = runs.stop(run_id)
    except KeyError:
        raise ApiError(404, "unknown_run", f"no run {run_id}")
    except AlreadyFinishedError:
        raise ApiError(409, "already_finished", f"run {run_id} has already ended")
    return run.public() | {"status": "stopping" if run.status not in ("stopped",) else run.status}


@app.get("/runs/{run_id}/video")
def run_video(run_id: str):
    path = runs.video_path(run_id)
    if path is None:
        raise ApiError(404, "no_video", f"no video for {run_id} (unknown, still running, or not recorded)")
    return FileResponse(path, media_type="video/mp4", filename=f"{run_id}.mp4")


@app.get("/frame.jpg")
async def frame():
    jpeg = await run_in_threadpool(runs.preview_jpeg)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# ---- datasets & fine-tuning -----------------------------------------------------------------------------------
@app.get("/datasets")
def list_datasets():
    return training.list_datasets()


@app.post("/datasets", status_code=202)
def create_dataset(req: DatasetRequest):
    if req.backend == "modal":
        if not modal_available():
            raise ApiError(501, "modal_unavailable",
                           "Modal runs from a host with the modal CLI: modal run src/Simulation/tools/modal_gen.py "
                           f"--name {req.name} --count {req.episodes}")
    try:
        return training.generate(req.name, req.episodes, req.randomize, req.seed)
    except ConflictError as error:
        raise ApiError(409, "busy", str(error))


@app.get("/datasets/{name}")
def get_dataset(name: str):
    record = training.dataset(name)
    if record is None:
        raise ApiError(404, "unknown_dataset", f"no dataset {name}")
    return record


@app.post("/datasets/{name}/upload", status_code=202)
def upload_dataset(name: str):
    if not config.dream_key_set():
        raise ApiError(503, "no_api_key", "DREAM_API_KEY is not set in the simulation container")
    try:
        return training.upload(name)
    except NotFoundError as error:
        raise ApiError(404, "unknown_dataset", str(error))
    except ConflictError as error:
        raise ApiError(409, "busy", str(error))


@app.post("/finetune", status_code=202)
def start_finetune(req: FinetuneRequest):
    if not config.dream_key_set():
        raise ApiError(503, "no_api_key", "DREAM_API_KEY is not set in the simulation container")
    if req.robot not in ROBOTS:
        raise ApiError(404, "unknown_robot", f"no robot {req.robot!r}; see GET /robots")
    if req.resume_from and req.lr_schedule != "constant":
        raise ApiError(400, "invalid_request", "resume_from needs lr_schedule 'constant' (Dream Labs rule)")
    try:
        job = training.finetune(req.dataset, req.suffix, req.steps, req.lr_schedule, req.confirm_cost_usd,
                                robot=req.robot, base_share=req.base_share, learning_rate=req.learning_rate,
                                resume_from=req.resume_from)
    except ValueError as error:
        raise ApiError(400, "cost_not_confirmed", str(error))
    except ConflictError as error:
        raise ApiError(409, "dataset_not_ready", str(error))
    except Exception as error:  # Dream service refusals (payment_required, conflict, ...)
        raise ApiError(502, getattr(error, "code", None) or "dream_error", str(error)[:300])
    return {"job_id": job["id"], "robot": req.robot, "status": job["status"],
            "price_usd": round(req.steps * 0.2, 2)}


@app.get("/finetune")
def list_finetunes(refresh: bool = True):
    """Our jobs. refresh=true asks Dream for every job not yet terminal (free calls) and stores the answer."""
    if refresh and config.dream_key_set():
        from dream import fine_tuning

        for job_id, record in list(training.jobs.items()):
            if record.get("status") in ("failed", "cancelled") or record.get("fine_tuned_model"):
                continue  # final: refused, or the published model is known
            try:
                training.record_job_status(fine_tuning.get(job_id))
            except Exception as error:  # keep the stored record; report nothing new for this job
                log.warning("finetune refresh %s: %s", job_id, error)
    return list(training.jobs.values())


@app.get("/finetune/{job_id}")
def get_finetune(job_id: str):
    from dream import fine_tuning

    try:
        job = fine_tuning.get(job_id)
    except Exception as error:
        code = getattr(error, "code", None)
        raise ApiError(404 if code == "not_found" else 502, code or "dream_error", str(error)[:300])
    training.record_job_status(job)
    robot = training.jobs.get(job["id"], {}).get("robot")
    return {"job_id": job["id"], "robot": robot, "status": job["status"], "progress": job.get("progress"),
            "base_model": job.get("base_model"), "hyperparameters": job.get("hyperparameters"),
            "fine_tuned_model": job.get("fine_tuned_model"), "error": job.get("error"),
            "created_at": job.get("created_at"), "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at")}


# ---- live cell session (control room) -----------------------------------------------------------------------
from .cell_session import CellSession  # noqa: E402
from .cnc import CELLS  # noqa: E402
from .cnc_expert import TASKS as CELL_TASKS  # noqa: E402

cell_box: list[CellSession | None] = [None]
CELL_ACTIONS = ("door_open", "door_close", "belt_on", "belt_off", "cycle_start", "light_red", "light_yellow",
                "light_green", "light_off", "auto_on", "auto_off", "feed")


class CellAction(BaseModel):
    action: Literal[CELL_ACTIONS]  # type: ignore[valid-type]


class CellTask(BaseModel):
    task: Literal[tuple(CELL_TASKS)]  # type: ignore[valid-type]
    seed: int = Field(1000, ge=0)
    mode: Literal["mock"] = "mock"  # Dream-1 in the live cell is not wired yet; mock = scripted reference
    request_id: str | None = Field(None, max_length=64)  # idempotency: a resent request is not run twice


def _session() -> CellSession:
    if cell_box[0] is None:
        raise ApiError(409, "no_session", "no cell session; POST /cells/{cell}/session first")
    return cell_box[0]


@app.get("/cells")
def list_cells():
    """The two cell experiments and their tasks."""
    return [{"cell": c, "tasks": [{"task": t, "arm": v["arm"], "prompt": v["prompt"]}
                                  for t, v in CELL_TASKS.items() if v["cell"] == c]} for c in CELLS]


@app.post("/cells/{cell}/session", status_code=202)
def start_cell(cell: str):
    """Start (or restart) the live session of a cell; the previous session is closed."""
    if cell not in CELLS:
        raise ApiError(404, "unknown_cell", f"no cell {cell!r}; see GET /cells")
    if cell_box[0] is not None:
        cell_box[0].close()
    cell_box[0] = CellSession(cell)
    return cell_box[0].public()


@app.get("/cells/session")
def cell_state():
    """Sensors, actuators, busy task, last check result and the latest events."""
    return _session().public()


@app.post("/cells/session/action", status_code=202)
def cell_action(req: CellAction):
    session = _session()
    session.submit("action", action=req.action)
    return {"queued": req.action}


@app.post("/cells/session/task", status_code=202)
def cell_task(req: CellTask):
    session = _session()
    with session.lock:  # check and mark in one step: busy from enqueue on, not only once the session thread starts
        if req.request_id and req.request_id in session.request_ids:
            return {"queued": req.task, "duplicate": True, "motion": "scripted reference controller (not Dream-1)"}
        if session.busy:
            raise ApiError(409, "busy", f"task {session.busy} is running")
        if CELL_TASKS[req.task]["cell"] != session.cell:
            raise ApiError(400, "wrong_cell", f"task {req.task} belongs to cell {CELL_TASKS[req.task]['cell']}")
        session.busy = req.task
        if req.request_id:
            session.request_ids.add(req.request_id)
    session.submit("task", task=req.task, seed=req.seed)
    return {"queued": req.task, "motion": "scripted reference controller (not Dream-1)"}


@app.get("/cells/session/frame.jpg")
def cell_frame(view: Literal["overview", "robot"] = "overview"):
    jpeg = _session().frame(view)
    if jpeg is None:
        raise ApiError(404, "no_frame", "no frame yet")
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.delete("/cells/session", status_code=204)
def stop_cell():
    if cell_box[0] is not None:
        cell_box[0].close()
        cell_box[0] = None
    return Response(status_code=204)


# ---- budget & evaluations ------------------------------------------------------------------------------------
@app.get("/budget")
def budget():
    return runs.budget()


@app.post("/evals", status_code=202)
def start_eval(req: EvalRequest):
    skill = SKILLS.get(req.skill)
    if skill is None:
        raise ApiError(404, "unknown_skill", f"no skill {req.skill!r}; see GET /skills")
    labels = [v.label for v in req.variants]
    if len(set(labels)) != len(labels):
        raise ApiError(400, "invalid_request", "variant labels must be unique")
    if req.mode == "mock" and not skill.mock_available:
        raise ApiError(400, "mock_unavailable", f"skill {req.skill} has no scripted (mock) version")
    if req.mode == "dream":
        if not config.dream_key_set():
            raise ApiError(503, "no_api_key", "DREAM_API_KEY is not set in the simulation container")
        for v in req.variants:
            if v.checkpoint and not (v.checkpoint in config.BASE_CHECKPOINTS or v.checkpoint.startswith("dream-1-ft:")):
                raise ApiError(400, "invalid_checkpoint", f"unknown checkpoint {v.checkpoint!r}")
        if runs.budget()["remaining_usd"] <= 0:
            raise ApiError(402, "budget_exhausted", f"service budget of {config.BUDGET_USD} USD is used up")
    try:
        evaluation = evals.start(skill, [v.model_dump() for v in req.variants], req.trials, req.seed_start,
                                 req.timeout_s, req.mode)
    except BusyError as busy:
        raise ApiError(409, "busy", "another evaluation is running", active_eval_id=busy.active_run_id)
    return {"eval_id": evaluation.eval_id, "status": evaluation.status,
            "runs_planned": req.trials * len(req.variants)}


@app.get("/evals")
def list_evals():
    return evals.list()


@app.get("/evals/{eval_id}")
def get_eval(eval_id: str):
    record = evals.get(eval_id)
    if record is None:
        raise ApiError(404, "unknown_eval", f"no evaluation {eval_id}")
    return record


@app.post("/evals/{eval_id}/stop")
def stop_eval(eval_id: str):
    try:
        evaluation = evals.stop(eval_id)
    except KeyError:
        raise ApiError(404, "unknown_eval", f"no evaluation {eval_id}")
    return evaluation.public()
