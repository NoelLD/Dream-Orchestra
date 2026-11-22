"""Geräte-Schnittstelle (F11). Jedes Gerät hat Name, Typ, Wert, Protokoll und Protokoll-Einstellungen.

`DeviceRegistry` hält den Gerätestamm (dauerhaft in SQLite) und die Werte (im Speicher, simuliert): Der Nutzer bedient
die Sensoren über die API, der Ablauf schaltet die Aktoren. Ein echter MQTT- oder OPC-UA-Adapter (F13) würde später je
Protokoll Werte lesen und schreiben; Engine und Workflows sprechen weiter nur `list/get/set`.
"""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from app.db import repo
from app.db.database import Database
from app.errors import ConflictError, InvalidError, NotFoundError, UpstreamError
from app.schemas.devices import ACTUATOR_TYPES, DeviceIn, DeviceKind, DeviceType, kind_of

__all__ = [
    "ACTUATOR_TYPES",
    "DEFAULT_DEVICES",
    "Device",
    "DeviceAdapter",
    "DeviceKind",
    "DeviceRegistry",
    "DeviceType",
    "VirtualAdapter",
]


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    type: DeviceType
    value: bool | float
    adapter: str = "virtual"
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    protocol: str = "virtual"
    config: dict[str, Any] = field(default_factory=lambda: {"protocol": "virtual"})

    @property
    def kind(self) -> DeviceKind:
        return kind_of(self.type)


class DeviceAdapter(Protocol):
    name: str

    def list(self) -> list[Device]: ...
    def get(self, device_id: str) -> Device: ...
    def set(self, device_id: str, value: bool | float) -> Device: ...


# Startbestand – gleiche Geräte wie im Frontend-Mock (src/Frontend/src/api/mockClient.ts) und im Beispiel-Workflow.
DEFAULT_DEVICES = (
    Device("lichtschranke", "Lichtschranke", DeviceType.SWITCH, False),
    Device("taster", "Taster „Start“", DeviceType.BUTTON, False),
    Device("weitere-objekte", "Weitere Objekte", DeviceType.SWITCH, True),
    Device("fuellstand", "Füllstand Kiste", DeviceType.NUMBER, 0.0, unit="Stk", min=0, max=10),
    Device("lampe", "Signallampe grün", DeviceType.LAMP, False),
    Device("lampe-rot", "Signallampe rot", DeviceType.LAMP, False),
    Device("foerderband", "Förderband", DeviceType.CONVEYOR, False),
)
_START_VALUES = {d.id: (d.type, d.value) for d in DEFAULT_DEVICES}


def initial_value(device_type: DeviceType, minimum: float | None) -> bool | float:
    return float(minimum or 0.0) if device_type is DeviceType.NUMBER else False


def _from_row(row: dict[str, Any], value: bool | float) -> Device:
    return Device(
        id=row["id"],
        name=row["name"],
        type=DeviceType(row["type"]),
        value=value,
        unit=row["unit"],
        min=row["min"],
        max=row["max"],
        protocol=row["protocol"],
        config=row["config"],
    )


class VirtualAdapter:
    """Geräte nur im Speicher (für Engine-Tests ohne Datenbank)."""

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


class DeviceRegistry(VirtualAdapter):
    """Gerätestamm aus SQLite (write-through) mit simulierten Werten im Speicher."""

    def __init__(self, db: Database) -> None:
        super().__init__(())
        self.db = db
        # Wächter: Grund, warum ein Sensor gerade keinen gültigen Wert hat (z. B. Zelle getrennt), sonst None
        self.guards: list[Callable[[str], str | None]] = []
        # Quittung: wird nach dem Schalten eines Aktors im Ablauf abgewartet (z. B. Zellen-Aktion)
        self.apply_hooks: list[Callable[[Device], Awaitable[None]]] = []

    def unavailable_reason(self, device_id: str) -> str | None:
        """Warum der Wert gerade nicht gilt (Zelle getrennt, Wert zu alt), sonst None."""
        for guard in self.guards:
            if (reason := guard(device_id)) is not None:
                return reason
        return None

    def read(self, device_id: str) -> Device:
        """Wert für den Ablauf: wie `get`, aber Fehler statt eines veralteten Werts."""
        if (reason := self.unavailable_reason(device_id)) is not None:
            raise UpstreamError(reason, status_code=503, code="sensor_unavailable")
        return self.get(device_id)

    async def apply(self, device_id: str, value: bool | float) -> Device:
        """Aktor im Ablauf schalten und auf die Quittung warten; Fehler gehen an den Block (Fehlerpfad)."""
        device = self.set(device_id, value)
        for hook in self.apply_hooks:
            await hook(device)
        return device

    def ensure(self, devices: Iterable[Device]) -> None:
        """Fehlende Geräte mit fester ID anlegen (vorhandene und vom Nutzer geänderte bleiben)."""
        for d in devices:
            if d.id not in self._devices:
                repo.insert_device(
                    self.db,
                    d.id,
                    {
                        "name": d.name,
                        "type": d.type.value,
                        "config": {"protocol": "virtual"},
                        "unit": None,
                        "min": None,
                        "max": None,
                    },
                )
                self._devices[d.id] = d

    def load(self) -> None:
        """Nach `init_schema` aufrufen: legt bei leerer Tabelle den Startbestand an und lädt alle Geräte."""
        repo.seed_devices(
            self.db,
            (
                {
                    "id": d.id,
                    "name": d.name,
                    "type": d.type.value,
                    "config": {"protocol": "virtual"},
                    "unit": d.unit,
                    "min": d.min,
                    "max": d.max,
                }
                for d in DEFAULT_DEVICES
            ),
        )
        self._devices = {}
        for row in repo.list_devices(self.db):
            device_type = DeviceType(row["type"])
            start_type, start_value = _START_VALUES.get(row["id"], (None, None))
            value = start_value if start_type is device_type and start_value is not None else None
            self._devices[row["id"]] = _from_row(
                row, initial_value(device_type, row["min"]) if value is None else value
            )

    def create(self, data: DeviceIn) -> Device:
        row = repo.create_device(self.db, data.model_dump(mode="json"))
        device = _from_row(row, initial_value(data.type, data.min))
        self._devices[device.id] = device
        return device

    def update(self, device_id: str, data: DeviceIn) -> Device:
        old = self.get(device_id)
        values = data.model_dump(mode="json")
        config = values["config"]
        if "password" in config and not config["password"] and old.protocol == config["protocol"]:
            config["password"] = old.config.get("password")  # leer = unverändert
        if kind_of(data.type) is not old.kind and repo.workflows_using_device(self.db, device_id):
            raise ConflictError(
                f"'{device_id}' wird in Workflows als {old.kind.value} verwendet; Art kann nicht wechseln"
            )
        row = repo.update_device(self.db, device_id, values)
        value = old.value if data.type is old.type else initial_value(data.type, data.min)
        device = _from_row(row, value)
        self._devices[device_id] = device
        return device

    def delete(self, device_id: str) -> None:
        self.get(device_id)
        using = repo.workflows_using_device(self.db, device_id)
        if using:
            names = ", ".join(f"„{w['name']}“" for w in using)
            raise ConflictError(f"Gerät '{device_id}' wird in Workflows verwendet: {names}", details=using)
        repo.delete_device(self.db, device_id)
        del self._devices[device_id]


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
