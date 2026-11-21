import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import SECRET, wait_for


def create_demo(client: TestClient, loop_prompt: str = "pick up the banana") -> int:
    skill = client.post("/api/skills", json={"name": "pick-banana", "description": "Banane greifen"}).json()
    definition = {
        "blocks": [
            {"id": "start", "type": "start"},
            {"id": "grab", "type": "prompt", "params": {"skill_id": skill["id"], "prompt": loop_prompt}},
            {"id": "wait", "type": "wait_sensor", "params": {"device": "lichtschranke", "value": True}},
            {"id": "more", "type": "condition", "params": {"device": "weitere-objekte", "value": True}},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "grab"},
            {"source": "grab", "target": "wait"},
            {"source": "wait", "target": "more"},
            {"source": "more", "target": "grab", "port": "true"},
            {"source": "more", "target": "end", "port": "false"},
        ],
    }
    response = client.post("/api/workflows", json={"name": "Demo", "definition": definition})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_health_and_status(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/health").status_code == 200
    assert client.get("/health/database").status_code == 200
    status = client.get("/api/status").json()
    assert status["api_mode"] == "mock"
    assert status["banner"] == "SIMULIERTE API"
    assert status["dream_api_key_set"] is True


def test_skills_crud(client: TestClient) -> None:
    created = client.post("/api/skills", json={"name": "Greifen", "description": "greift"})
    assert created.status_code == 201
    skill = created.json()
    assert skill["status"] == "Entwurf"
    assert client.post("/api/skills", json={"name": "Greifen", "description": "x"}).status_code == 409
    updated = client.put(f"/api/skills/{skill['id']}", json={**skill, "status": "Bereit", "fine_tuned_model": "m1"})
    assert updated.json()["fine_tuned_model"] == "m1"
    assert client.delete(f"/api/skills/{skill['id']}").status_code == 204
    assert client.get(f"/api/skills/{skill['id']}").status_code == 404


def test_workflow_save_load_validate(client: TestClient) -> None:
    workflow_id = create_demo(client)
    loaded = client.get(f"/api/workflows/{workflow_id}").json()
    assert len(loaded["definition"]["blocks"]) == 5
    result = client.post("/api/workflows/validate", json=loaded["definition"]).json()
    assert result == {"valid": True, "errors": [], "warnings": [], "credits_estimate": 1}

    loaded["definition"]["blocks"][1]["params"]["prompt"] = ""
    result = client.post("/api/workflows/validate", json=loaded["definition"]).json()
    assert result["valid"] is False
    assert {"block_id": "grab", "message": "Leerer Prompt"} in result["errors"]


def test_invalid_workflow_does_not_start(client: TestClient) -> None:
    response = client.post("/api/workflows", json={"name": "leer", "definition": {"blocks": [], "edges": []}})
    started = client.post("/api/runs", json={"workflow_id": response.json()["id"]})
    assert started.status_code == 422
    assert started.json()["details"]["valid"] is False


def test_demo_run_with_sensor_loop(client: TestClient) -> None:
    workflow_id = create_demo(client)
    client.put("/api/devices/weitere-objekte/value", json={"value": True})
    started = client.post("/api/runs", json={"workflow_id": workflow_id})
    assert started.status_code == 202
    run_id = started.json()["id"]
    assert started.json()["credits_estimate"] == 1

    def get(after: int = 0) -> dict[str, Any]:
        return dict(client.get(f"/api/runs/{run_id}", params={"after": after}).json())

    wait_for(get, lambda r: r["active_block_id"] == "wait")
    assert client.post("/api/runs", json={"workflow_id": workflow_id}).status_code == 409  # nur ein Lauf
    client.put("/api/devices/weitere-objekte/value", json={"value": False})  # keine weitere Runde
    client.put("/api/devices/lichtschranke/value", json={"value": True})
    final = wait_for(get, lambda r: r["status"] != "running")
    assert final["status"] == "succeeded"
    assert final["credits_used"] >= 1
    assert final["log"][-1]["message"] == "Lauf beendet: succeeded"
    assert get(after=final["cursor"])["log"] == []


def test_stop_mid_run(client: TestClient) -> None:
    workflow_id = create_demo(client, loop_prompt="#hang")
    run_id = client.post("/api/runs", json={"workflow_id": workflow_id}).json()["id"]
    wait_for(lambda: client.get(f"/api/runs/{run_id}").json(), lambda r: r["active_block_id"] == "grab")
    stopped = client.post(f"/api/runs/{run_id}/stop").json()
    assert stopped["status"] == "stopped"
    assert any("gestoppt" in entry["message"] for entry in stopped["log"])
    assert client.post(f"/api/runs/{run_id}/stop").status_code == 409


def test_pause_resume(client: TestClient) -> None:
    workflow_id = create_demo(client)
    run_id = client.post("/api/runs", json={"workflow_id": workflow_id}).json()["id"]
    assert client.post(f"/api/runs/{run_id}/pause").json()["status"] == "paused"
    assert client.post(f"/api/runs/{run_id}/resume").json()["status"] == "running"
    client.post(f"/api/runs/{run_id}/stop")


def test_devices(client: TestClient) -> None:
    devices = {d["id"]: d for d in client.get("/api/devices").json()}
    assert {
        "lichtschranke",
        "weitere-objekte",
        "taster",
        "fuellstand",
        "lampe",
        "lampe-rot",
        "foerderband",
    } <= devices.keys()
    assert client.put("/api/devices/fuellstand/value", json={"value": 4.5}).json()["value"] == 4.5
    assert client.put("/api/devices/lampe/value", json={"value": True}).status_code == 409  # Aktor
    assert client.put("/api/devices/weitere-objekte/value", json={"value": 3}).status_code == 422
    assert client.put("/api/devices/gibtsnicht/value", json={"value": True}).status_code == 404


def test_training_proxy_reports_unreachable_simulation(client: TestClient) -> None:
    response = client.get("/api/training/datasets")
    assert response.status_code == 503
    assert response.json()["error"] == "simulation_unavailable"


@pytest.mark.parametrize("path", ["/api/status", "/openapi.json", "/api/skills", "/api/devices", "/api/runs"])
def test_api_key_never_leaks(client: TestClient, caplog: pytest.LogCaptureFixture, path: str) -> None:
    caplog.set_level(logging.DEBUG)
    create_demo(client)
    assert SECRET not in client.get(path).text
    assert SECRET not in caplog.text


SNAPSHOT = {
    "blocks": [
        {"id": "start", "type": "start", "params": {"label": "Los"}},
        {"id": "grab", "type": "prompt", "params": {"skill_id": None, "prompt": "pick up", "timeout_s": 5}},
        {"id": "end", "type": "end"},
    ],
    "edges": [{"id": "e1", "source": "start", "target": "grab"}, {"id": "e2", "source": "grab", "target": "end"}],
}


def test_start_snapshot_with_base_model(client: TestClient) -> None:
    # Momentaufnahme aus dem Editor, ohne gespeicherten Workflow und ohne Skill (Basismodell, Modus mock)
    started = client.post("/api/runs", json={"definition": SNAPSHOT})
    assert started.status_code == 202, started.text
    run = started.json()
    assert run["workflow_id"] is None
    assert run["status"] == "running"
    assert run["credits_estimate"] == 1
    final = wait_for(lambda: client.get(f"/api/runs/{run['id']}").json(), lambda r: r["status"] != "running")
    assert final["status"] == "succeeded"


def test_start_needs_workflow_or_definition(client: TestClient) -> None:
    response = client.post("/api/runs", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "invalid_request"
    assert "workflow_id oder definition" in body["detail"]


def test_workflow_roundtrip_keeps_editor_fields(client: TestClient) -> None:
    created = client.post("/api/workflows", json={"name": "Editor", "definition": SNAPSHOT}).json()
    stored = client.get(f"/api/workflows/{created['id']}").json()["definition"]
    assert stored["blocks"][0]["params"] == {"label": "Los"}
    assert stored["edges"][0]["id"] == "e1"


def test_skill_without_description_and_device_ranges(client: TestClient) -> None:
    assert client.post("/api/skills", json={"name": "Sortieren", "description": ""}).status_code == 201
    fill = next(d for d in client.get("/api/devices").json() if d["id"] == "fuellstand")
    assert (fill["unit"], fill["min"], fill["max"]) == ("Stk", 0, 10)


def test_import_simulation_skills(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    services = client.app.state.services  # type: ignore[attr-defined]
    client.post("/api/skills", json={"name": "pick-banana", "description": "schon da"})

    async def fake_request(method: str, path: str, json: Any = None) -> Any:
        assert (method, path) == ("GET", "/skills")
        return [
            {"name": "pick-banana", "description": "Pick up the banana", "fine_tuned_model": None},
            {"name": "pick-apple", "description": "Pick up the apple", "fine_tuned_model": "dream-1-ft:ab-c"},
        ]

    monkeypatch.setattr(services.simulation, "request", fake_request)
    skills = {s["name"]: s for s in client.post("/api/skills/import-simulation").json()}
    assert skills["pick-banana"]["description"] == "schon da"  # vorhandene bleiben unverändert
    assert skills["pick-apple"]["fine_tuned_model"] == "dream-1-ft:ab-c"


def test_multiple_workflows_list_update_delete(client: TestClient) -> None:
    first = client.post("/api/workflows", json={"name": "Erster", "definition": SNAPSHOT}).json()
    second = client.post("/api/workflows", json={"name": "Zweiter", "definition": SNAPSHOT}).json()
    client.put(f"/api/workflows/{first['id']}", json={"name": "Erster (neu)", "definition": SNAPSHOT})
    assert [w["name"] for w in client.get("/api/workflows").json()] == ["Erster (neu)", "Zweiter"]

    run = client.post("/api/runs", json={"workflow_id": second["id"]}).json()
    wait_for(lambda: client.get(f"/api/runs/{run['id']}").json(), lambda r: r["status"] != "running")
    assert client.delete(f"/api/workflows/{second['id']}").status_code == 204
    assert client.get(f"/api/workflows/{second['id']}").status_code == 404
    assert client.delete(f"/api/workflows/{second['id']}").status_code == 404
    assert client.get(f"/api/runs/{run['id']}").json()["workflow_id"] is None  # Lauf bleibt erhalten
    assert [w["name"] for w in client.get("/api/workflows").json()] == ["Erster (neu)"]
