from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]

ApiMode = Literal["mock", "sim", "real"]


class Settings(BaseSettings):
    """Alle Werte kommen aus der Umgebung (Compose reicht `.env` durch)."""

    model_config = SettingsConfigDict(extra="ignore")

    version: str = "0.1.0"

    # mock: FakeDreamClient im Backend, ohne Simulation und ohne Credits (Standard, N2)
    # sim:  Simulationsdienst mit geskriptetem Ablauf, ohne Dream-Aufrufe und ohne Credits
    # real: Simulationsdienst mit Dream-1, kostet Credits
    dream_api_mode: ApiMode = "mock"
    dream_api_key: SecretStr | None = None  # N1: nur aus der Umgebung, nie ausgeben

    simulation_url: str = "http://simulation:3001"
    simulation_timeout_s: float = Field(default=10.0, gt=0)

    database_path: Path = BACKEND_ROOT / "data" / "dreamorchestra.sqlite3"
    schema_path: Path = BACKEND_ROOT / "models" / "schema.sql"

    poll_interval_s: float = Field(default=1.0, gt=0)  # N5: Abstand der Statusabfragen
    sensor_poll_interval_s: float = Field(default=0.2, gt=0)
    # Harte Obergrenze; Erfolg und Zeitlimit misst der Simulationsdienst (inkl. Aufwärmphase des Modells)
    default_block_timeout_s: float = Field(default=600.0, gt=0)
    max_steps_per_run: int = Field(default=1000, ge=1)  # Schutz gegen Endlosschleifen
    fake_run_duration_s: float = Field(default=3.0, ge=0)

    cors_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]

    @property
    def api_banner(self) -> str:
        return "ECHTE API" if self.dream_api_mode == "real" else "SIMULIERTE API"


@lru_cache
def get_settings() -> Settings:
    return Settings()
