# Simulation-Dienst (`simulation`)

> **API v0.3 (21.11.2026).** Beide Modi laufen. `mock`: 15 pytest-Tests grün. `dream`: am 21.11. gegen die echte API
> geprüft. `pick-banana` mit `dreamlabs/dream-1-beta` zero-shot `succeeded` (Banane 8,3 cm angehoben, 7 Aufrufe,
> 34 s, ~0,01 $). Ein erster Lauf davor endete mit `timeout`. Einzelläufe sind keine Erfolgsquote.
> Live-Doku der laufenden API: http://localhost:3001/docs

Einer von vier Compose-Diensten des Dream Orchestrators (`frontend`, `backend`, `simulation`, `database`):

```
┌────────────┐  HTTP   ┌────────────┐  HTTP (diese API, :3001)  ┌──────────────────────────────┐
│  frontend  │ ──────► │  backend   │ ────────────────────────► │  simulation                   │
│  Editor,   │ ◄────── │  Ablauf-   │ ◄──────────────────────── │  MuJoCo-Szene (2× YAM)        │
│  Geräte    │         │  Engine    │    Status, Video, Bild     │  Dream-1-Steuerschleife       │
└────────────┘         └────────────┘                            │  Erfolgsprüfung, Datasets,    │
                                                                 │  Fine-Tuning (Dream Labs)     │
                                                                 └──────────────────────────────┘
```

**Warum es diesen Dienst braucht:** Die Dream-Labs-API hat **keinen** "Simulationslauf"-Endpunkt. Ein Aufruf (`get_action`) liefert 1,6 s Gelenkziele und meldet weder Erfolg noch Ende. Dieser Dienst übernimmt Simulation, Erfolgsprüfung, Zeitlimit und Stopp. Für das Backend ist ein Skill-Lauf damit genau das, was die Team-Anforderungen annehmen (A1): starten, Status abfragen, stoppen.

## Schnellstart

```sh
docker compose up -d --build simulation          # API auf http://localhost:3001 (Doku: /docs)
curl localhost:3001/health
curl -X POST localhost:3001/runs -H 'Content-Type: application/json' \
     -d '{"skill": "pick-banana", "mode": "mock"}'  # geskripteter Lauf, keine Credits
curl localhost:3001/runs/<run_id>                 # Status abfragen, bis er terminal ist
docker compose --profile gui up -d simulation-gui # optional: MuJoCo-Fenster im Browser, Port 6080
```

- **Testkonsole:** http://localhost:3001/demo. Sie wird vom Simulations-Dienst selbst ausgeliefert, ist eine Testseite und nicht das Produkt-Frontend: Lauf starten und stoppen, Livebild, Versuche, Video, Evaluationsergebnis mit Wilson-Intervall. Quelltext in `app/static/demo.html`, eine Referenz für die Frontend-Anbindung.
- **Prompt für das Frontend-Team:** [`FRONTEND_PROMPT.md`](FRONTEND_PROMPT.md).

- Tests (Modus `mock`, keine Credits): `docker compose run --rm -e DREAM_API_KEY= simulation bash -c "cd /app && python -m pytest -q -p no:cacheprovider tests"`
- Der API-Key kommt aus `.env` (`DREAM_API_KEY`). Keine Antwort und kein Log enthält ihn (N1). Ohne Key gibt es nur `mock`.
- Laufzeitdaten (Läufe, Videos, Datasets) liegen in `src/Simulation/data/` (vom Host eingebunden, von Git ignoriert).

## Verzeichnis

