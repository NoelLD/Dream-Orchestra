from fastapi import APIRouter, Response, status

from app.api.deps import Services, Svc
from app.devices.adapter import Device, set_by_user
from app.schemas.devices import DeviceIn, public_config
from app.schemas.models import DeviceOut, DeviceValue

router = APIRouter(prefix="/devices", tags=["Geräte"])


def _out(device: Device, unavailable: str | None = None) -> DeviceOut:
    """Gerät mit Verfügbarkeit: ein Wert, der gerade nicht gilt, wird als solcher gemeldet (nicht als alter Wert)."""
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
        available=unavailable is None,
        unavailable_reason=unavailable,
    )


def _out_live(services: Services, device: Device) -> DeviceOut:
    reason = getattr(services.devices, "unavailable_reason", lambda _: None)(device.id)
    return _out(device, reason)


@router.get("", response_model=list[DeviceOut], summary="Geräte mit aktuellem (simuliertem) Wert")
def list_devices(services: Svc) -> list[DeviceOut]:
    return [_out_live(services, d) for d in services.devices.list()]


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED, summary="Gerät anlegen")
def create_device(services: Svc, data: DeviceIn) -> DeviceOut:
    return _out_live(services, services.devices.create(data))


@router.put("/{device_id}", response_model=DeviceOut, summary="Stammdaten ändern (leeres Passwort = unverändert)")
def update_device(services: Svc, device_id: str, data: DeviceIn) -> DeviceOut:
    return _out_live(services, services.devices.update(device_id, data))


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
    return _out_live(services, set_by_user(services.devices, device_id, data.value))
