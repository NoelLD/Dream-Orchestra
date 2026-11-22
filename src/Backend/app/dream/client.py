"""Schnittstelle der Engine zu Dream-1: Skill-Lauf starten, Status abfragen, stoppen (F6, F7).

Die Dream-SDK selbst kennt keinen Lauf mit Status (siehe docs/dream-sdk.md): `get_action()` liefert
nur einen Aktions-Chunk. Den Lauf mit Erfolgsprüfung, Zeitlimit und Stopp stellt der
Simulationsdienst bereit; `SimulationDreamClient` spricht mit ihm, `FakeDreamClient` spielt ihn nach.
"""

from dataclasses import dataclass
from typing import Protocol

# Status-Lebenszyklus des Simulationsdienstes
TERMINAL = frozenset({"succeeded", "failed", "timeout", "stopped", "error"})


@dataclass(frozen=True)
class DreamRun:
    run_id: str
    status: str  # queued | warming | running | stopping | finalizing | succeeded | failed | timeout | stopped | error
    success: bool | None = None
    api_calls: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    note: str | None = None  # Hinweis fürs Protokoll (z. B. Zelle neu bestückt)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL


class DreamError(Exception):
    """Fehler beim Starten, Abfragen oder Stoppen. Die Engine schreibt ihn ins Protokoll (N4)."""


class DreamClient(Protocol):
    mode: str

    async def start(self, *, skill: str, prompt: str, checkpoint: str | None, timeout_s: float | None = None) -> str:
        """Startet einen Skill-Lauf und gibt dessen ID zurück. `timeout_s`: simulierte Sekunden (Simulationsdienst)."""
        ...

    async def status(self, run_id: str) -> DreamRun: ...

    async def stop(self, run_id: str) -> None: ...

    async def aclose(self) -> None: ...