| Pfad | Inhalt |
|---|---|
| `app/main.py` | FastAPI-Routen, Pydantic-Modelle, Fehlerformat |
| `app/runner.py` | Lauf-Verwaltung: ein Lauf zur Zeit, Worker-Thread, Mock- und Dream-Schleife, Versuche, Budget, Stopp, Zeitlimit, Video, Livebild |
| `app/evals.py` | Serienläufe mit gepaarten Seeds, Wilson-Intervalle, Kosten pro Erfolg |
| `app/render.py` | Gemeinsamer Renderer für Läufe und Policy-Datasets (320×180) |
| `app/skills.py` | Skills und ihre Erfolgsprüfung in der Simulation |
| `app/training.py` | Datasets erzeugen, hochladen, Fine-Tune starten (Zustand in `data/training.json`) |
| `app/embodiment.py` | YAM-Embodiment (14 Werte, rechter Arm zuerst, 3 Kameras) |
| `app/config.py` | Pfade und Einstellungen (Umgebungsvariablen) |
| `tools/` | Kommandozeilen-Werkzeuge, siehe unten |
| `tests/test_api.py` | 15 API-Tests im Modus `mock` |
| `app/static/demo.html` | Testkonsole (`GET /demo`) |
| `Dockerfile` | Python 3.12, MuJoCo, Mesa-Rendering ohne GPU, noVNC. Das Dream-Labs-Beispiel `yam_mujoco` ist auf Commit `ba8ad98` gepinnt |

Die Szene stammt aus dem Dream-Labs-Beispiel `dream_library/examples/yam_mujoco`: zwei YAM-Arme, Kameras `top`, `left` und `right`, Banane, Apfel, Orange, Flasche, Schale und Teller. Der geskriptete Greifablauf (`mock_pickups.run_trial`) nutzt IK und arbeitet ohne API-Aufrufe.

## API

- Im Compose-Netz `http://simulation:3001`, vom Host `http://localhost:3001`. Port 8000 belegt das Backend.
- Alle Antworten sind JSON, Zeiten in UTC (ISO 8601), Dauer in Sekunden. Die Pydantic-Modelle in `app/main.py` sind die Quelle der Wahrheit, `GET /openapi.json` das maschinenlesbare Schema.

| Methode | Pfad | Zweck | Anforderung |
|---|---|---|---|
| `GET` | `/health` | Läuft der Dienst, ist der Key gesetzt, welche Modi, aktiver Lauf | N6 |
| `GET` | `/skills` | Skills mit Standard-Prompt und Erfolgsprüfung | Datenmodell Skill |
| `POST` | `/runs` | Skill-Lauf starten | F6 |
| `GET` | `/runs` | Letzte Läufe, neueste zuerst (`?limit=50`) | F14 |
| `GET` | `/runs/{run_id}` | Status, Erfolg, Dauer, Aufrufe, Kosten | F6, F14, F15 |
| `POST` | `/runs/{run_id}/stop` | Lauf abbrechen | F7 |
| `GET` | `/runs/{run_id}/video` | MP4 des Laufs (sobald terminal) | F16 |
| `GET` | `/frame.jpg` | Neuestes Kamerabild für eine Live-Kachel | F16 |
| `GET` | `/budget` | Budget-Grenze, bisherige und verbleibende Ausgaben (Schätzung) | F15 |
| `POST` | `/evals` | Serienläufe: Varianten (Prompt × Modell × Versuche) auf gleichen Testszenen | F15, Bewertung |
| `GET` | `/evals`, `/evals/{eval_id}` | Fortschritt, Erfolgsquoten mit Wilson-Intervall, Kosten pro Erfolg | |
| `POST` | `/evals/{eval_id}/stop` | Evaluation abbrechen | |
| `GET` / `POST` | `/datasets` | Datasets auflisten / Demos erzeugen | Training |
| `GET` | `/datasets/{name}` | Fortschritt, Validierung, Dream-Status | Training |
| `POST` | `/datasets/{name}/upload` | Zu Dream Labs hochladen (kostenlos) | Training |
| `POST` | `/finetune` | Fine-Tune starten (**kostet Credits**) | Training |
| `GET` | `/finetune`, `/finetune/{job_id}` | Jobs, Status, am Ende die Checkpoint-ID | Training |

### `GET /health`

```json
{ "status": "ok", "service": "simulation", "dream_key_set": true, "modes": ["mock", "dream"], "active_run_id": null, "version": "0.2.0" }
```

