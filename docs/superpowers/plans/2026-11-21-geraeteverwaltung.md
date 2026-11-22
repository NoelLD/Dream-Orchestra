# Geräteverwaltung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sensoren/Aktoren mit Protokoll (virtual, MQTT, OPC UA) dauerhaft verwalten; die Geräteleiste zeigt nur die Geräte des offenen Workflows; Werte bleiben simuliert.

**Architecture:** Neue SQLite-Tabelle `devices` + Repo-Funktionen. `DeviceRegistry` (ersetzt `VirtualAdapter`) hält Stammdaten im Speicher (write-through in die DB) und simulierte Werte; erfüllt weiter das `DeviceAdapter`-Protokoll für Engine und Prüfung. CRUD-API unter `/api/devices`, Frontend bekommt Tab „Geräte“ (Muster `SkillsView`) und filtert `DeviceBar` nach den `deviceId`s im Editor-Store.

**Tech Stack:** FastAPI, Pydantic 2, sqlite3, pytest · React 19, TanStack Query 5, zustand 5, zod 4, shadcn/ui, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-21-geraeteverwaltung-design.md`

## Global Constraints

- Alle Befehle nur im Container (Backend: `docker compose run --rm --no-deps backend …`; Frontend: `docker compose --profile dev exec frontend-dev …`). Nichts auf dem Host installieren. Keine neuen Abhängigkeiten.
- `schema.sql`: bestehende Tabellen nicht ändern, neue nur mit `CREATE TABLE IF NOT EXISTS`.
- Die sieben bisherigen Geräte behalten IDs, Namen, Typen: `lichtschranke`, `taster`, `weitere-objekte`, `fuellstand` (Stk, 0–10), `lampe`, `lampe-rot`, `foerderband`; Protokoll `virtual`.
- Passwort (`config.password`) erscheint nie in API-Antworten oder Logs; stattdessen `config.password_set: bool`. Leeres/fehlendes Passwort beim Bearbeiten = unverändert.
- Aktoren in der Geräteleiste nur Anzeige; `PUT /devices/{id}/value` auf Aktor → 409.
- Kein echter MQTT/OPC-UA-Verkehr; jedes Gerät `simulated: true`.
- Mock-Banner/Badge im Frontend nicht verändern. UI-Texte deutsch.
- Nur diese Aufgabe darf Backend und Frontend zugleich ändern; außerdem `docs/api-contract.md`.
- Vor „fertig“: Backend ruff + ruff format --check + mypy + pytest; Frontend `pnpm check`; Screenshot bei 1280 px.

## Review Focus

- Gerät, das nur in einem **ungespeicherten** Editor-Stand verwendet wird, ist löschbar; Blöcke zeigen danach „Gerät existiert nicht“ in der Prüfung (kein Absturz in PropertiesPanel/DeviceBar). → Test in Task 5 (DeviceBar ignoriert unbekannte IDs).
- Name nur aus Sonderzeichen/Umlauten („Ü“, „###“) → ID trotzdem gültig und eindeutig (`geraet`, `geraet-2`). → Test in Task 1.
- Bearbeiten ohne Passwort behält das gespeicherte Passwort; Protokollwechsel MQTT → virtual verwirft es. → Test in Task 2.
- Typwechsel `number` → `switch` setzt Wert auf `false` und entfernt unit/min/max; laufende Prüfung sieht neue Art sofort. → Test in Task 2.
- Neustart des Backends: angelegte Geräte sind wieder da, gelöschte Startgeräte kommen nicht zurück. → Test in Task 2.

---

### Task 1: Backend – Tabelle, Konfig-Modelle, Repo

**Files:**
- Modify: `src/Backend/models/schema.sql` (Tabelle `devices` laut Spec, Spalten `id, name, type, protocol, config, unit, min, max, created_at, updated_at`)
- Create: `src/Backend/app/schemas/devices.py`
- Modify: `src/Backend/app/db/repo.py` (Abschnitt `# --- Geräte ---`)
- Test: `src/Backend/tests/test_devices_repo.py`

