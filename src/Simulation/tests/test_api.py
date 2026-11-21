"""API tests in mock mode: no Dream API calls, no credits.

    docker compose run --rm simulation python -m pytest -q /app/tests
"""

import os
import tempfile
import time

os.environ["SIM_DATA_DIR"] = tempfile.mkdtemp(prefix="simtest-")
os.environ.pop("DREAM_API_KEY", None)  # tests must never spend credits

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def wait_for_end(run_id: str, timeout: float = 240) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] in ("succeeded", "failed", "timeout", "stopped", "error"):
            return run
        time.sleep(1)
    raise AssertionError(f"run {run_id} did not finish")


def test_health_without_key_offers_mock_only():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["service"] == "simulation"
    assert body["dream_key_set"] is False and body["modes"] == ["mock"]


def test_skills_have_success_checks():
    skills = {s["name"]: s for s in client.get("/skills").json()}
    assert {"pick-banana", "pick-apple", "banana-to-plate", "apple-to-bowl"} <= set(skills)
    assert skills["pick-banana"]["mock_available"] and not skills["banana-to-plate"]["mock_available"]


def test_robots_own_skills_and_checkpoint():
    robots = {r["name"]: r for r in client.get("/robots").json()}
    yam = robots["yam-sim"]
    assert {"pick-banana", "pick-apple"} <= set(yam["skills"]) and yam["embodiment"] == "yam-sim"
    assert yam["fine_tuned_model"] is None  # no finished fine-tune in a fresh data dir: base model
    skills = {s["name"]: s for s in client.get("/skills").json()}
    assert skills["pick-banana"]["robot"] == "yam-sim" and skills["pick-banana"]["fine_tuned_model"] is None
    missing = client.get("/robots/nope")
    assert missing.status_code == 404 and missing.json()["error"] == "unknown_robot"


@pytest.mark.parametrize("payload,status,error", [
    ({"skill": "nope", "mode": "mock"}, 404, "unknown_skill"),
    ({"skill": "pick-banana", "mode": "mock", "prompt": "   "}, 400, "invalid_request"),
    ({"skill": "banana-to-plate", "mode": "mock"}, 400, "mock_unavailable"),
    ({"skill": "pick-banana", "mode": "dream"}, 503, "no_api_key"),
    ({"skill": "pick-banana", "mode": "mock", "timeout_s": 1}, 400, "invalid_request"),
])
def test_rejects_bad_run_requests(payload, status, error):
    response = client.post("/runs", json=payload)
    assert response.status_code == status and response.json()["error"] == error


def test_mock_run_succeeds_with_video_and_zero_cost():
    response = client.post("/runs", json={"skill": "pick-banana", "mode": "mock", "seed": 1})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    busy = client.post("/runs", json={"skill": "pick-apple", "mode": "mock"})
    assert busy.status_code == 409 and busy.json()["active_run_id"] == run_id
    run = wait_for_end(run_id)
    assert run["status"] == "succeeded" and run["success"] is True
    assert run["cost_usd"] == 0.0 and run["api_calls"] == 0
    video = client.get(f"/runs/{run_id}/video")
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4"
    assert client.get("/frame.jpg").headers["content-type"] == "image/jpeg"
    assert any(r["run_id"] == run_id for r in client.get("/runs").json())


def test_stop_ends_a_run():
    run_id = client.post("/runs", json={"skill": "pick-apple", "mode": "mock", "seed": 2}).json()["run_id"]
    time.sleep(3)
    assert client.post(f"/runs/{run_id}/stop").status_code == 200
    run = wait_for_end(run_id)
    assert run["status"] == "stopped" and run["success"] is False
    assert client.post(f"/runs/{run_id}/stop").status_code == 409


def test_finetune_requires_key_and_exact_cost():
    response = client.post("/finetune", json={"dataset": "x", "suffix": "x", "steps": 500, "confirm_cost_usd": 1})
    assert response.status_code == 503  # no key in tests; with a key a wrong cost gives 400 cost_not_confirmed


def test_budget_reports_cap_and_spend():
    body = client.get("/budget").json()
    assert body["budget_usd"] > 0 and body["spent_usd"] == 0.0 and body["is_estimate"] is True


def test_rejects_blank_recovery_prompt():
    response = client.post("/runs", json={"skill": "pick-banana", "mode": "mock", "max_attempts": 2,
                                          "recovery_prompts": [" "]})
    assert response.status_code == 400 and response.json()["error"] == "invalid_request"


def test_mock_eval_reports_rates_with_wilson_interval():
    response = client.post("/evals", json={"skill": "pick-banana", "mode": "mock", "trials": 1, "seed_start": 5,
                                           "variants": [{"label": "scripted"}]})
    assert response.status_code == 202
    eval_id = response.json()["eval_id"]
    deadline = time.time() + 240
    while time.time() < deadline:
        body = client.get(f"/evals/{eval_id}").json()
        if body["status"] not in ("queued", "running"):
            break
        time.sleep(1)
    assert body["status"] == "completed"
    summary = body["summary"][0]
    assert summary["n"] == 1 and summary["success_rate"] == 1.0 and summary["cost_usd"] == 0.0
    assert summary["ci95"][1] == 1.0 and 0 < summary["ci95"][0] < 1


def test_eval_rejects_duplicate_labels_and_training_seeds():
    dup = client.post("/evals", json={"skill": "pick-banana", "mode": "mock",
                                      "variants": [{"label": "a"}, {"label": "a"}]})
    assert dup.status_code == 400
    seeds = client.post("/evals", json={"skill": "pick-banana", "mode": "mock", "seed_start": 1000,
                                        "variants": [{"label": "a"}]})
    assert seeds.status_code == 400


def test_demo_page_and_cors_for_frontend():
    page = client.get("/demo")
    assert page.status_code == 200 and "Testseite" in page.text
    preflight = client.options("/runs", headers={"Origin": "http://localhost:8080",
                                                 "Access-Control-Request-Method": "POST"})
    assert preflight.headers.get("access-control-allow-origin") == "http://localhost:8080"