### `GET /skills`

| Skill | Prompt (Standard) | Erfolg (gemessen in der Simulation) | `mock` |
|---|---|---|---|
| `pick-banana` | pick up the banana | Banane ≥ 8 cm über Startposition | ja |
| `pick-apple` | pick up the apple | Apfel ≥ 8 cm über Startposition | ja |
| `banana-to-plate` | put the banana on the plate | Banane liegt ruhig ≤ 8 cm um die Tellermitte | nein |
| `apple-to-bowl` | put the apple into the bowl | Apfel liegt ruhig ≤ 7 cm um die Schalenmitte | nein |

Jeder Eintrag hat `name`, `description`, `default_prompt`, `fine_tuned_model`, `success_check` und `mock_available`, passend zur Tabelle `skills` in `src/Backend/models/schema.sql`.

### `POST /runs`

```json
{ "skill": "pick-banana", "prompt": "pick up the banana", "checkpoint": "dreamlabs/dream-1-beta", "mode": "dream", "timeout_s": 60, "seed": 42, "record_video": true }
```

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `skill` | string | ja | Skill-Name aus `GET /skills`. Bestimmt die Erfolgsprüfung |
| `prompt` | string | nein | Text für Dream-1. Fehlt er, gilt der Standard-Prompt. Ein leerer String gibt `400` (F4) |
| `checkpoint` | string | nein | `dreamlabs/dream-1-beta` (Standard), `dreamlabs/dream-1-beta-flash` oder ein Fine-Tune `dream-1-ft:<uid8>-<suffix>` |
| `mode` | `"dream"` \| `"mock"` | nein | `dream` (Standard) = echte API, kostet Credits. `mock` = geskripteter Greifablauf ohne API (N2). Die Oberfläche zeigt bei `mock` "SIMULIERTE API" an |
| `timeout_s` | 5–600 | nein | **Simulierte** Sekunden, Standard 60. Bei `dream` zählt die Zeit ab der ersten Modellantwort. Zusätzlich gilt eine harte Wanduhr-Grenze von 10 × `timeout_s` |
| `seed` | int | nein | Verschiebt Banane und Apfel reproduzierbar um bis zu ±3 cm. Fehlt er, wird gelost |
| `record_video` | bool | nein | MP4 aufzeichnen (Standard `true`) |
| `max_attempts` | 1–5 | nein | Versuche pro Lauf (Standard 1). Nach einem gescheiterten Versuch (Zeitlimit ohne Erfolg) setzt der Dienst neu an (F9) |
| `recovery` | `"rehome"` \| `"continue"` | nein | Vor dem nächsten Versuch die Arme in 1 s in die Grundstellung fahren (Standard) oder direkt weitermachen. Jeder Versuch ist eine neue Dream-Episode |
| `recovery_prompts` | string[] (≤ 4) | nein | Prompts für Versuch 2, 3, … Fehlt einer, gilt wieder `prompt` |

Antwort `202`: `{"run_id": "run_7f3a9c12", "status": "queued", "mode": "mock"}`. Es läuft **ein Lauf zur Zeit**. Ist einer aktiv, kommt `409` mit `{"error": "busy", "detail": "...", "active_run_id": "..."}`.

### `GET /runs/{run_id}`

```json
{
  "run_id": "run_7f3a9c12", "skill": "pick-banana", "mode": "mock", "prompt": "pick up the banana",
  "checkpoint": null, "seed": 1, "timeout_s": 60,
  "status": "succeeded", "success": true,
  "success_detail": { "lift_m": 0.145, "tcp_distance_m": 0.026, "release_drop_m": 0.154 },
  "created_at": "2026-11-21T19:40:02Z", "started_at": "2026-11-21T19:40:02Z", "finished_at": "2026-11-21T19:41:55Z",
  "duration_s": 30.2, "api_calls": 0, "cost_usd": 0.0, "cost_is_estimate": true,
  "error": null, "video_url": "/runs/run_7f3a9c12/video"
}
```

