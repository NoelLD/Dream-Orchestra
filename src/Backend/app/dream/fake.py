import itertools
import time
from typing import Any

from app.dream.client import DreamError, DreamRun


class FakeDreamClient:
    """Spielt die Statusfolge des Simulationsdienstes nach, ohne Netz und ohne Credits (N2).

    queued → warming → running → succeeded, mit `duration_s` Gesamtdauer. Steuerung über den Prompt:
    `#fail` → failed, `#error` → error, `#hang` → läuft endlos (für Zeitlimits), `#down` → Start schlägt fehl.
    """

    mode = "mock"

    def __init__(self, duration_s: float = 3.0) -> None:
        self.duration_s = duration_s
        self._ids = itertools.count(1)
        self._runs: dict[str, dict[str, Any]] = {}
        self.stopped: list[str] = []

    async def start(self, *, skill: str, prompt: str, checkpoint: str | None) -> str:
        if "#down" in prompt:
            raise DreamError("Simulierter Ausfall: Dienst nicht erreichbar")
        run_id = f"fake_{next(self._ids)}"
        self._runs[run_id] = {"t0": time.monotonic(), "prompt": prompt, "stopped": False}
        return run_id

    async def status(self, run_id: str) -> DreamRun:
        run = self._runs.get(run_id)
        if run is None:
            raise DreamError(f"Unbekannter Lauf {run_id}")
        elapsed = time.monotonic() - run["t0"]
        calls = int(elapsed / 1.6)
        if run["stopped"]:
            return DreamRun(run_id, "stopped", success=False, api_calls=calls)
        if elapsed < self.duration_s * 0.2:
            return DreamRun(run_id, "warming")
        if elapsed < self.duration_s or "#hang" in run["prompt"]:
            return DreamRun(run_id, "running", api_calls=calls)
        if "#fail" in run["prompt"]:
            return DreamRun(run_id, "failed", success=False, api_calls=calls)
        if "#error" in run["prompt"]:
            return DreamRun(run_id, "error", success=False, api_calls=calls, error="Simulierter API-Fehler")
        return DreamRun(run_id, "succeeded", success=True, api_calls=calls)

    async def stop(self, run_id: str) -> None:
        if run_id in self._runs:
            self._runs[run_id]["stopped"] = True
            self.stopped.append(run_id)

    async def aclose(self) -> None:
        return None
