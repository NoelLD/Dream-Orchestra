from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.db.database import Database
from app.devices.adapter import DeviceAdapter
from app.dream.client import DreamClient
from app.dream.simulation import SimulationApi
from app.runs import RunRegistry


@dataclass
class Services:
    settings: Settings
    db: Database
    dream: DreamClient
    devices: DeviceAdapter
    simulation: SimulationApi
    runs: RunRegistry


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


Svc = Annotated[Services, Depends(get_services)]
