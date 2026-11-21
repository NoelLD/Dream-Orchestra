import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SECRET = "sk-test-SECRET-do-not-leak-1234567890"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        dream_api_mode="mock",  # Tests rufen nie die echte API auf
        dream_api_key=SECRET,
        database_path=tmp_path / "test.sqlite3",
        simulation_url="http://127.0.0.1:9",  # unerreichbar, falls doch etwas durchrutscht
        poll_interval_s=0.01,
        sensor_poll_interval_s=0.01,
        fake_run_duration_s=0.05,
        default_block_timeout_s=5,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def wait_for(fetch: Callable[[], Any], done: Callable[[Any], bool], timeout: float = 5.0) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        value = fetch()
        if done(value):
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f"Zeitüberschreitung, letzter Wert: {value}")
        time.sleep(0.02)
