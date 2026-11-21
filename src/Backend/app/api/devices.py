from fastapi import APIRouter

from app.api.deps import Svc
from app.devices.adapter import Device, set_by_user
from app.schemas.models import DeviceOut, DeviceValue

router = APIRouter(prefix="/devices", tags=["Geräte"])


def _out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=device.id, name=device.name, type=device.type, kind=device.kind, adapter=device.adapter, value=device.value
    )


@router.get("", response_model=list[DeviceOut], summary="Geräteleiste (F10)")
def list_devices(services: Svc) -> list[DeviceOut]:
    return [_out(d) for d in services.devices.list()]


@router.put("/{device_id}", response_model=DeviceOut, summary="Sensor bedienen (Aktoren schaltet der Ablauf)")
def set_device(services: Svc, device_id: str, data: DeviceValue) -> DeviceOut:
    return _out(set_by_user(services.devices, device_id, data.value))
