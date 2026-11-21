"""Geräte-Stammdaten: Typ, Art und Protokoll-Einstellungen (MQTT, OPC UA, virtuell).

Die Werte werden vorerst simuliert; die Einstellungen beschreiben, wie ein echter Adapter das Gerät später erreicht.
"""

import re
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


def kind_of(device_type: DeviceType) -> DeviceKind:
    return DeviceKind.ACTUATOR if device_type in ACTUATOR_TYPES else DeviceKind.SENSOR


class Protocol(StrEnum):
    VIRTUAL = "virtual"
    MQTT = "mqtt"
    OPCUA = "opcua"


class VirtualConfig(BaseModel):
    protocol: Literal["virtual"] = "virtual"


class MqttConfig(BaseModel):
    protocol: Literal["mqtt"]
    host: str = Field(min_length=1)
    port: int = Field(default=1883, ge=1, le=65535)
    topic: str = Field(min_length=1)
    qos: int = Field(default=0, ge=0, le=2)
    username: str | None = None
    password: str | None = Field(default=None, description="Nur schreiben; Antworten enthalten password_set")
    tls: bool = False
    payload_path: str | None = Field(default=None, description="JSON-Feld im Payload, z. B. value")


class OpcUaConfig(BaseModel):
    protocol: Literal["opcua"]
    endpoint: str = Field(min_length=1, description="z. B. opc.tcp://anlage:4840")
    node_id: str = Field(min_length=1, description="z. B. ns=2;s=Lichtschranke")
    security_mode: Literal["None", "Sign", "SignAndEncrypt"] = "None"
    username: str | None = None
    password: str | None = Field(default=None, description="Nur schreiben; Antworten enthalten password_set")

    @field_validator("endpoint")
    @classmethod
    def _opc_tcp(cls, value: str) -> str:
        if not value.startswith("opc.tcp://"):
            raise ValueError("Endpoint muss mit opc.tcp:// beginnen")
        return value


DeviceConfig = Annotated[VirtualConfig | MqttConfig | OpcUaConfig, Field(discriminator="protocol")]


class DeviceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: DeviceType
    config: DeviceConfig = Field(default_factory=VirtualConfig)
    unit: str | None = None
    min: float | None = None
    max: float | None = None

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name darf nicht leer sein")
        return value

    @model_validator(mode="after")
    def _ranges(self) -> "DeviceIn":
        if self.type is not DeviceType.NUMBER:
            self.unit = self.min = self.max = None
        elif self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min darf nicht größer als max sein")
        return self


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    """Einstellungen ohne Passwort; stattdessen password_set, falls das Protokoll eines kennt."""
    shown = {k: v for k, v in config.items() if k != "password"}
    if "password" in config:
        shown["password_set"] = bool(config["password"])
    return shown


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().translate(_UMLAUTS)).strip("-")
    return slug or "geraet"
