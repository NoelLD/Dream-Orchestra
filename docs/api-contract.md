# API-Vertrag Frontend ↔ Backend

Verbindlich ist das OpenAPI-Schema des laufenden Backends: `http://localhost:8000/docs` bzw. `/openapi.json`.
Diese Datei fasst es zusammen und beschreibt, wie das Frontend es nutzt.

- Alle Fach-Endpunkte liegen unter `/api`. Vite-Proxy (Dev) und nginx (Prod) reichen `/api/...` **unverändert** an
  `http://backend:8000/api/...` weiter.
- Fehler: `{"error": "<code>", "detail": "<Text>", "details"?: ...}` – auch für Validierungsfehler der Anfrage (422).
- Das Frontend arbeitet intern im Editor-Format (`src/Frontend/src/api/contract.ts`); `realClient.ts` übersetzt über
  `backendMapping.ts` (getestet, inkl. verlustfreiem Roundtrip des Beispiel-Workflows).

## Endpunkte

| Methode | Pfad | Zweck | Frontend (`ApiClient`) |
|---|---|---|---|
| GET | `/health`, `/health/database`, `/api/health` | Lebenszeichen | `health()` |
| GET | `/api/status` | `api_mode` (`mock`/`sim`/`real`), `banner`, `problems` | `status()` → Badge, Banner „SIMULIERTE API“ |
| GET/POST | `/api/skills` | Skills (Felder wie Konzept §5; `description` darf leer sein) | `listSkills()`, `createSkill()` |
| GET/PUT/DELETE | `/api/skills/{id}` | | `updateSkill()` |
| POST | `/api/skills/import-simulation` | fehlende Skills des Simulationsdienstes anlegen | `importSimulationSkills()` → Knopf „Aus Simulation übernehmen“ |
| GET/POST | `/api/workflows` | `{name, definition}`; Liste zuletzt geänderte zuerst | `listWorkflows()`, `createWorkflow()` → Dialog „Öffnen …“, „Speichern“, „Als Kopie“ |
| GET/PUT/DELETE | `/api/workflows/{id}` | Laden, Speichern, Löschen (Läufe bleiben, ohne Zuordnung) | `getWorkflow()`, `updateWorkflow()`, `deleteWorkflow()` |
| POST | `/api/workflows/validate` | Body = `definition`; `{valid, errors: [{block_id, message}], warnings, credits_estimate}` | `validateWorkflow()` → „Prüfen“ (2. Stufe) |
| POST | `/api/runs` | `{workflow_id?, definition?}` → `202` mit vollständigem Lauf; `422` mit Prüfergebnis in `details`; `409` wenn schon ein Lauf aktiv | `startRun()`; 422-Fehler werden am Block markiert |
| GET | `/api/runs` | letzte Läufe | – |
| GET | `/api/runs/{id}?after=<cursor>` | Status, `active_block_id`, `credits_used`, `log` (ab Cursor), `cursor` | `getRun()` (Polling, ganzes Protokoll) |
| POST | `/api/runs/{id}/stop` \| `pause` \| `resume` \| `step` | Steuerung (F7, F8) | `stopRun()`, `pauseRun()`, `resumeRun()`, `stepRun()` |
| GET | `/api/devices` | Geräte mit `protocol`, `config` (ohne Passwort, dafür `password_set`), `simulated`, Wert; `unit`, `min`, `max` bei Zahlenwerten; `available`/`unavailable_reason` (Wert gilt gerade nicht, z. B. Zelle getrennt); `read_only` (Wert meldet die Zelle, `PUT …/value` → 409) | `listDevices()` |
| POST | `/api/devices` | `{name, type, config, unit?, min?, max?}` → `201`; ID wird aus dem Namen gebildet | `createDevice()` → Ansicht „Geräte“ |
| PUT | `/api/devices/{id}` | wie POST; leeres Passwort = unverändert; `409` bei Wechsel Sensor↔Aktor, solange ein gespeicherter Workflow das Gerät nutzt | `updateDevice()` |
| DELETE | `/api/devices/{id}` | `204`; `409` mit `details: [{id, name}]` der Workflows, die das Gerät nutzen | `deleteDevice()` |
| PUT | `/api/devices/{id}/value` | `{value}`; nur Sensoren (`409` bei Aktoren) | `setDevice()` |
| GET/POST | `/api/training/datasets`, `GET …/{name}`, `POST …/{name}/upload` | Durchgriff auf den Simulationsdienst | – |
| GET/POST | `/api/training/finetune`, `GET …/{job_id}` | Fine-Tuning (kostet Credits, `confirm_cost_usd`) | – |
| GET | `/api/simulation/skills`, `/api/simulation/runs/{run_id}` | Skills und Laufdetails des Simulationsdienstes | – |
| GET | `/api/simulation/runs/{run_id}/video`, `/api/simulation/frame.jpg` | MP4 nach Laufende, Livebild (F16) | – |

