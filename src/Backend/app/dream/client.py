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
    status: str  # queued | warming | running | finalizing | succeeded | failed | timeout | stopped | error
    success: bool | None = None
    api_calls: int = 0
    error: str | None = None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL


class DreamError(Exception):
    """Fehler beim Starten, Abfragen oder Stoppen. Die Engine schreibt ihn ins Protokoll (N4)."""


class DreamClient(Protocol):
    mode: str

    async def start(self, *, skill: str, prompt: str, checkpoint: str | None) -> str:
        """Startet einen Skill-Lauf und gibt dessen ID zurück."""
        ...

    async def status(self, run_id: str) -> DreamRun: ...

    async def stop(self, run_id: str) -> None: ...

    async def aclose(self) -> None: ...
