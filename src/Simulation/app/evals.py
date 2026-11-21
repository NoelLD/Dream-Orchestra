"""Batch evaluation of skill variants (prompt x checkpoint x retry strategy) on held-out scenes.

Every variant runs on the same seeds (paired comparison); seeds start below 1000, so no evaluation scene is a
training scene (datasets use seeds >= 1000). Success is the simulator's verdict. Reported per variant: success rate
with a Wilson 95 % interval, first-attempt rate (same runs, before any retry), calls, cost and cost per success.
All numbers are simulation results with small n, not a statement about real hardware.
"""

import json
import logging
import math
import threading
import time
import uuid

from . import config
from .runner import TERMINAL, BusyError, RunManager, RunSpec, now
from .skills import Skill

log = logging.getLogger("simulation.evals")
EVALS_DIR = config.DATA_DIR / "evals"


def wilson(successes: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def summarize(label: str, results: list[dict]) -> dict:
    n = len(results)
    wins = sum(1 for r in results if r["success"])
    first = sum(1 for r in results if r.get("first_attempt_success"))
    cost = round(sum(r["cost_usd"] for r in results), 4)
    return {
        "label": label,
        "n": n,
        "successes": wins,
        "success_rate": round(wins / n, 3) if n else None,
        "ci95": wilson(wins, n),
        "first_attempt_successes": first,
        "first_attempt_rate": round(first / n, 3) if n else None,
        "first_attempt_ci95": wilson(first, n),
        "api_calls": sum(r["api_calls"] for r in results),
        "cost_usd": cost,
        "cost_per_success_usd": round(cost / wins, 4) if wins else None,
        "mean_attempts_used": round(sum(r["attempts_used"] for r in results) / n, 2) if n else None,
        "errors": sum(1 for r in results if r["status"] == "error"),
    }


class Evaluation:
    def __init__(self, skill: Skill, variants: list[dict], trials: int, seed_start: int, timeout_s: float, mode: str):
        self.eval_id = "eval_" + uuid.uuid4().hex[:8]
        self.skill, self.variants, self.trials = skill, variants, trials
        self.seed_start, self.timeout_s, self.mode = seed_start, timeout_s, mode
        self.status = "queued"
        self.results: dict[str, list[dict]] = {v["label"]: [] for v in variants}
        self.created_at, self.finished_at = now(), None
        self.error: str | None = None
        self.active_run_id: str | None = None
        self.stop_event = threading.Event()

    def public(self) -> dict:
        total = self.trials * len(self.variants)
        done = sum(len(r) for r in self.results.values())
        return {
            "eval_id": self.eval_id, "skill": self.skill.name, "mode": self.mode, "status": self.status,
            "trials": self.trials, "seeds": [self.seed_start, self.seed_start + self.trials - 1],
            "timeout_s": self.timeout_s, "progress": {"done": done, "total": total},
            "active_run_id": self.active_run_id, "variants": self.variants,
            "summary": [summarize(label, results) for label, results in self.results.items()],
            "runs": {label: [r["run_id"] for r in results] for label, results in self.results.items()},
            "created_at": self.created_at, "finished_at": self.finished_at, "error": self.error,
            "note": "simulation results, small n; success is the simulator's verdict",
        }


class EvalManager:
    def __init__(self, runs: RunManager):
        self.runs = runs
        self.evals: dict[str, Evaluation] = {}
        self.history: list[dict] = []
        EVALS_DIR.mkdir(parents=True, exist_ok=True)
        for path in sorted(EVALS_DIR.glob("eval_*.json")):
            try:
                record = json.loads(path.read_text())
                if record.get("status") in ("queued", "running"):
                    record["status"], record["error"] = "stopped", "interrupted by a service restart"
                self.history.append(record)
            except (OSError, json.JSONDecodeError):
                log.warning("unreadable eval record %s", path)

    def start(self, skill: Skill, variants: list[dict], trials: int, seed_start: int, timeout_s: float,
              mode: str) -> Evaluation:
        if any(e.status in ("queued", "running") for e in self.evals.values()):
            raise BusyError(next(e.eval_id for e in self.evals.values() if e.status in ("queued", "running")))
        evaluation = Evaluation(skill, variants, trials, seed_start, timeout_s, mode)
        self.evals[evaluation.eval_id] = evaluation
        threading.Thread(target=self._execute, args=(evaluation,), daemon=True).start()
        return evaluation

    def get(self, eval_id: str) -> dict | None:
        if eval_id in self.evals:
            return self.evals[eval_id].public()
        return next((e for e in self.history if e["eval_id"] == eval_id), None)

    def list(self) -> list[dict]:
        current = [e.public() for e in self.evals.values()]
        known = {e["eval_id"] for e in current}
        merged = current + [e for e in self.history if e["eval_id"] not in known]
        return sorted(merged, key=lambda e: e["created_at"], reverse=True)

    def stop(self, eval_id: str) -> Evaluation:
        evaluation = self.evals.get(eval_id)
        if evaluation is None:
            raise KeyError(eval_id)
        evaluation.stop_event.set()
        if evaluation.active_run_id:
            try:
                self.runs.stop(evaluation.active_run_id)
            except Exception:
                pass
        return evaluation

    def _save(self, evaluation: Evaluation) -> None:
        (EVALS_DIR / f"{evaluation.eval_id}.json").write_text(json.dumps(evaluation.public(), indent=2))

    def _execute(self, evaluation: Evaluation) -> None:
        evaluation.status = "running"
        try:
            for trial in range(evaluation.trials):
                seed = evaluation.seed_start + trial
                for variant in evaluation.variants:  # interleaved: every variant sees the same scene in turn
                    if evaluation.stop_event.is_set():
                        evaluation.status = "stopped"
                        return
                    if evaluation.mode == "dream" and self.runs.budget()["remaining_usd"] <= 0:
                        evaluation.status, evaluation.error = "stopped", "budget_exhausted"
                        return
                    run_id = self._start_run(evaluation, variant, seed)
                    evaluation.active_run_id = run_id
                    result = self._wait(run_id)
                    evaluation.active_run_id = None
                    attempts = result.get("attempts") or []
                    evaluation.results[variant["label"]].append({
                        "run_id": run_id, "seed": seed, "status": result["status"],
                        "success": bool(result["success"]),
                        "first_attempt_success": bool(attempts and attempts[0].get("success")),
                        "attempts_used": result.get("attempts_used", 1), "api_calls": result["api_calls"],
                        "cost_usd": result["cost_usd"],
                    })
                    self._save(evaluation)
            evaluation.status = "completed"
        except Exception as error:
            log.exception("eval %s failed", evaluation.eval_id)
            evaluation.status, evaluation.error = "error", f"{type(error).__name__}: {str(error)[:300]}"
        finally:
            evaluation.finished_at = now()
            self._save(evaluation)

    def _start_run(self, evaluation: Evaluation, variant: dict, seed: int) -> str:
        spec = RunSpec(
            skill=evaluation.skill, mode=evaluation.mode,
            prompt=variant.get("prompt") or evaluation.skill.default_prompt,
            checkpoint=variant.get("checkpoint") or config.DEFAULT_CHECKPOINT,
            timeout_s=evaluation.timeout_s, seed=seed, record_video=True,
            max_attempts=variant.get("max_attempts", 1), recovery=variant.get("recovery", "rehome"),
            recovery_prompts=variant.get("recovery_prompts") or [], eval_id=evaluation.eval_id,
        )
        while True:  # wait for a free slot (a manual run may be active)
            try:
                return self.runs.start(spec).run_id
            except BusyError:
                if evaluation.stop_event.is_set():
                    raise
                time.sleep(2)

    def _wait(self, run_id: str) -> dict:
        while True:
            run = self.runs.get(run_id)
            if run and run["status"] in TERMINAL:
                return run
            time.sleep(1)
