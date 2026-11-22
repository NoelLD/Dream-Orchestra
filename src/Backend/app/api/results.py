"""Ergebnisse der Zellen-Fine-Tunes (vorher/nachher auf 40 gleichen Testszenen).

Die Zusammenfassung schreibt `src/Simulation/tools/results_page.py` nach `data/evals/cells/results.json`;
Compose bindet den Ordner schreibgeschützt ein (`cell_results_path`). Das Backend liest nur.
"""

import json
from typing import Any

from fastapi import APIRouter

from app.api.deps import Svc
from app.errors import NotFoundError

router = APIRouter(prefix="/results", tags=["Ergebnisse"])


@router.get("/cells", summary="Fine-Tune-Ergebnisse: Erfolg je Modell, gepaart gegen die Basis, Ausgaben")
async def cell_results(services: Svc) -> Any:
    path = services.settings.cell_results_path
    if not path.is_file():
        raise NotFoundError("Noch keine Ergebnisse: results_page.py hat results.json nicht geschrieben.")
    return json.loads(path.read_text())
