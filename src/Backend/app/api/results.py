"""Ergebnisse der Zellen-Fine-Tunes (vorher/nachher auf 40 gleichen Testszenen) und die daraus folgende Freigabe.

Die Zusammenfassung schreibt `src/Simulation/tools/results_page.py` nach `data/evals/cells/results.json`;
Compose bindet den Ordner schreibgeschützt ein (`cell_results_path`). Fehlt er (frischer Klon), gilt der
eingecheckte Snapshot `docs/results/results.json` (`cell_results_snapshot_path`). Das Backend liest nur.

`/results/policy` macht sichtbar, wie die Messung das Verhalten steuert: je Aufgabe, welcher Checkpoint zulässig
ist, welche abgelehnt sind (mit Zahl und Grund) und wer im Workflow tatsächlich ausführt. Die Regeln stehen hier
fest im Code (vorab festgelegt, siehe `data/evals/cells/report.md`), die Zahlen kommen aus den Messdaten.
"""

import json
from math import comb
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.api.deps import Svc
from app.config import Settings
from app.errors import NotFoundError

router = APIRouter(prefix="/results", tags=["Ergebnisse"])

MAIN_RECIPE = "ft-main"  # vorab festgelegtes Hauptrezept: c500, 160 Zellen-Vorführungen
REFERENCE = "expert"  # geskripteter Referenz-Controller, führt Zellen-Tasks im Workflow aus
# Varianten des Hauptrezepts: warum sie nicht freigegeben werden (Gesamtzahlen werden ergänzt)
VARIANT_RULES: dict[str, str] = {
    "ft-rep-main": "Replikat desselben Rezepts, misst nur das Trainingsrauschen",
    "ft-lr3-main": "Abstand zum Hauptrezept nicht größer als zwischen zwei gleichen Trainings (Regel vorab)",
    "ft-b05-main": "schlechter als das Hauptrezept (Abstand größer als das Trainingsrauschen)",
    "ft-c1000-main": "nicht besser als c500 bei doppelten Trainingskosten",
    "ft-rep-g15": "explorativ, nicht vorab festgelegt",
}
OUTSIDE_SKILL = {"skill": "pick-banana", "name": "Banane greifen (außerhalb der Zellen)"}


def _first_file(*paths: Path) -> Path | None:
    return next((p for p in paths if p.is_file()), None)


def _load_results(settings: Settings) -> dict[str, Any]:
    path = _first_file(
        settings.cell_results_path, settings.cell_results_snapshot_path
    )  # lokal gemessen, sonst Snapshot
    if path is None:
        raise NotFoundError(
            "Noch keine Ergebnisse: weder lokale Messdaten noch der Snapshot docs/results/results.json."
        )
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def _mcnemar_p(gained: int, lost: int) -> float:
    """Exakter zweiseitiger McNemar-Test (Binomial mit p = 0,5 auf den kippenden Szenen)."""
    n = gained + lost
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(min(gained, lost) + 1)) / float(2**n)
    return min(1.0, 2 * tail)


@router.get("/cells", summary="Fine-Tune-Ergebnisse: Erfolg je Modell, gepaart gegen die Basis, Ausgaben")
async def cell_results(services: Svc) -> Any:
    return _load_results(services.settings)


def _cell_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {m["label"]: m for m in data.get("models", [])}
    base, main, ref = models.get(data.get("base", "")), models.get(MAIN_RECIPE), models.get(REFERENCE)
    first: dict[str, Any] = next(iter(models.values()), {})
    n_total = len(first.get("scenes", [])) or 40
    n_task = n_total // max(len(data.get("tasks", [])), 1)
    rows = []
    for task in data.get("tasks", []):

        def k(m: dict[str, Any] | None, task: str = task) -> int | None:
            return m["tasks"].get(task) if m else None

        rejected = [
            {
                "label": label,
                "name": m["name"],
                "k": k(m),
                "total": m["k"],
                "reason": f"{reason} (gesamt {m['k']}/{n_total}, Hauptrezept {main['k'] if main else '–'}/{n_total})",
            }
            for label, reason in VARIANT_RULES.items()
            if (m := models.get(label))
        ]
        rows.append(
            {
                "skill": task,
                "name": data.get("task_names", {}).get(task, task),
                "scope": "cell",
                "n": n_task,
                "base": {"label": base["label"], "name": base["name"], "k": k(base)} if base else None,
                "checkpoint": (
                    {
                        "label": main["label"],
                        "name": main["name"],
                        "k": k(main),
                        "note": "freigegeben nur für diesen Roboter in den Zellen (nicht Standard für andere Skills)",
                    }
                    if main
                    else None
                ),
                "controller": {
                    "name": "Referenz-Controller (geskriptet)",
                    "k": k(ref),
                    "reason": "gelernter Checkpoint im Workflow noch nicht angebunden; Referenz gemessen zuverlässiger",
                },
                "rejected": rejected,
            }
        )
    return rows


def _outside_row(settings: Settings) -> dict[str, Any] | None:
    path = _first_file(
        settings.cell_results_path.parent / "fruit-forget.json",
        settings.cell_results_snapshot_path.parent / "raw" / "fruit-forget.json",
    )
    if path is None:
        return None
    paired = json.loads(path.read_text()).get("paired", {})
    variants = {v["label"]: v for v in paired.get("variants", [])}
    base = variants.get("beta")
    if base is None:
        return None
    rejected = []
    for label, v in variants.items():
        vs = v.get("vs_reference")
        if label == "beta" or not vs:
            continue
        p = _mcnemar_p(vs["gained"], vs["lost"])
        harms = vs["gained"] == 0 and vs["lost"] >= 6  # vorab festgelegt: „schadet“ ab 6 : 0
        rejected.append(
            {
                "label": label,
                "name": f"Zellen-Fine-Tune {label}",
                "k": v["successes"],
                "total": v["successes"],
                "reason": (
                    f"Vergessen: {base['successes']}/{base['n']} → {v['successes']}/{v['n']} "
                    f"({vs['lost']} : {vs['gained']} gepaart, p = {p:.3f})"
                    + (", Regel „schadet“ erfüllt" if harms else "")
                ),
            }
        )
    return {
        **OUTSIDE_SKILL,
        "scope": "outside",
        "n": base["n"],
        "base": {"label": "beta", "name": "Dream-1 beta (Basis)", "k": base["successes"]},
        "checkpoint": {
            "label": "beta",
            "name": "Dream-1 beta (Basis)",
            "k": base["successes"],
            "note": "Standard des Roboters",
        },
        "controller": {
            "name": "Dream-1 beta (Basis)",
            "k": base["successes"],
            "reason": "Zellen-Fine-Tunes ausgeschlossen",
        },
        "rejected": rejected,
    }


@router.get("/policy", summary="Checkpoint-Freigabe je Aufgabe: zulässig, abgelehnt mit Grund, ausführender Controller")
async def checkpoint_policy(services: Svc) -> Any:
    data = _load_results(services.settings)
    rows = _cell_rows(data)
    outside = _outside_row(services.settings)
    if outside:
        rows.append(outside)
    return {"robot": "yam-sim", "generated_at": data.get("generated_at", ""), "rows": rows}