**Status-Lebenszyklus:**

```
queued ──► (warming) ──► running ──► finalizing ──┬──► succeeded   Erfolgsprüfung bestanden
                                                   ├──► failed      Ablauf beendet, Prüfung nicht bestanden (mock)
                                                   ├──► timeout     timeout_s überschritten, Ziel nicht erreicht
                                                   ├──► stopped     POST /stop
                                                   └──► error       API- oder Simulationsfehler, siehe "error"
```

- `warming` gibt es nur im Modus `dream`: Das Modell startet (`pool_warming`, bei Fine-Tunes laut Dream Labs bis zu 1 h). Die Zeit zählt **nicht** zu `timeout_s`.
- `finalizing`: Video und Protokoll werden geschrieben. Erst danach ist der Status terminal, `video_url` funktioniert also sofort.
- Im Modus `dream` endet der Lauf, sobald die Erfolgsprüfung besteht (`succeeded`), sonst nach `timeout_s` (`timeout`).
- `success` setzt **die Simulation**, nicht die API (Konzept-Regel).
- `attempts`: pro Versuch `{attempt, prompt, api_calls, sim_seconds, success}`, dazu `attempts_used`. `timeout_s` gilt pro Versuch.
- **Budget:** Vor jedem Dream-Aufruf prüft der Dienst die geschätzten Gesamtkosten gegen `SIM_BUDGET_USD` (Standard 10 $). Ist die Grenze erreicht, endet der Lauf mit `stopped` und `error: "budget_exhausted: …"`, und neue Dream-Läufe bekommen `402`. Dazu kommt die monatliche Budgetgrenze des Dream-Accounts (`over_cap`); sie erscheint als `error: "dream_over_cap: …"`.
- `cost_usd` = `api_calls` × Preis pro Aufruf (0,0014 $ Basis, 0,0028 $ Fine-Tune, laut Tutorial, an der Abrechnung noch zu prüfen). Bei `mock` immer 0.
- API- und Simulationsfehler landen in `error` und bringen den Dienst nicht zum Absturz (N4). Abgeschlossene Läufe liegen als `data/runs/<run_id>.json` und `.mp4` vor und überstehen einen Neustart.

### `POST /runs/{run_id}/stop`

Antwort `200`, Status zuerst `stopping`, dann `stopped`. Im Modus `dream` greift der Stopp nach dem laufenden Aufruf, also nach höchstens etwa 1,6 s plus Netzlaufzeit. Ein schon beendeter Lauf gibt `409`, ein unbekannter `404`.

### `GET /runs/{run_id}/video` und `GET /frame.jpg`

- `video`: `video/mp4` mit 5 fps, 320×270 (Draufsicht oben, beide Handgelenkkameras unten). Es sind dieselben Bilder, die Dream-1 sieht. `404`, solange der Lauf nicht terminal ist.
- `frame.jpg`: neueste Draufsicht (320×180) des laufenden oder letzten Laufs, sonst die Startszene (640×360). Für eine Live-Kachel reicht Polling alle 200–500 ms.

### Evaluation: `POST /evals`

Wie zuverlässig ist ein Skill mit welchem Prompt, welchem Modell und welcher Wiederholungsstrategie, und was kostet ein Erfolg? Dream-1 meldet selbst keinen Erfolg. Diese Antwort liefert nur die Simulation.

```json
{
  "skill": "pick-banana", "mode": "dream", "trials": 10, "seed_start": 0, "timeout_s": 30,
  "variants": [
    {"label": "beta-1x", "checkpoint": "dreamlabs/dream-1-beta"},
    {"label": "beta-3x", "checkpoint": "dreamlabs/dream-1-beta", "max_attempts": 3, "recovery": "rehome",
     "recovery_prompts": ["grasp the yellow banana and lift it up", "use the right gripper to pick up the banana"]},
    {"label": "flash-1x", "checkpoint": "dreamlabs/dream-1-beta-flash"}
  ]
}
```

