# Backend-API (Vertrag Frontend ↔ Backend)

Verbindlich ist das OpenAPI-Schema des laufenden Backends: `http://localhost:8000/docs` bzw. `/openapi.json`.
Diese Datei fasst es zusammen und listet Abweichungen vom ursprünglichen Vorschlag.

Alle Fach-Endpunkte liegen unter `/api`. Fehler: `{"error": "<code>", "detail": "<Text>", "details"?: ...}`.

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/health`, `/health/database`, `/api/health` | Lebenszeichen |
| GET | `/api/status` | `api_mode` (`mock`/`sim`/`real`), `banner` („SIMULIERTE API“/„ECHTE API“), `problems` |
| GET/POST | `/api/skills` | Skills (Felder wie Konzept §5) |
| GET/PUT/DELETE | `/api/skills/{id}` | |
| GET/POST | `/api/workflows` | Workflow mit `name` und `definition` (Blöcke + Pfeile) |
| GET/PUT | `/api/workflows/{id}` | |
| POST | `/api/workflows/validate` | Body = `definition`; Antwort `{valid, errors: [{block_id, message}], warnings, credits_estimate}` |
| POST | `/api/runs` | `{workflow_id}` → `202 {run_id, status, api_mode, credits_estimate}`; `422` mit Prüfergebnis, `409` wenn schon ein Lauf aktiv |
| GET | `/api/runs` | Letzte Läufe |
| GET | `/api/runs/{id}?after=<cursor>` | Status, `active_block_id`, `credits_used`, neue `log`-Einträge, `cursor` |
| POST | `/api/runs/{id}/stop` \| `pause` \| `resume` \| `step` | Steuerung (F7, F8) |
| GET | `/api/devices` | Geräteleiste |
| PUT | `/api/devices/{id}` | `{value}`; nur Sensoren (`409` bei Aktoren) |
| GET/POST | `/api/training/datasets`, `GET /api/training/datasets/{name}`, `POST …/{name}/upload` | Durchgriff auf den Simulationsdienst |
| GET/POST | `/api/training/finetune`, `GET /api/training/finetune/{job_id}` | Fine-Tuning (kostet Credits, `confirm_cost_usd`) |
| GET | `/api/simulation/skills` | Skills des Simulationsdienstes (gültige Skill-Namen) |
| GET | `/api/simulation/runs/{run_id}` | Details eines Simulationslaufs (`success_detail`, `duration_s`, `cost_usd`); `run_…` steht im Protokoll |
| GET | `/api/simulation/runs/{run_id}/video`, `/api/simulation/frame.jpg` | MP4 nach Laufende, Livebild (F16) |

## Workflow-JSON

```json
{
  "blocks": [
    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
    {"id": "grab", "type": "prompt", "params": {"skill_id": 1, "prompt": "pick up the banana", "sim_timeout_s": 60, "timeout_s": 600, "retries": 1}},
    {"id": "wait", "type": "wait_sensor", "params": {"device": "lichtschranke", "operator": "==", "value": true, "timeout_s": 30}},
    {"id": "lamp", "type": "set_actuator", "params": {"device": "lampe", "value": true}},
    {"id": "pause", "type": "wait_time", "params": {"seconds": 2}},
    {"id": "more", "type": "condition", "params": {"device": "schalter", "operator": "==", "value": true}},
    {"id": "end", "type": "end"}
  ],
  "edges": [{"source": "start", "target": "grab", "port": "next"}, {"source": "more", "target": "grab", "port": "true"}]
}
```

- Blocktypen: `start`, `prompt`, `wait_sensor`, `set_actuator`, `wait_time`, `condition`, `end`.
- Ausgänge (`port`): `next`; `condition` hat `true` („wahr“) und `false` („sonst“); `prompt`, `wait_sensor`,
  `set_actuator` haben optional `error` (Fehlerpfad). Ohne Fehlerpfad bricht ein Fehler den Lauf ab.
- Rückkanten (Schleifen) sind erlaubt; ein Lauf endet nach `MAX_STEPS_PER_RUN` Blöcken (Standard 1000).
- Operatoren: `==`, `!=`, `>`, `>=`, `<`, `<=`.

## Hinweise fürs Frontend

- Fortschritt per Polling von `GET /api/runs/{id}?after=<cursor>` (z. B. alle 500 ms); `cursor` der Antwort beim
  nächsten Mal mitschicken. `active_block_id` hervorheben (F5).
- Banner aus `GET /api/status`: `banner` anzeigen, `problems` als Warnung.
- Geräte-IDs (virtuell, nach Neustart wieder Startwert): `lichtschranke`, `schalter`, `taster`, `pruefwert` (Sensoren),
  `lampe`, `foerderband` (Aktoren).
- Im Modus `sim`/`real` muss der Skill-`name` ein Skill des Simulationsdienstes sein (`pick-banana`, `pick-apple`,
  `banana-to-plate`, `apple-to-bowl`).

## Abweichungen vom ursprünglichen Vorschlag

1. `DREAM_API_MODE` hat drei Werte statt zwei: `sim` = Simulationsdienst mit geskriptetem Ablauf (echte Szene, keine
   Credits). `mock` (Standard) braucht keinen Simulationsdienst.
2. Der „echte“ Dream-Client spricht mit dem Simulationsdienst statt direkt mit der SDK, weil die SDK keinen Lauf mit
   Status kennt (siehe `src/Backend/docs/dream-sdk.md`).
3. Zusätzlich: `GET /api/runs`, `/api/health`, `/api/training/...` und `/api/simulation/...`.
4. Workflows haben (noch) kein `DELETE`.
5. Prompt-Block: `sim_timeout_s` (5–600 simulierte Sekunden, Standard 60) ist das erfolgsbewusste Zeitlimit des
   Simulationsdienstes; `timeout_s` (Standard 600) ist nur die harte Wanduhr-Grenze im Backend.
