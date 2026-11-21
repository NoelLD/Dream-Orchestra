from typing import Any

from fastapi import APIRouter, status

from app.api.deps import Svc
from app.db import repo
from app.schemas.workflow import ValidationResult, WorkflowDefinition, WorkflowIn, WorkflowOut, WorkflowSummary

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(services: Svc) -> list[dict[str, Any]]:
    return repo.list_workflows(services.db)


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED, summary="Speichern als JSON (F3)")
def create_workflow(services: Svc, data: WorkflowIn) -> dict[str, Any]:
    return repo.create_workflow(services.db, data.name, data.definition.model_dump(mode="json"))


@router.post(
    "/validate", response_model=ValidationResult, summary="Prüfung vor dem Start (F4) + Credit-Schätzung (F15)"
)
def validate_workflow(services: Svc, definition: WorkflowDefinition) -> ValidationResult:
    return services.runs.check(definition)


@router.get("/{workflow_id}", response_model=WorkflowOut, summary="Laden (F3)")
def get_workflow(services: Svc, workflow_id: int) -> dict[str, Any]:
    return repo.get_workflow(services.db, workflow_id)


@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(services: Svc, workflow_id: int, data: WorkflowIn) -> dict[str, Any]:
    return repo.update_workflow(services.db, workflow_id, data.name, data.definition.model_dump(mode="json"))
