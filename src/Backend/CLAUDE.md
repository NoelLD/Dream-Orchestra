# Backend (FastAPI)

## Struktur

```
app/
  main.py         App, Lifespan, Fehlerformat, build_services() (Modus mock|sim|real)
  config.py       Settings aus der Umgebung
  errors.py       AppError & Co. (ohne FastAPI)
  runs.py         RunRegistry – einziger globaler Zustand, Läufe als asyncio-Tasks
  api/            Router: health, skills, workflows, runs, devices, training
  schemas/        Pydantic: workflow.py (Workflow-JSON, Parameter), models.py (Skill, Run, Device, Status)
  engine/         engine.py (Zustandsmaschine), validation.py (F4/F15) – rein, ohne FastAPI
  dream/          client.py (Protokoll), fake.py (FakeDreamClient), simulation.py (HTTP zum Simulationsdienst)
  devices/        adapter.py (DeviceAdapter-Protokoll, VirtualAdapter)
  db/             database.py (sqlite3), repo.py (Repository-Funktionen)
models/schema.sql Schema; vorhandene Tabellen nicht ändern, neue nur mit CREATE TABLE IF NOT EXISTS
docs/dream-sdk.md Belegte SDK-Aufrufe
tests/            pytest (Engine + API)
```

API-Vertrag: `../../docs/api-contract.md`, live unter http://localhost:8000/docs.

## Befehle (aus dem Repo-Root)

```sh
docker compose up --build backend                                   # Start mit --reload
docker compose run --rm --no-deps backend python -m pytest          # Tests
docker compose run --rm --no-deps backend ruff check .              # Lint
docker compose run --rm --no-deps backend ruff format --check .     # Format prüfen
docker compose run --rm --no-deps -v ./src/Backend:/work -w /work backend ruff format .   # Formatieren (Mount beschreibbar)
docker compose run --rm --no-deps backend mypy                      # Typen
docker compose exec database python -m sqlite3 /data/dreamorchestra.sqlite3                # SQLite-Shell
```

In Git Bash vor Befehlen mit `-w /work` `MSYS_NO_PATHCONV=1` setzen.

## API-Modus (`DREAM_API_MODE` in `.env`)

- `mock` (Standard): FakeDreamClient im Backend, keine Simulation, keine Credits. Prompt-Marker `#fail`, `#error`,
  `#hang`, `#down` erzeugen Fehlerfälle.
- `sim`: Simulationsdienst, geskripteter Ablauf, keine Credits.
- `real`: Simulationsdienst mit Dream-1 – **kostet Credits**, nur nach Freigabe.

`GET /api/status` meldet Modus, Banner und Probleme (z. B. fehlender Key).

## Regeln

- Python-Befehle nur im Container, nie auf dem Host.
- Engine (`app/engine`) ohne FastAPI-Abhängigkeit und mit Tests.
- Kein Secret (`DREAM_API_KEY`) in Logs, Antworten oder Exceptions; `.env` nie lesen oder ausgeben.
- Tests laufen nie gegen die echte API (immer `DREAM_API_MODE=mock`, temporäre SQLite-Datei).
- SDK-Aufrufe nur wie in `docs/dream-sdk.md` belegt.
- Vor „fertig“ immer ruff + mypy + pytest.
