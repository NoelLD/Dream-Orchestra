"""HTTP-Anbindung an den Simulationsdienst (src/Simulation/README.md, API v0.2)."""

from typing import Any

import httpx

from app.dream.client import DreamError, DreamRun
from app.errors import UpstreamError


class SimulationApi:
    """Dünne httpx-Hülle. Fehler des Dienstes kommen als UpstreamError mit seinem Status zurück."""

    def __init__(self, base_url: str, timeout_s: float = 10.0) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_s)

    async def request(self, method: str, path: str, json: Any = None) -> Any:
        try:
            response = await self._http.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise UpstreamError(
                f"Simulationsdienst nicht erreichbar ({type(exc).__name__})",
                status_code=503,
                code="simulation_unavailable",
            ) from exc
        if response.is_error:
            try:
                body = response.json()
                code, detail = body.get("error", "simulation_error"), body.get("detail", response.text)
            except ValueError:
                code, detail = "simulation_error", response.text[:300]
            raise UpstreamError(f"Simulation: {detail}", status_code=response.status_code, code=code)
        return response.json() if response.content else None

    async def aclose(self) -> None:
        await self._http.aclose()


class SimulationDreamClient:
    """Skill-Läufe über den Simulationsdienst. `sim_mode` "dream" = Dream-1 (Credits), "mock" = geskriptet."""

    def __init__(self, api: SimulationApi, *, sim_mode: str, label: str) -> None:
        self.api = api
        self.sim_mode = sim_mode
        self.mode = label

    async def start(self, *, skill: str, prompt: str, checkpoint: str | None) -> str:
        body: dict[str, Any] = {"skill": skill, "prompt": prompt, "mode": self.sim_mode}
        if checkpoint:
            body["checkpoint"] = checkpoint
        try:
            data = await self.api.request("POST", "/runs", body)
        except UpstreamError as exc:
            raise DreamError(exc.detail) from exc
        return str(data["run_id"])

    async def status(self, run_id: str) -> DreamRun:
        try:
            data = await self.api.request("GET", f"/runs/{run_id}")
        except UpstreamError as exc:
            raise DreamError(exc.detail) from exc
        return DreamRun(
            run_id=run_id,
            status=data["status"],
            success=data.get("success"),
            api_calls=data.get("api_calls") or 0,
            error=data.get("error"),
        )

    async def stop(self, run_id: str) -> None:
        try:
            await self.api.request("POST", f"/runs/{run_id}/stop")
        except UpstreamError as exc:
            if exc.status_code != 409:  # 409 = schon beendet
                raise DreamError(exc.detail) from exc

    async def aclose(self) -> None:
        await self.api.aclose()