**Interfaces:**
- Produces (`app/schemas/devices.py`):
  - `class Protocol(StrEnum)`: `VIRTUAL="virtual"`, `MQTT="mqtt"`, `OPCUA="opcua"`
  - `VirtualConfig(protocol: Literal["virtual"])`
  - `MqttConfig(protocol: Literal["mqtt"], host: str (min 1), port: int = 1883 (1–65535), topic: str (min 1), qos: int = 0 (0–2), username: str|None, password: str|None, tls: bool = False, payload_path: str|None)`
  - `OpcUaConfig(protocol: Literal["opcua"], endpoint: str (muss mit "opc.tcp://" beginnen), node_id: str (min 1), security_mode: Literal["None","Sign","SignAndEncrypt"] = "None", username: str|None, password: str|None)`
  - `DeviceConfig = Annotated[VirtualConfig | MqttConfig | OpcUaConfig, Field(discriminator="protocol")]`
  - `DeviceIn(name: str (strip, min 1), type: DeviceType, config: DeviceConfig, unit: str|None, min: float|None, max: float|None)`; Validator: `min <= max`; bei `type != number` werden unit/min/max auf `None` gesetzt.
  - `def public_config(config: dict) -> dict` – entfernt `password`, setzt `password_set`.
  - `def slugify(name: str) -> str` – ä→ae, ö→oe, ü→ue, ß→ss, lower, Nicht-[a-z0-9] → `-`, Ränder trimmen, leer → `"geraet"`.
- Produces (`repo.py`), Rückgabe dicts mit `config` als dict (JSON geparst):
  - `list_devices(db) -> list[dict]`, `get_device(db, device_id: str) -> dict` (404)
  - `create_device(db, data: dict) -> dict` – erzeugt ID via `slugify` + Suffix `-2`, `-3` … bei Kollision
  - `update_device(db, device_id: str, data: dict) -> dict` (404)
  - `delete_device(db, device_id: str) -> None` (404)
  - `seed_devices(db, devices: Iterable[dict]) -> None` – fügt nur ein, wenn Tabelle leer
  - `workflows_using_device(db, device_id: str) -> list[dict]` – `[{id, name}]` aller gespeicherten Workflows mit Block `type in {"wait_sensor","condition","set_actuator"}` und `params.device == device_id`

- [ ] **Step 1: Failing tests** in `test_devices_repo.py` (Fixture: `Database(tmp_path/"t.sqlite3")` + `init_schema(Path("models/schema.sql"))`):
  - `test_slugify`: `slugify("Füllstand Kiste") == "fuellstand-kiste"`, `slugify("###") == "geraet"`, `slugify("  Ü ") == "ue"`
  - `test_create_device_unique_ids`: zwei Mal Name „Band“ → IDs `band`, `band-2`
  - `test_config_validation`: `DeviceIn` mit MQTT ohne topic → ValidationError; OPC UA mit endpoint `http://x` → ValidationError; `min=5,max=1` → ValidationError; `type="switch", unit="x"` → `unit is None`
  - `test_public_config_hides_password`: `public_config({"protocol":"mqtt","password":"geheim",...})` enthält kein `password`, `password_set is True`
  - `test_seed_only_when_empty`: seed 2 Geräte, eines löschen, erneut seed → 1 Gerät
  - `test_workflows_using_device`: Workflow mit `set_actuator` auf `lampe` → `[{"id":…, "name":…}]`; für `taster` → `[]`
- [ ] **Step 2:** `docker compose run --rm --no-deps backend python -m pytest tests/test_devices_repo.py -q` → FAIL (ImportError)
- [ ] **Step 3:** Implementieren wie in Interfaces.
- [ ] **Step 4:** Gleicher Befehl → PASS.
- [ ] **Step 5:** Commit `feat(backend): Gerätetabelle, Protokoll-Einstellungen und Repo`

### Task 2: Backend – DeviceRegistry, Start, API

**Files:**
- Modify: `src/Backend/app/devices/adapter.py` (`VirtualAdapter` → `DeviceRegistry`; `DEFAULT_DEVICES`, `coerce`, `set_by_user`, `DeviceType`, `DeviceKind` bleiben)
- Modify: `src/Backend/app/main.py`, `src/Backend/app/api/deps.py`, `src/Backend/app/api/devices.py`, `src/Backend/app/schemas/models.py`
- Modify: `src/Backend/tests/test_api.py` (bisherige `client.put("/api/devices/<id>", …)` → `/api/devices/<id>/value`)
- Modify: `docs/api-contract.md` (Gerätetabelle + Abschnitt „Geräte“), `src/Backend/CLAUDE.md` (Strukturzeile devices)
- Test: `src/Backend/tests/test_devices_api.py`