- **Gepaart:** Alle Varianten laufen abwechselnd auf denselben Szenen (`seed_start` … `seed_start + trials - 1`).
- **Getrennte Seeds:** Testszenen haben Seeds < 1000, Trainingsdaten ≥ 1000. Keine Testszene kommt also im Training vor.
- `GET /evals/{id}` → `summary` pro Variante:

| Feld | Bedeutung |
|---|---|
| `n`, `successes`, `success_rate`, `ci95` | Erfolgsquote mit 95-%-Wilson-Intervall |
| `first_attempt_rate`, `first_attempt_ci95` | Quote nur des ersten Versuchs, aus denselben Läufen. Der Unterschied zu `success_rate` zeigt, was die Wiederholungen bringen |
| `api_calls`, `cost_usd`, `cost_per_success_usd` | Aufwand und Kosten pro erfolgreichem Lauf (Schätzung) |
| `mean_attempts_used`, `errors` | |

- Läuft gerade ein manueller Lauf, wartet die Evaluation, bis er fertig ist. Es läuft eine Evaluation zur Zeit (sonst `409`). Ist das Budget aufgebraucht, endet sie mit `status: "stopped"` und `error: "budget_exhausted"`.
- Alle Zahlen gelten nur in der Simulation und haben kleine Stichproben. Sie sagen nichts über echte Hardware.

### Datasets und Fine-Tuning

| Anfrage | Body | Antwort |
|---|---|---|
| `POST /datasets` | `{"name": "pick-v2", "episodes": 10, "randomize": true, "seed": 0, "backend": "local"}` | `202`, Datensatz-Eintrag mit `status: "generating"` |
| `GET /datasets/{name}` | – | `status` (`generating` → `validated` → `uploading` → `processing` → `processed`, oder `failed` mit `error`), dazu `sessions`, `episodes`, `frames`, `validation`, `dream_dataset_id` und `dream_status` |
| `POST /datasets/{name}/upload` | – | `202`. Registriert bei Bedarf das Embodiment `yam-sim`, lädt hoch und fragt den Status ab |
| `POST /finetune` | `{"dataset": "pick-v1", "suffix": "pick-v1", "steps": 500, "lr_schedule": "cosine", "confirm_cost_usd": 100}` | `202` mit `{"job_id": "ftj_…", "status": "queued", "price_usd": 100}` |
| `GET /finetune/{job_id}` | – | `status`, `progress` (`phase`, `step`, `total_steps`, `loss`) und `fine_tuned_model`, sobald fertig |

- `backend: "local"` erzeugt im Container, etwa 2,5 min pro Episode. `backend: "modal"` geht nur vom Host aus: `modal run src/Simulation/tools/modal_gen.py --name <name> --count <n>` (ein Container pro Episode, Minuten, ~0,003 $ pro Episode). Im Container antwortet die API dafür mit `501` und nennt den Befehl.
- Fehlgeschlagene Simulationsversuche werden nie exportiert.
- **Fine-Tune:** 0,20 $ pro Step. `confirm_cost_usd` muss genau dem Preis entsprechen, sonst `400`. Ein Job läuft nach dem Queuen bis zum Ende und lässt sich nicht abbrechen. Sobald `fine_tuned_model` gesetzt ist, kann es als `checkpoint` in `POST /runs` verwendet werden.

### Fehlerformat

`{"error": "<code>", "detail": "<Text>"}` mit diesen HTTP-Status:

| Status | Codes |
|---|---|
| `400` | `invalid_request`, `mock_unavailable`, `invalid_checkpoint`, `cost_not_confirmed` |
| `402` | `budget_exhausted` |
| `404` | `unknown_skill`, `unknown_run`, `no_video`, `unknown_dataset`, `unknown_eval` |
| `409` | `busy`, `already_finished`, `dataset_not_ready` |
| `501` | `modal_unavailable` |
| `502` | Fehler des Dream-Dienstes, z. B. `payment_required` |
| `503` | `no_api_key` |

