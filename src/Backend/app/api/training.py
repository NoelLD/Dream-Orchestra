"""Training: dünner Durchgriff auf den Simulationsdienst, der Datensätze erzeugt, hochlädt und fine-tunt.

Bodies und Antworten sind die des Simulationsdienstes (src/Simulation/README.md, „Datasets und Fine-Tuning“).
Fine-Tuning kostet Credits; der Dienst verlangt dafür `confirm_cost_usd`.
"""

from typing import Any

from fastapi import APIRouter, Body, status

from app.api.deps import Svc

router = APIRouter(prefix="/training", tags=["Training"])

DatasetBody = Body(examples=[{"name": "pick-v2", "episodes": 10, "randomize": True, "seed": 0, "backend": "local"}])
FinetuneBody = Body(
    examples=[
        {"dataset": "pick-v2", "suffix": "pick-v2", "steps": 500, "lr_schedule": "cosine", "confirm_cost_usd": 100}
    ]
)


@router.get("/datasets")
async def list_datasets(services: Svc) -> Any:
    return await services.simulation.request("GET", "/datasets")


@router.post("/datasets", status_code=status.HTTP_202_ACCEPTED, summary="Demonstrationen in der Simulation erzeugen")
async def create_dataset(services: Svc, body: dict[str, Any] = DatasetBody) -> Any:
    return await services.simulation.request("POST", "/datasets", body)


@router.get("/datasets/{name}")
async def get_dataset(services: Svc, name: str) -> Any:
    return await services.simulation.request("GET", f"/datasets/{name}")


@router.post("/datasets/{name}/upload", status_code=status.HTTP_202_ACCEPTED, summary="Zu Dream Labs hochladen")
async def upload_dataset(services: Svc, name: str) -> Any:
    return await services.simulation.request("POST", f"/datasets/{name}/upload")


@router.get("/finetune")
async def list_finetunes(services: Svc) -> Any:
    return await services.simulation.request("GET", "/finetune")


@router.post("/finetune", status_code=status.HTTP_202_ACCEPTED, summary="Fine-Tuning starten (kostet Credits)")
async def start_finetune(services: Svc, body: dict[str, Any] = FinetuneBody) -> Any:
    return await services.simulation.request("POST", "/finetune", body)


@router.get("/finetune/{job_id}", summary="Status; am Ende fine_tuned_model per PUT /api/skills/{id} eintragen")
async def get_finetune(services: Svc, job_id: str) -> Any:
    return await services.simulation.request("GET", f"/finetune/{job_id}")