**Interfaces:**
- Consumes: Task 1 (`repo.*_device*`, `DeviceIn`, `public_config`).
- Produces:
  - `Device` dataclass erhält `protocol: str = "virtual"`, `config: dict = {}` (field default_factory).
  - `class DeviceRegistry` (erfüllt `DeviceAdapter`): `__init__(db: Database)`, `load() -> None` (seed aus `DEFAULT_DEVICES` mit `{"protocol":"virtual"}`, dann alle laden; Werte: bool-Typen `False`, number `min or 0.0`; Startwerte der Defaults wie bisher, z. B. `weitere-objekte=True`), `list()`, `get(id)`, `set(id, value)`, `create(data: DeviceIn) -> Device`, `update(id, data: DeviceIn) -> Device`, `delete(id) -> None`.
  - `update`: Passwort leer/fehlend + gleiches Protokoll → altes Passwort übernehmen; Wechsel in andere Art bei `workflows_using_device` ≠ [] → `ConflictError`; Typwechsel → Wert zurücksetzen.
  - `delete`: verwendet → `ConflictError("Gerät '<id>' wird in Workflows verwendet", details=[{id, name}])`.
  - `Services.devices: DeviceRegistry`; `create_app`-Lifespan ruft nach `init_schema` `services.devices.load()`.
  - `DeviceOut` + `protocol: str`, `config: dict[str, Any]` (öffentlich), `simulated: bool = True`; `adapter` bleibt `"virtual"`.
  - Routen: `GET /devices`, `POST /devices` (201), `PUT /devices/{id}` (Body `DeviceIn`), `DELETE /devices/{id}` (204), `PUT /devices/{id}/value` (Body `DeviceValue`, `set_by_user`).

- [ ] **Step 1: Failing tests** in `test_devices_api.py` (Fixtures aus `conftest.py`):
  - `test_create_mqtt_device_hides_password`: POST `{name:"Band 2", type:"conveyor", config:{protocol:"mqtt", host:"broker", topic:"halle/band2", password:"geheim"}}` → 201, `id=="band-2"`, `kind=="actuator"`, `simulated is True`, `"geheim" not in response.text`, `config.password_set is True`
  - `test_update_keeps_password_and_switch_protocol_drops_it`: PUT ohne password → `password_set` bleibt True; PUT mit `{protocol:"virtual"}` → `password_set` fehlt/False
  - `test_type_change_resets_value`: `fuellstand` auf 4 setzen, PUT `type:"switch"` → `value is False`, `unit is None`
  - `test_delete_blocked_when_used`: Workflow mit `wait_sensor` auf `lichtschranke` speichern → DELETE 409, `body["details"][0]["name"]` = Workflowname; ohne Verwendung (`taster`) → 204, danach GET ohne `taster`
  - `test_kind_change_blocked_when_used`: `lampe` in Workflow, PUT `type:"switch"` → 409
  - `test_invalid_opcua_endpoint`: POST mit `endpoint:"http://x"` → 422
  - `test_devices_persist_across_restart`: Gerät anlegen, `taster` löschen, neue `TestClient(create_app(settings))` → neues Gerät da, `taster` weg
  - `test_set_value_route`: `/api/devices/fuellstand/value` 4.5 → 4.5; `/api/devices/lampe/value` → 409; unbekannt → 404
  - `test_new_device_usable_in_run_check`: neues Sensorgerät, Workflow mit `wait_sensor` darauf → `POST /api/workflows/validate` (Body = Workflow-Definition) → `valid is True`