## Workflow: Editor-Format ↔ Backend-Format

| Editor (`nodes`, `data`) | Backend (`blocks`, `params`) |
|---|---|
| `start`, `prompt`, `waitSensor`, `setActuator`, `wait`, `condition`, `end` | `start`, `prompt`, `wait_sensor`, `set_actuator`, `wait_time`, `condition`, `end` |
| `data.deviceId` | `params.device` |
| `data.skillId` (`null` = Basismodell) | `params.skill_id` (`null` nur im Modus `mock`; in `sim`/`real` Pflicht) |
| `data.timeoutS` (Prompt) | `params.timeout_s` (Wanduhr-Grenze pro Versuch) |
| `data.timeoutS` (Sensor, `null` = ohne Limit) | `params.timeout_s` (`null` = ohne Limit) |
| `data.operator` `eq neq gt gte lt lte` | `params.operator` `== != > >= < <=` |
| `data.label` | `params.label` (wird gespeichert, von der Engine ignoriert) |
| Kante `sourceHandle` `out error true false` | Kante `port` `next error true false` (`id` bleibt erhalten) |
| `id` (String) | `id` (Zahl) |

Weitere Backend-Parameter am Prompt-Block (noch nicht im Editor): `retries` (F9), `checkpoint`,
`sim_timeout_s` (5–600 simulierte Sekunden, erfolgsbewusstes Zeitlimit des Simulationsdienstes).

Beispiel (Backend-Format):

```json
{
  "blocks": [
    {"id": "start", "type": "start", "position": {"x": 0, "y": 20}},
    {"id": "greifen", "type": "prompt", "params": {"label": "Greifen", "skill_id": 1, "prompt": "pick up the banana", "timeout_s": 600, "retries": 1}},
    {"id": "sensor", "type": "wait_sensor", "params": {"device": "lichtschranke", "operator": "==", "value": true, "timeout_s": 30}},
    {"id": "weiter", "type": "condition", "params": {"device": "weitere-objekte", "operator": "==", "value": true}},
    {"id": "ende", "type": "end"}
  ],
  "edges": [
    {"id": "e1", "source": "start", "target": "greifen", "port": "next"},
    {"id": "e2", "source": "weiter", "target": "greifen", "port": "true"}
  ]
}
```

- Rückkanten (Schleifen) sind erlaubt; ein Lauf endet nach `MAX_STEPS_PER_RUN` Blöcken (Standard 1000).
- Ohne Fehlerpfad (`error`) bricht ein Blockfehler den Lauf ab.

## Läufe

- Läufe im Frontend: `id`/`workflowId` als String, `activeNodeId` ← `active_block_id`, `credits.used` ← `credits_used`,
  Protokoll `ts` ← `timestamp`, `level` `warning` → `warn`, `nodeId` ← `block_id`, `apiStatus`, `durationMs`.
- Status: `running`, `paused`, `succeeded`, `failed`, `stopped`. Es läuft ein Lauf zur Zeit.

## Geräte

Stammdaten liegen in der Tabelle `devices` (SQLite), Werte werden simuliert und stehen nach einem Neustart wieder auf
ihrem Startwert. `config` je Protokoll:

- `virtual`: `{protocol}`
- `mqtt`: `{protocol, host, port=1883, topic, qos=0, username?, password?, tls=false, payload_path?}`
- `opcua`: `{protocol, endpoint (opc.tcp://…), node_id, security_mode=None|Sign|SignAndEncrypt, username?, password?}`

Startbestand (Protokoll `virtual`, wird nur in eine leere Tabelle geschrieben):

| ID | Typ | Art |
|---|---|---|
| `lichtschranke` | switch | Sensor |
| `taster` | button | Sensor |
| `weitere-objekte` | switch (Start: an) | Sensor |
| `fuellstand` | number (0–10 Stk) | Sensor |
| `lampe`, `lampe-rot` | lamp | Aktor |
| `foerderband` | conveyor | Aktor |

## API-Modi

- Frontend `VITE_API_MODE`: `mock` = Backend im Browser nachgespielt, `real` = echtes Backend über `/api`.
- Backend `DREAM_API_MODE`: `mock` (Stellvertreter, Standard), `sim` (Simulationsdienst, geskriptet, keine Credits),
  `real` (Dream-1, kostet Credits). Im Frontend-Modus `real` zeigen Badge und Banner den Backend-Modus.
- Im Modus `sim`/`real` muss der Skill-Name ein Skill des Simulationsdienstes sein (`pick-banana`, `pick-apple`,
  `banana-to-plate`, `apple-to-bowl`) – am einfachsten über „Aus Simulation übernehmen“.
