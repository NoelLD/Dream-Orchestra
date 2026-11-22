"""Ergebnisse der Zellen-Fine-Tunes (vorher/nachher auf 40 gleichen Testszenen).

Die Zusammenfassung schreibt `src/Simulation/tools/results_page.py` nach `data/evals/cells/results.json`;
Compose bindet den Ordner schreibgeschützt ein (`cell_results_path`). Fehlt er (frischer Klon), gilt der
eingecheckte Snapshot `docs/results/results.json` (`cell_results_snapshot_path`). Das Backend liest nur.
"""

import json
from typing import Any

from fastapi import APIRouter

from app.api.deps import Svc
from app.errors import NotFoundError

router = APIRouter(prefix="/results", tags=["Ergebnisse"])


@router.get("/cells", summary="Fine-Tune-Ergebnisse: Erfolg je Modell, gepaart gegen die Basis, Ausgaben")
async def cell_results(services: Svc) -> Any:
    settings = services.settings
    for path in (settings.cell_results_path, settings.cell_results_snapshot_path):  # lokal gemessen, sonst Snapshot
        if path.is_file():
            return json.loads(path.read_text())
    raise NotFoundError("Noch keine Ergebnisse: weder lokale Messdaten noch der Snapshot docs/results/results.json.")