- [ ] **Step 2:** `docker compose run --rm --no-deps backend python -m pytest -q` → neue Tests FAIL.
- [ ] **Step 3:** Implementieren; `test_api.py` auf `/value` umstellen; `docs/api-contract.md` aktualisieren.
- [ ] **Step 4:** `docker compose run --rm --no-deps backend sh -c "ruff check . && ruff format --check . && mypy && python -m pytest -q"` → alles grün.
- [ ] **Step 5:** Commit `feat(backend): Geräte verwalten (CRUD, Löschsperre, Protokolle)`

### Task 3: Frontend – Vertrag, Real- und Mock-Client

**Files:**
- Modify: `src/Frontend/src/api/contract.ts`, `realClient.ts`, `mockClient.ts`
- Test: `src/Frontend/src/api/realClient.test.ts`, `src/Frontend/src/api/mockClient.test.ts`

**Interfaces:**
- Produces (`contract.ts`):
  - `DeviceProtocolSchema = z.enum(['virtual','mqtt','opcua'])`
  - `DeviceConfigSchema` (zod `discriminatedUnion('protocol', …)`) mit denselben Feldern wie Backend; Antworten zusätzlich `password_set?: boolean`, ohne `password`.
  - `DeviceSchema` + `protocol`, `config`, `simulated: z.boolean()`.
  - `DeviceInputSchema = { name, type, config, unit?, min?, max? }`, `type DeviceInput`.
  - `ApiClient` + `createDevice(input: DeviceInput): Promise<Device>`, `updateDevice(id: string, input: DeviceInput): Promise<Device>`, `deleteDevice(id: string): Promise<void>`.
  - `DEVICE_TYPE_KIND: Record<DeviceType, 'sensor'|'actuator'>`, `DEVICE_TYPE_LABELS` (Schalter, Taster, Zahlenwert, Lampe, Förderband), `PROTOCOL_LABELS` (virtuell, MQTT, OPC UA).
- `realClient`: `setDevice` → `PUT /devices/{id}/value`; neue Methoden auf POST/PUT/DELETE `/devices…`.
- `mockClient`: `DEFAULT_MOCK_DEVICES` mit `protocol:'virtual', config:{protocol:'virtual'}, simulated:true`; CRUD mit gleicher ID-Erzeugung (`slugify` als Export in `mockClient.ts`), Löschsperre gegen gespeicherte Mock-Workflows → `ApiError(…, 409)` mit Namen der Workflows in der Meldung; Passwort nicht zurückgeben.

- [ ] **Step 1: Failing tests:**
  - realClient: `setDevice('taster', true)` ruft `/api/devices/taster/value`; `deleteDevice('x')` ruft DELETE `/api/devices/x`
  - mockClient: `createDevice({name:'Band', type:'conveyor', config:{protocol:'mqtt',host:'b',topic:'t',port:1883,qos:0,tls:false,password:'p'}})` → `id 'band'`, `kind 'actuator'`, kein `password` im Ergebnis; zweites „Band“ → `band-2`; `deleteDevice('lampe')` bei gespeichertem Workflow mit setActuator `lampe` → wirft Status 409; `deleteDevice('taster')` ohne Verwendung → Liste ohne `taster`
- [ ] **Step 2:** `docker compose --profile dev exec frontend-dev pnpm test src/api` → FAIL
- [ ] **Step 3:** Implementieren.
- [ ] **Step 4:** `docker compose --profile dev exec frontend-dev pnpm test src/api && docker compose --profile dev exec frontend-dev pnpm typecheck` → PASS
- [ ] **Step 5:** Commit `feat(frontend): Geräte-API im Vertrag, Real- und Mock-Client`

### Task 4: Frontend – Ansicht „Geräte“

**Files:**
- Create: `src/Frontend/src/devices/DevicesView.tsx`
- Modify: `src/Frontend/src/App.tsx` (Tab `devices` „Geräte“ zwischen Editor und Skills)
- Test: `src/Frontend/src/devices/DevicesView.test.tsx`

**Interfaces:**
- Consumes: Task 3 (`api.createDevice/updateDevice/deleteDevice/listDevices`, Labels, `DeviceInputSchema`).
- Aufbau wie `SkillsView`: Tabelle (Name, Art, Typ, Protokoll, Adresse = `topic` bzw. `node_id` bzw. „–“, Wert) + Buttons Bearbeiten/Löschen; Dialog mit Name, Typ (Select mit Art in Klammern), Protokoll (Select), danach nur Felder des Protokolls; Einheit/Min/Max nur bei `number`; Passwortfeld mit Platzhalter „unverändert“ wenn `password_set`. Löschen mit `confirm`-Dialog; 409 → `toast.error` mit Backend-Meldung. Nach jeder Mutation `invalidateQueries(['devices'])`.

