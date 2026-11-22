from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import BACKEND_ROOT
from app.db import repo
from app.db.database import Database
from app.schemas.devices import DeviceIn, public_config, slugify


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "t.sqlite3")
    database.init_schema(BACKEND_ROOT / "models" / "schema.sql")
    return database


def device(name: str, type_: str = "switch", **config: Any) -> dict[str, Any]:
    data = DeviceIn.model_validate({"name": name, "type": type_, "config": config or {"protocol": "virtual"}})
    return data.model_dump(mode="json")


def test_slugify() -> None:
    assert slugify("Füllstand Kiste") == "fuellstand-kiste"
    assert slugify("###") == "geraet"
    assert slugify("  Ü ") == "ue"
    assert slugify("Straße/Tor 2") == "strasse-tor-2"


def test_create_device_unique_ids(db: Database) -> None:
    first = repo.create_device(db, device("Band"))
    second = repo.create_device(db, device("Band"))
    assert (first["id"], second["id"]) == ("band", "band-2")
    assert repo.get_device(db, "band-2")["config"] == {"protocol": "virtual"}


def test_config_validation() -> None:
    with pytest.raises(ValidationError):
        DeviceIn.model_validate({"name": "x", "type": "switch", "config": {"protocol": "mqtt", "host": "b"}})
    with pytest.raises(ValidationError):
        DeviceIn.model_validate(
            {"name": "x", "type": "switch", "config": {"protocol": "opcua", "endpoint": "http://x", "node_id": "n"}}
        )
    with pytest.raises(ValidationError):
        DeviceIn.model_validate({"name": "x", "type": "number", "min": 5, "max": 1, "config": {"protocol": "virtual"}})
    with pytest.raises(ValidationError):
        DeviceIn.model_validate({"name": "  ", "type": "switch", "config": {"protocol": "virtual"}})
    plain = DeviceIn.model_validate({"name": "x", "type": "switch", "unit": "x", "config": {"protocol": "virtual"}})
    assert plain.unit is None
    mqtt = DeviceIn.model_validate(
        {"name": "x", "type": "switch", "config": {"protocol": "mqtt", "host": "b", "topic": "t"}}
    )
    assert mqtt.config.model_dump()["port"] == 1883


def test_public_config_hides_password() -> None:
    shown = public_config({"protocol": "mqtt", "host": "b", "topic": "t", "password": "geheim"})
    assert "password" not in shown
    assert shown["password_set"] is True
    assert public_config({"protocol": "virtual"}) == {"protocol": "virtual"}


def test_seed_only_when_empty(db: Database) -> None:
    seed = [{"id": "a", **device("A")}, {"id": "b", **device("B")}]
    repo.seed_devices(db, seed)
    repo.delete_device(db, "a")
    repo.seed_devices(db, seed)
    assert [d["id"] for d in repo.list_devices(db)] == ["b"]


def test_delete_unknown_device(db: Database) -> None:
    from app.errors import NotFoundError

    with pytest.raises(NotFoundError):
        repo.delete_device(db, "gibtsnicht")


def test_workflows_using_device(db: Database) -> None:
    definition = {
        "blocks": [
            {"id": "s", "type": "start"},
            {"id": "a", "type": "set_actuator", "params": {"device": "lampe", "value": True}},
            {"id": "e", "type": "end"},
        ],
        "edges": [],
    }
    wf = repo.create_workflow(db, "Ampel", definition)
    assert repo.workflows_using_device(db, "lampe") == [{"id": wf["id"], "name": "Ampel"}]
    assert repo.workflows_using_device(db, "taster") == []
