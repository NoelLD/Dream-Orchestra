"""Demo datasets (generate, validate, upload to Dream Labs) and fine-tuning jobs.

Generation runs tools/record_dataset.py as a subprocess (local backend). The Modal backend fans out on Modal from a
host with the `modal` CLI (tools/modal_gen.py); the API reports it as unavailable inside the container.
State survives restarts in DATA_DIR/training.json.
"""

import json
import logging
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config

log = logging.getLogger("simulation.training")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
STATE_FILE = config.DATA_DIR / "training.json"


class TrainingState:
    def __init__(self):
        self.lock = threading.Lock()
        self.datasets: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        if STATE_FILE.exists():
            try:
                saved = json.loads(STATE_FILE.read_text())
                self.datasets, self.jobs = saved.get("datasets", {}), saved.get("jobs", {})
            except (OSError, json.JSONDecodeError):
                log.warning("unreadable %s, starting empty", STATE_FILE)
        for record in self.datasets.values():  # a generation the service did not survive cannot finish
            if record.get("status") in ("generating", "uploading"):
                record["status"], record["error"] = "failed", "interrupted by a service restart"

    def save(self) -> None:
        with self.lock:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps({"datasets": self.datasets, "jobs": self.jobs}, indent=2))

    # ---- datasets ------------------------------------------------------------------------------------------
    def dataset(self, name: str) -> dict | None:
        record = self.datasets.get(name)
        directory = config.DATASETS_DIR / name
        if record is None and not directory.exists():
            return None
        record = dict(record or {"name": name, "status": "validated" if directory.exists() else "unknown"})
        record.update(_count(directory))
        return record

    def list_datasets(self) -> list[dict]:
        names = set(self.datasets) | {p.name for p in config.DATASETS_DIR.glob("*") if p.is_dir()}
        return [self.dataset(n) for n in sorted(names) if not n.endswith(".sim_results")]

    def generate(self, name: str, episodes: int, randomize: bool, seed: int) -> dict:
        if self.datasets.get(name, {}).get("status") in ("generating", "uploading", "processing"):
            raise ConflictError(f"dataset {name} is busy")
        record = {"name": name, "status": "generating", "backend": "local", "episodes_requested": episodes,
                  "randomize": randomize, "seed": seed, "error": None, "validation": None,
                  "dream_dataset_id": None, "dream_dataset_name": None, "dream_status": None}
        self.datasets[name] = record
        self.save()
        threading.Thread(target=self._generate, args=(record,), daemon=True).start()
        return record

    def _generate(self, record: dict) -> None:
        cmd = [sys.executable, str(config.SERVICE_DIR / "tools/record_dataset.py"),
               "--out", str(config.DATASETS_DIR / record["name"]), "--episodes", str(record["episodes_requested"]),
               "--seed", str(record["seed"])] + (["--randomize"] if record["randomize"] else [])
        proc = subprocess.run(cmd, cwd=config.WORK_DIR, capture_output=True, text=True)
        tail = (proc.stdout + proc.stderr)[-1500:]
        ok = proc.returncode == 0 and "validate_dataset: OK" in proc.stdout
        record["status"] = "validated" if ok else "failed"
        record["validation"] = {"ok": ok, "log_tail": tail[-500:]}
        record["error"] = None if ok else tail[-300:]
        self.save()

    def upload(self, name: str) -> dict:
        record = self.datasets.setdefault(name, {"name": name})
        if not (config.DATASETS_DIR / name / "meta").exists() and not any((config.DATASETS_DIR / name).glob("*/meta")):
            raise NotFoundError(f"no local dataset {name}")
        if record.get("status") in ("generating", "uploading", "processing"):
            raise ConflictError(f"dataset {name} is busy")
        record.update(status="uploading", error=None)
        self.save()
        threading.Thread(target=self._upload, args=(record,), daemon=True).start()
        return record

    def _upload(self, record: dict) -> None:
        from dream import datasets

        from .embodiment import EMBODIMENT

        try:
            embodiment = next((b.name for b in datasets.list_embodiments()
                               if b.name.endswith("/" + config.EMBODIMENT_NAME)), None)
            if embodiment is None:
                embodiment = datasets.add_embodiment(config.EMBODIMENT_NAME, EMBODIMENT).name
            remote_name = f"{record['name']}-{time.strftime('%m%d%H%M')}"  # remote names cannot be reused
            uploaded = datasets.upload_dataset(config.DATASETS_DIR / record["name"], remote_name, embodiment)
            record.update(dream_dataset_id=uploaded.id, dream_dataset_name=uploaded.name,
                          dream_status=uploaded.status, status="processing")
            self.save()
            while record["dream_status"] not in ("processed", "failed"):
                time.sleep(20)
                current = datasets.get_dataset(uploaded.id)
                record["dream_status"] = current.status
                if current.status == "failed":
                    record["error"] = getattr(current, "error", None)
            record["status"] = "processed" if record["dream_status"] == "processed" else "failed"
        except Exception as error:
            log.exception("upload of %s failed", record["name"])
            record.update(status="failed", error=f"{type(error).__name__}: {str(error)[:300]}")
        self.save()

    # ---- fine-tuning ---------------------------------------------------------------------------------------
    def finetune(self, dataset: str, suffix: str, steps: int, lr_schedule: str, confirm_cost_usd: float) -> dict:
        from dream import fine_tuning

        price = round(steps * config.PRICE_PER_FINETUNE_STEP_USD, 2)
        if abs(confirm_cost_usd - price) > 1e-6:
            raise ValueError(f"confirm_cost_usd must be {price} for {steps} steps")
        record = self.datasets.get(dataset)
        if not record or record.get("status") != "processed" or not record.get("dream_dataset_name"):
            raise ConflictError(f"dataset {dataset} is not processed at Dream Labs yet")
        job = fine_tuning.create(record["dream_dataset_name"], suffix, steps=steps, lr_schedule=lr_schedule)
        self.jobs[job["id"]] = {"job_id": job["id"], "dataset": dataset, "suffix": suffix, "steps": steps,
                                "price_usd": price, "created_at": job.get("created_at")}
        self.save()
        return job


class ConflictError(Exception):
    pass


class NotFoundError(Exception):
    pass


def _count(directory: Path) -> dict:
    """Episodes and frames of a local dataset folder (one session or a folder of sessions)."""
    if (directory / "meta/info.json").exists():
        sessions = [directory]
    elif directory.is_dir():
        sessions = sorted(p for p in directory.iterdir() if (p / "meta/info.json").exists())
    else:
        sessions = []
    episodes = frames = 0
    for session in sessions:
        try:
            info = json.loads((session / "meta/info.json").read_text())
            episodes += info.get("total_episodes", 0)
            frames += info.get("total_frames", 0)
        except (OSError, json.JSONDecodeError):
            continue
    return {"sessions": len(sessions), "episodes": episodes, "frames": frames}


def modal_available() -> bool:
    try:
        import modal  # noqa: F401
    except ImportError:
        return False
    return True
