from fastapi import APIRouter, Response, status

from app.api.deps import Svc
from app.devices.adapter import Device, set_by_user
from app.schemas.devices import DeviceIn, public_config
from app.schemas.models import DeviceOut, DeviceValue

router = APIRouter(prefix="/devices", tags=["Geräte"])


def _out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=device.id,
        name=device.name,
        type=device.type,
        kind=device.kind,
        adapter=device.adapter,
        value=device.value,
        unit=device.unit,
        min=device.min,
        max=device.max,
        protocol=device.protocol,
        config=public_config(device.config),
        simulated=True,
    )


@router.get("", response_model=list[DeviceOut], summary="Geräte mit aktuellem (simuliertem) Wert")
def list_devices(services: Svc) -> list[DeviceOut]:
    return [_out(d) for d in services.devices.list()]


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED, summary="Gerät anlegen")
def create_device(services: Svc, data: DeviceIn) -> DeviceOut:
    return _out(services.devices.create(data))


@router.put("/{device_id}", response_model=DeviceOut, summary="Stammdaten ändern (leeres Passwort = unverändert)")
def update_device(services: Svc, device_id: str, data: DeviceIn) -> DeviceOut:
    return _out(services.devices.update(device_id, data))


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Gerät löschen (409, solange ein gespeicherter Workflow es verwendet)",
)
def delete_device(services: Svc, device_id: str) -> Response:
    services.devices.delete(device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{device_id}/value", response_model=DeviceOut, summary="Sensor bedienen (Aktoren schaltet der Ablauf)")
def set_device_value(services: Svc, device_id: str, data: DeviceValue) -> DeviceOut:
    return _out(set_by_user(services.devices, device_id, data.value))
