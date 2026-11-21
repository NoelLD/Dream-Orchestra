"""Geräte-Schnittstelle (F11). Jedes Gerät hat Name, Typ, Wert und einen Adapter.

Für den Hackathon gibt es nur `VirtualAdapter`: Werte liegen im Speicher, der Nutzer bedient die
Sensoren über die API, der Ablauf schaltet die Aktoren. Ein MQTT-Adapter (F13) würde dieselbe
Schnittstelle implementieren.
"""

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from app.errors import ConflictError, InvalidError, NotFoundError


class DeviceType(StrEnum):
    SWITCH = "switch"  # Schalter
    BUTTON = "button"  # Taster
    NUMBER = "number"  # Zahlenwert
    LAMP = "lamp"  # Lampe
    CONVEYOR = "conveyor"  # Förderband an/aus


class DeviceKind(StrEnum):
    SENSOR = "sensor"
    ACTUATOR = "actuator"


ACTUATOR_TYPES = {DeviceType.LAMP, DeviceType.CONVEYOR}


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    type: DeviceType
    value: bool | float
    adapter: str = "virtual"

    @property
    def kind(self) -> DeviceKind:
        return DeviceKind.ACTUATOR if self.type in ACTUATOR_TYPES else DeviceKind.SENSOR


class DeviceAdapter(Protocol):
    name: str

    def list(self) -> list[Device]: ...
    def get(self, device_id: str) -> Device: ...
    def set(self, device_id: str, value: bool | float) -> Device: ...


DEFAULT_DEVICES = (
    Device("lichtschranke", "Lichtschranke", DeviceType.SWITCH, False),
    Device("schalter", "Schalter", DeviceType.SWITCH, False),
    Device("taster", "Taster", DeviceType.BUTTON, False),
    Device("pruefwert", "Prüfwert", DeviceType.NUMBER, 0.0),
    Device("lampe", "Lampe", DeviceType.LAMP, False),
    Device("foerderband", "Förderband", DeviceType.CONVEYOR, False),
)


class VirtualAdapter:
    name = "virtual"

    def __init__(self, devices: tuple[Device, ...] = DEFAULT_DEVICES) -> None:
        self._devices = {device.id: device for device in devices}

    def list(self) -> list[Device]:
        return list(self._devices.values())

    def get(self, device_id: str) -> Device:
        try:
            return self._devices[device_id]
        except KeyError:
            raise NotFoundError(f"Gerät '{device_id}' nicht gefunden") from None

    def set(self, device_id: str, value: bool | float) -> Device:
        device = self.get(device_id)
        updated = replace(device, value=coerce(device.type, value))
        self._devices[device_id] = updated
        return updated


def coerce(device_type: DeviceType, value: bool | float) -> bool | float:
    if device_type is DeviceType.NUMBER:
        if isinstance(value, bool):
            raise InvalidError("Zahlenwert erwartet eine Zahl, nicht true/false")
        return float(value)
    if not isinstance(value, bool):
        raise InvalidError(f"{device_type.value} erwartet true/false")
    return value


def set_by_user(adapter: DeviceAdapter, device_id: str, value: bool | float) -> Device:
    """F10: Der Nutzer bedient Sensoren; Aktoren schaltet nur der Ablauf."""
    if adapter.get(device_id).kind is DeviceKind.ACTUATOR:
        raise ConflictError(f"'{device_id}' ist ein Aktor und wird vom Ablauf geschaltet")
    return adapter.set(device_id, value)