## Werkzeuge (`tools/`)

Im Container mit `docker compose run --rm simulation python /app/tools/<script> ...` aufrufen. Arbeitsordner ist `/data` = `src/Simulation/data`.

| Skript | Zweck |
|---|---|
| `record_dataset.py --out datasets/<name> --episodes N --randomize --seed S` | Episoden als LeRobot v2.1 aufnehmen und lokal prüfen |
| `validate.py datasets/<name>` | Dataset-Ordner offline gegen `yam-sim` prüfen |
| `upload_dataset.py datasets/<name> <remote-name>` | Hochladen und auf `processed` warten |
| `modal_gen.py` (Host, `modal run`) | Generierung auf Modal, setzt nach Abbruch fort |
| `record_pickup.py banana` | Greifversuch als Video nach `data/pickup-banana.mp4` |
| `view_pickup.py`, `gui.sh` | Live-Ansicht für `simulation-gui` (noVNC) |

## Konfiguration

| Variable | Standard | Bedeutung |
|---|---|---|
| `DREAM_API_KEY` | – | Aus `.env`, nur im Container |
| `MUJOCO_GL` | `egl` | `osmesa` als Ausweichlösung |
| `SIM_DATA_DIR` | `/data` | Läufe, Videos, Datasets |
| `SIM_DEFAULT_TIMEOUT_S` / `SIM_DEFAULT_MOCK_TIMEOUT_S` | `60` / `60` | Standard-Zeitlimits (simulierte Sekunden) |
| `SIM_CORS_ORIGINS` | `http://localhost:8080,http://127.0.0.1:8080` | Origins, die die API direkt aus dem Browser aufrufen dürfen (Frontend) |
| `SIM_BUDGET_USD` | `10` | Harte Grenze für die geschätzten Dream-Kosten aller Läufe dieses Dienstes |
| `SIM_RENDER_SHADOWS` | `0` | `1` = Schatten und Spiegelungen in Läufen (wie in den Trainingsdaten), etwa 3× langsamer bei Software-Rendering |
| `SIM_MIN_CALL_INTERVAL_S` | `0.7` | Mindestabstand zwischen API-Aufrufen (Ratenlimit: 3 schnelle, danach 1 pro 0,7 s; N5) |
| `DREAM_YAM_EXAMPLE` | im Image gepinnt | Pfad zum Dream-Beispiel `yam_mujoco` |

## Bekannte Grenzen

- Die Simulation rendert per Software (Mesa, 2 CPUs in Colima): ~200 ms für drei 320×180-Bilder ohne Schatten. Ein Dream-Lauf läuft dadurch etwa 1–2× langsamer als Echtzeit. Mehr CPUs für Docker oder Colima beschleunigen das.
- Läufe rendern standardmäßig ohne Schatten. Die Trainingsdaten (`pick-v1`) wurden mit Schatten in 640×360 aufgenommen. Für einen fairen Vergleich mit einem Fine-Tune `SIM_RENDER_SHADOWS=1` setzen.
- Datasets haben 10 fps, weil Dream Labs nur 30, 15, 10 oder 5 fps annimmt und die Simulation mit 20 Hz steuert.
- Der geskriptete Ablauf greift nur Banane und Apfel. Bei der Orange findet die IK keine Lösung.
- Erfolgsquoten gelten nur in der Simulation. Laut Dream Labs lehrt Fine-Tuning vor allem den Roboterkörper, nicht eine Aufgabe. Ob ein Fine-Tune auf YAM die Quote verbessert, wird gemessen und nicht vorausgesetzt.

## Offene Punkte

1. Skills der finalen Demo (Kiste? Prüfstation?) und ob virtuelle Geräte (Lampe, Förderband, Lichtschranke) auch in der Szene erscheinen sollen.
2. Push statt Polling (Server-Sent Events für Status und Bild)?
3. Mehrere Läufe hintereinander in derselben Szene (Schleife "nächstes Objekt") statt einer frischen Szene pro Lauf.
