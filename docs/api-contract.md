# API-Vertrag Frontend ↔ Backend (Vorschlag v1)

Status: **Vorschlag**, mit dem Backend abzustimmen. Maßgeblich im Code ist [`src/Frontend/src/api/contract.ts`](../src/Frontend/src/api/contract.ts) (zod-Schemas). Das Frontend prüft jede Antwort gegen diese Schemas und zeigt Abweichungen als Fehler an.

## Grundsätze

- Das Frontend ruft nur `/api/...` auf. Vite (Entwicklung) und nginx (Produktion) leiten an `http://backend:8000/...` weiter und **entfernen dabei das Präfix `/api`**. Das Backend implementiert also `GET /skills`, `GET /health` usw.
- JSON in beide Richtungen, `Content-Type: application/json`.
- Fehler: HTTP-Status ≥ 400 mit dem Body `{ "error": "Meldung für Menschen", "details": <optional> }`. Das Frontend zeigt `error` an.
- Zeitstempel: Bei Skills kommt `created_at` so, wie SQLite es liefert (`2026-11-21 17:30:00`), alle anderen Zeitstempel als ISO 8601 (`2026-11-21T17:30:00Z`).
- **Keine Secrets im Frontend (N1).** Der Dream-Labs-API-Key bleibt im Backend (`.env`).
- **Die Engine läuft im Backend (N3).** Das Frontend startet und stoppt Läufe nur und fragt ihren Status ab.

## Endpunkte

| Methode | Pfad (Frontend) | Request-Body | Antwort | Prio |
|---|---|---|---|---|
| GET | `/api/health` | – | `Health` | vorhanden |
| GET | `/api/skills` | – | `Skill[]` | M |
| POST | `/api/skills` | `SkillInput` | `Skill` (201) | M |
| PUT | `/api/skills/{id}` | `SkillInput` | `Skill` | M, **zusätzlich vorgeschlagen** fürs Bearbeiten |
| GET | `/api/workflows` | – | `WorkflowSummary[]` | M |
| GET | `/api/workflows/{id}` | – | `Workflow` | M |
| POST | `/api/workflows` | `WorkflowDocument` | `Workflow` (201) | M |
| PUT | `/api/workflows/{id}` | `WorkflowDocument` | `Workflow` | M |
| POST | `/api/runs` | `StartRunRequest` | `Run` (201) | M |
| GET | `/api/runs/{id}` | – | `Run` | M, wird gepollt (Intervall einstellbar, N5) |
| POST | `/api/runs/{id}/stop` | – | `Run` | M (F7) |
| POST | `/api/runs/{id}/pause` | – | `Run` | S (F8) |
| POST | `/api/runs/{id}/resume` | – | `Run` | S (F8) |
| POST | `/api/runs/{id}/step` | – | `Run` | S (F8), Einzelschritt aus der Pause |
| GET | `/api/devices` | – | `Device[]` | M |
| PUT | `/api/devices/{id}` | `{ "value": boolean \| number }` | `Device` | M, nur Sensoren werden aus der Oberfläche gesetzt |

## Datenmodelle

### Health
```json
{ "status": "ok", "service": "backend" }
```

### Skill (Felder exakt aus `src/Backend/models/schema.sql`)
| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | integer | |
| `name` | string | `UNIQUE`; bei Duplikat HTTP 409 |
| `description` | string | |
| `created_at` | string | SQLite `CURRENT_TIMESTAMP` |
| `status` | string | Standard `Entwurf`. Die Oberfläche schlägt `Entwurf`, `Training`, `Bereit` und `Fehler` vor (Konzept §5). Das Schema erlaubt beliebigen Text. |
| `fine_tuned_model` | string \| null | |

`SkillInput`: `name` (Pflicht, nicht leer), `description`, optional `status` und `fine_tuned_model`.

### WorkflowDocument (identisch mit dem JSON-Export, F3)
```json
{
  "schemaVersion": 1,
  "name": "Pick-and-Place",
  "nodes": [ { "id": "n1", "type": "start", "position": { "x": 0, "y": 0 }, "data": {} } ],
  "edges": [ { "id": "e1", "source": "n1", "target": "n2", "sourceHandle": "out" } ]
}
```
`Workflow` = `WorkflowDocument` + `id` (string) + `updated_at` (ISO). `WorkflowSummary` = `id`, `name`, `updated_at`.

**Blocktypen und `data`** (alle haben zusätzlich ein optionales `label`):