- [ ] **Step 1: Failing tests** (Testing Library; `vi.mock('@/api/client', …)` liefert `{ api: createMockClient() }`, Komponente in eigenem `QueryClientProvider`):
  - Tabelle zeigt „Lichtschranke“ und Protokoll „virtuell“
  - „Neues Gerät“ → Name „Band 2“, Typ Förderband, Protokoll MQTT → Felder Host/Topic sichtbar, OPC-UA-Felder nicht; Speichern → Zeile „Band 2“ mit Adresse = Topic
  - Löschen eines verwendeten Geräts zeigt Fehlertoast, Zeile bleibt
- [ ] **Step 2:** `pnpm test src/devices` → FAIL
- [ ] **Step 3:** Implementieren.
- [ ] **Step 4:** `pnpm test src/devices` → PASS
- [ ] **Step 5:** Commit `feat(frontend): Ansicht Geräte zum Anlegen, Bearbeiten und Löschen`

### Task 5: Frontend – Geräteleiste filtert nach Workflow, E2E

**Files:**
- Modify: `src/Frontend/src/devices/DeviceBar.tsx`
- Create: `src/Frontend/src/devices/workflowDevices.ts` (+ `workflowDevices.test.ts`)
- Create: `src/Frontend/e2e/devices.spec.ts`
- Modify: `src/Frontend/README.md` (Abschnitt Geräte, kurz)

**Interfaces:**
- Produces: `workflowDeviceIds(nodes: FlowNode[]): Set<string>` – `deviceId` aller `waitSensor`/`condition`/`setActuator`-Knoten, leere IDs ignoriert; `useWorkflowDeviceIds()` = `useEditor` + `useShallow`.
- DeviceBar: `list.filter(d => ids.has(d.id))`; unbekannte IDs ignoriert; leer → Hinweistext aus Spec („Noch keine Geräte im Workflow – im Block (Warte auf Sensor, Bedingung, Aktor setzen) auswählen.“); Kopfzeile „Adapter: virtuell“ → „Werte simuliert“; pro Gerät Badge mit `PROTOCOL_LABELS[d.protocol]`.

- [ ] **Step 1: Failing tests:** `workflowDeviceIds` mit Start + waitSensor(`lichtschranke`) + setActuator(`''`) + condition(`gibtsnicht`) → `{'lichtschranke','gibtsnicht'}`; DeviceBar-Render mit diesen Knoten zeigt nur Lichtschranke, keinen Fehler.
- [ ] **Step 2:** `pnpm test src/devices` → FAIL
- [ ] **Step 3:** Implementieren.
- [ ] **Step 4:** E2E `devices.spec.ts`: Tab Geräte → MQTT-Sensor „Testschalter“ (Typ Schalter) anlegen → Editor → leerer Workflow → Block „Warte auf Sensor“ einfügen, Sensor „Testschalter“ wählen → Geräteleiste zeigt „Testschalter“ mit Badge „MQTT“; Screenshot `e2e/screenshots/devices-*.png` bei 1280 px.
- [ ] **Step 5:** `docker compose --profile dev exec frontend-dev pnpm check` und `docker compose --profile dev --profile e2e run --rm e2e` → grün; Screenshots ansehen (nichts abgeschnitten).
- [ ] **Step 6:** Commit `feat(frontend): Geräteleiste zeigt Geräte des Workflows`

### Task 6: Gesamtprüfung

- [ ] Backend: `docker compose run --rm --no-deps backend sh -c "ruff check . && ruff format --check . && mypy && python -m pytest -q"` → grün
- [ ] Frontend: `pnpm check` + E2E → grün
- [ ] Manuell im Real-Modus: `docker compose up -d --build backend frontend` → http://localhost:8080, Gerät anlegen, im Workflow nutzen, Lauf im Modus mock starten, Aktor schaltet in Leiste.
