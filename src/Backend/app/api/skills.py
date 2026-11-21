from typing import Any

from fastapi import APIRouter, status

from app.api.deps import Svc
from app.db import repo
from app.schemas.models import SkillIn, SkillOut

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.get("", response_model=list[SkillOut])
def list_skills(services: Svc) -> list[dict[str, Any]]:
    return repo.list_skills(services.db)


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def create_skill(services: Svc, data: SkillIn) -> dict[str, Any]:
    return repo.create_skill(services.db, data.model_dump())


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(services: Svc, skill_id: int) -> dict[str, Any]:
    return repo.get_skill(services.db, skill_id)


@router.put("/{skill_id}", response_model=SkillOut)
def update_skill(services: Svc, skill_id: int, data: SkillIn) -> dict[str, Any]:
    return repo.update_skill(services.db, skill_id, data.model_dump())


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(services: Svc, skill_id: int) -> None:
    repo.delete_skill(services.db, skill_id)