| `type` | `data` | Ausgänge (`sourceHandle`) |
|---|---|---|
| `start` | – | `out` |
| `prompt` | `prompt` (string), `skillId` (int \| null = Basismodell), `timeoutS` (> 0, pro Versuch), `retries` (≥ 0) | `out` = Erfolg, `error` = nach allen Versuchen fehlgeschlagen oder abgelaufen |
| `waitSensor` | `deviceId`, `operator`, `value`, `timeoutS` (> 0 \| null) | `out` = erfüllt, `error` = Zeitlimit |
| `setActuator` | `deviceId`, `value` | `out` |
| `wait` | `seconds` (> 0) | `out` |
| `condition` | `deviceId`, `operator`, `value` | `true` = Pfad A „wahr“, `false` = Pfad B „sonst“ |
| `end` | – | – |

`operator`: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`. `value`: boolean oder number. Kanten zurück zu früheren Blöcken (Schleifen) sind erlaubt.

### StartRunRequest
```json
{ "workflowId": "wf-1 oder null", "workflow": { "...": "WorkflowDocument (Momentaufnahme)" } }
```
Das Backend führt die mitgeschickte Momentaufnahme aus. So lassen sich auch ungespeicherte Änderungen starten.

### Run
| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | string | |
| `workflowId` | string \| null | |
| `status` | `queued` \| `running` \| `paused` \| `succeeded` \| `failed` \| `stopped` | Das Frontend pollt, bis `succeeded`, `failed` oder `stopped` erreicht ist. |
| `activeNodeId` | string \| null | Block, der gerade ausgeführt wird (F5); `null`, sobald der Lauf beendet ist |
| `startedAt`, `finishedAt` | ISO \| null | |
| `error` | string \| null | Grund bei `failed` |
| `credits.used` | number | verbrauchte Dream-Labs-Aufrufe (F15) |
| `log` | `RunLogEntry[]` | vollständiges Protokoll (F14) |

`RunLogEntry`: `ts` (ISO), `level` (`info`, `warn` oder `error`), `nodeId` (string \| null), `apiStatus` (string \| null, z. B. `running`, `succeeded`, `timeout`, `stopped`), `durationMs` (number \| null), `message` (string).

### Device (F10/F11)
| Feld | Typ | Anmerkung |
|---|---|---|
| `id` | string | z. B. `lichtschranke` |
| `name` | string | Anzeigename |
| `kind` | `sensor` \| `actuator` | |
| `type` | `switch` \| `button` \| `number` \| `lamp` \| `conveyor` | |
| `adapter` | string | Im Hackathon immer `virtual`; später z. B. `mqtt` |
| `value` | boolean \| number | |
| `unit`, `min`, `max` | optional | für `number` |

## Testmodus (N2)

Mit `VITE_API_MODE=mock` verwendet das Frontend statt des Backends einen Stellvertreter im Browser (`src/Frontend/src/api/mockClient.ts`). Er hat dieselbe Schnittstelle und spielt Läufe nach:
- Ein Prompt dauert 3 s.
- Sensoren sind die virtuellen Geräte.
- Zeitlimits und Wiederholungen werden berücksichtigt.

Die Oberfläche zeigt dabei dauerhaft das Banner **„SIMULIERTE API“**. Ist `VITE_API_MODE` nicht gesetzt, gilt `real`.

## Was das Backend dafür braucht (Notizen für euch)

1. Die Endpunkte oben **ohne** `/api`-Präfix, Fehler im Format `{ "error": ... }`
2. Eine Tabelle oder einen Speicher für Workflows, zum Beispiel `workflows(id TEXT PRIMARY KEY, name TEXT, document TEXT /* JSON */, updated_at TEXT)`. Das Schema gehört euch, ich habe es nicht angefasst.
3. Die Ablauf-Engine (Zustandsautomat) mit denselben Regeln wie oben:
   - Ausgänge `out`, `error`, `true` und `false`
   - Zeitlimit pro Versuch, danach Wiederholungen
   - Ein Block ohne passenden Ausgang beendet den Lauf mit `failed`.
   - Schutz vor Endlosschleifen ohne Wartezeit
4. Virtuelle Geräte: Lichtschranke, Taster „Start“, Weitere Objekte, Füllstand Kiste, Signallampe grün und rot, Förderband. Die IDs stehen in `DEFAULT_MOCK_DEVICES` in `mockClient.ts`.
5. `POST /runs/{id}/stop` muss auch den laufenden Dream-Labs-Simulationslauf abbrechen (F7).
6. `credits.used` pro Lauf mitzählen (F15).
