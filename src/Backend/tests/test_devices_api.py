from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

MQTT = {"protocol": "mqtt", "host": "broker", "topic": "halle/band2", "password": "geheim"}


def save_workflow(client: TestClient, name: str, block: dict[str, Any]) -> None:
    definition = {
        "blocks": [{"id": "s", "type": "start"}, {"id": "x", **block}, {"id": "e", "type": "end"}],
        "edges": [{"source": "s", "target": "x"}, {"source": "x", "target": "e"}],
    }
    assert client.post("/api/workflows", json={"name": name, "definition": definition}).status_code == 201


def test_create_mqtt_device_hides_password(client: TestClient) -> None:
    response = client.post("/api/devices", json={"name": "Band 2", "type": "conveyor", "config": MQTT})
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["id"], body["kind"], body["protocol"], body["simulated"]) == ("band-2", "actuator", "mqtt", True)
    assert body["value"] is False
    assert body["config"]["password_set"] is True
    assert "geheim" not in response.text
    assert "geheim" not in client.get("/api/devices").text


def test_update_keeps_password_and_switch_protocol_drops_it(client: TestClient) -> None:
    client.post("/api/devices", json={"name": "Band 2", "type": "conveyor", "config": MQTT})
    without_password = {**MQTT, "password": None, "topic": "halle/neu"}
    updated = client.put("/api/devices/band-2", json={"name": "Band 2", "type": "conveyor", "config": without_password})
    assert updated.status_code == 200, updated.text
    assert updated.json()["config"]["password_set"] is True
    assert updated.json()["config"]["topic"] == "halle/neu"
    virtual = client.put(
        "/api/devices/band-2", json={"name": "Band 2", "type": "conveyor", "config": {"protocol": "virtual"}}
    )
    assert virtual.json()["config"] == {"protocol": "virtual"}


def test_type_change_resets_value(client: TestClient) -> None:
    client.put("/api/devices/fuellstand/value", json={"value": 4})
    response = client.put("/api/devices/fuellstand", json={"name": "Füllstand", "type": "switch", "unit": "Stk"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["value"] is False
    assert body["unit"] is None
    assert body["id"] == "fuellstand"


def test_delete_blocked_when_used(client: TestClient) -> None:
    save_workflow(client, "Sortierung", {"type": "wait_sensor", "params": {"device": "lichtschranke", "value": True}})
    blocked = client.delete("/api/devices/lichtschranke")
    assert blocked.status_code == 409
    assert blocked.json()["details"][0]["name"] == "Sortierung"
    assert client.delete("/api/devices/taster").status_code == 204
    assert "taster" not in {d["id"] for d in client.get("/api/devices").json()}
    assert client.delete("/api/devices/taster").status_code == 404


def test_kind_change_blocked_when_used(client: TestClient) -> None:
    save_workflow(client, "Ampel", {"type": "set_actuator", "params": {"device": "lampe", "value": True}})
    assert client.put("/api/devices/lampe", json={"name": "Lampe", "type": "switch"}).status_code == 409
    assert client.put("/api/devices/lampe", json={"name": "Lampe neu", "type": "conveyor"}).status_code == 200


def test_invalid_opcua_endpoint(client: TestClient) -> None:
    config = {"protocol": "opcua", "endpoint": "http://x", "node_id": "ns=2;s=A"}
    assert client.post("/api/devices", json={"name": "A", "type": "switch", "config": config}).status_code == 422


def test_devices_persist_across_restart(client: TestClient, settings: Settings) -> None:
    config = {"protocol": "opcua", "endpoint": "opc.tcp://anlage:4840", "node_id": "ns=2;s=Tor"}
    client.post("/api/devices", json={"name": "Tor offen", "type": "switch", "config": config})
    client.delete("/api/devices/taster")
    with TestClient(create_app(settings)) as again:
        devices = {d["id"]: d for d in again.get("/api/devices").json()}
    assert devices["tor-offen"]["config"]["node_id"] == "ns=2;s=Tor"
    assert "taster" not in devices
    assert devices["weitere-objekte"]["value"] is True  # Startwert des Startbestands


def test_set_value_route(client: TestClient) -> None:
    assert client.put("/api/devices/fuellstand/value", json={"value": 4.5}).json()["value"] == 4.5
    assert client.put("/api/devices/lampe/value", json={"value": True}).status_code == 409
    assert client.put("/api/devices/gibtsnicht/value", json={"value": True}).status_code == 404


def test_new_device_usable_in_run_check(client: TestClient) -> None:
    client.post("/api/devices", json={"name": "Tor offen", "type": "switch"})
    definition = {
        "blocks": [
            {"id": "s", "type": "start"},
            {"id": "w", "type": "wait_sensor", "params": {"device": "tor-offen", "value": True}},
            {"id": "e", "type": "end"},
        ],
        "edges": [{"source": "s", "target": "w"}, {"source": "w", "target": "e"}],
    }
    result = client.post("/api/workflows/validate", json=definition).json()
    assert result["valid"] is True, result
