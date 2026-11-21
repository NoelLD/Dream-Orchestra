"""HTTP-Anbindung an den Simulationsdienst (src/Simulation/README.md, API v0.2)."""

import asyncio
import time
from typing import Any

import httpx

from app.dream.client import DreamError, DreamRun
from app.errors import UpstreamError


class SimulationApi:
    """Dünne httpx-Hülle. Fehler des Dienstes kommen als UpstreamError mit seinem Status und Code zurück."""

    def __init__(self, base_url: str, timeout_s: float = 10.0, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)

    async def send(self, method: str, path: str, json: Any = None) -> httpx.Response:
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
        return response

    async def request(self, method: str, path: str, json: Any = None) -> Any:
        response = await self.send(method, path, json)
        return response.json() if response.content else None

    async def aclose(self) -> None:
        await self._http.aclose()


class SimulationDreamClient:
    """Skill-Läufe über den Simulationsdienst. `sim_mode` "dream" = Dream-1 (Credits), "mock" = geskriptet."""

    def __init__(
        self, api: SimulationApi, *, sim_mode: str, label: str, busy_wait_s: float = 30.0, busy_poll_s: float = 1.0
    ) -> None:
        self.api = api
        self.sim_mode = sim_mode
        self.mode = label
        self.busy_wait_s = busy_wait_s
        self.busy_poll_s = busy_poll_s

    async def start(self, *, skill: str, prompt: str, checkpoint: str | None, timeout_s: float | None = None) -> str:
        body: dict[str, Any] = {"skill": skill, "prompt": prompt, "mode": self.sim_mode}
        if checkpoint:
            body["checkpoint"] = checkpoint
        if timeout_s is not None:
            body["timeout_s"] = timeout_s
        # Der Dienst fährt einen Lauf zur Zeit; nach einem Stopp schreibt er noch das Video (409 busy).
        deadline = time.monotonic() + self.busy_wait_s
        while True:
            try:
                data = await self.api.request("POST", "/runs", body)
                return str(data["run_id"])
            except UpstreamError as exc:
                if exc.code == "busy" and time.monotonic() < deadline:
                    await asyncio.sleep(self.busy_poll_s)
                    continue
                raise DreamError(exc.detail) from exc

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
            cost_usd=data.get("cost_usd") or 0.0,
            error=data.get("error"),
        )

    async def stop(self, run_id: str) -> None:
        try:
            await self.api.request("POST", f"/runs/{run_id}/stop")
        except UpstreamError as exc:
            if exc.code != "already_finished":
                raise DreamError(exc.detail) from exc

    async def aclose(self) -> None:
        await self.api.aclose()
