# Geräteverwaltung (Sensoren und Aktoren) – Design

Stand: 21.11.2026

## Ziel und Hintergrund

Sensoren und Aktoren (externe Systeme) sollen in einer eigenen Ansicht angelegt, bearbeitet und gelöscht werden: Name,
Art, Typ, Protokoll (MQTT, OPC UA) und die passenden Verbindungseinstellungen. Ein Gerät, das in einem Workflow
verwendet wird, erscheint in der Geräteleiste unten rechts und kann dort beobachtet bzw. (Sensor) bedient werden.

**Warum jetzt:** Für die Demo soll sichtbar sein, dass echte Anlagen über Standardprotokolle anschließbar sind.
Die Werte werden vorerst **simuliert**. Später werden echte Geräte angebunden – ohne dass Workflows sich ändern.

## Ziele

- Gerätestamm dauerhaft in SQLite statt fest im Code.
- CRUD-API im Backend, neue Ansicht „Geräte“ im Frontend (Tab neben „Workflow-Editor“ und „Skills“).
- Protokolle: `virtual` (ohne Einstellungen), `mqtt`, `opcua` – Einstellungen je Protokoll validiert.
- Geräteleiste zeigt nur Geräte, auf die der geöffnete Workflow verweist.
- Löschen eines Geräts, das ein gespeicherter Workflow verwendet, wird blockiert (mit Liste der Workflows).
- Mock-Client im Frontend kann dasselbe (für den Testmodus).

## Nicht-Ziele

- Keine echte MQTT-/OPC-UA-Verbindung, keine Client-Bibliotheken, kein Verbindungstest.
- Keine neuen Gerätetypen (bleibt bei `switch`, `button`, `number` → Sensor; `lamp`, `conveyor` → Aktor).
- Aktoren bleiben in der Geräteleiste reine Anzeige; geschaltet werden sie vom Ablauf (F10 unverändert).
- Keine Speicherung der simulierten Werte über einen Neustart hinaus.

## Anti-Ziele

- Bestehende Workflows (Beispiel-Workflow, gespeicherte Workflows) dürfen nicht kaputtgehen: Die sieben bisherigen
  Geräte bleiben mit unveränderten IDs erhalten.
- Kein Passwort im Klartext in API-Antworten oder Logs.

## Ansätze

- **A – Geräte als eigene, gespeicherte Liste im Backend (gewählt).** Gemeinsamer Gerätestamm, Workflows verweisen
  per ID; später je Protokoll ein Adapter hinter derselben Schnittstelle.
- B – Geräte im Workflow speichern: schneller, aber dasselbe Gerät müsste in jedem Workflow neu angelegt werden; passt
  nicht zu „verwalten“ und gemeinsam genutzten echten Anlagen.
- C – Nur im Browser speichern: scheidet aus, die Engine im Backend muss die Geräte kennen.

Vom User entschieden: A; Löschen blockieren, solange ein gespeicherter Workflow das Gerät verwendet.

## Design

### Datenmodell (Backend)

Neue Tabelle in `src/Backend/models/schema.sql` (nur `CREATE TABLE IF NOT EXISTS`, bestehende Tabellen bleiben):

```sql
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,          -- stabile ID, auf die Workflows verweisen
    name TEXT NOT NULL,
    type TEXT NOT NULL,           -- switch | button | number | lamp | conveyor
    protocol TEXT NOT NULL,       -- virtual | mqtt | opcua
    config TEXT NOT NULL,         -- JSON, je Protokoll
    unit TEXT, min REAL, max REAL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
```

- `kind` (sensor/actuator) wird wie heute aus `type` abgeleitet.
- **ID:** beim Anlegen aus dem Namen erzeugt (Slug, Umlaute ersetzt, bei Kollision `-2`, `-3` …), danach unveränderlich.
- **Startbestand:** Ist die Tabelle beim Start leer, werden die sieben bisherigen `DEFAULT_DEVICES` mit Protokoll
  `virtual` eingefügt (einmalig; gelöschte Geräte kommen nicht zurück, solange noch eines existiert).

### Protokoll-Einstellungen (Pydantic, diskriminiert nach `protocol`)

- `virtual`: keine Felder.
- `mqtt`: `host` (Pflicht), `port` (Standard 1883), `topic` (Pflicht), `qos` (0–2, Standard 0), `username` (optional),
  `password` (optional, write-only), `tls` (bool, Standard false), `payload_path` (optional, z. B. JSON-Feld `value`).
- `opcua`: `endpoint` (Pflicht, muss mit `opc.tcp://` beginnen), `node_id` (Pflicht, z. B. `ns=2;s=Lichtschranke`),
  `security_mode` (`None` | `Sign` | `SignAndEncrypt`, Standard `None`), `username`/`password` (optional, Passwort
  write-only).

Passwort: wird gespeichert, in Antworten aber nie zurückgegeben – stattdessen `password_set: true/false`. Beim
Bearbeiten bedeutet ein leeres/fehlendes Passwort „unverändert lassen“.

### Laufzeit (Werte simuliert)

- `VirtualAdapter` wird zur Geräte-Registry: Stammdaten aus der DB, Werte im Speicher. Neues Gerät startet mit `false`
  bzw. `min` oder `0`. Ändert sich der Typ, wird der Wert zurückgesetzt.
- Jedes Gerät – egal welches Protokoll – wird vorerst simuliert. In der Antwort steht `simulated: true`, damit die
  Oberfläche „simuliert“ anzeigen kann. Später entscheidet die Registry anhand von `protocol`, welcher Adapter
  (MQTT/OPC UA) Werte liest bzw. schreibt; `DeviceAdapter`-Schnittstelle (`list/get/set`) bleibt.
- Laufende Läufe: Prüfung vor dem Start nutzt den aktuellen Stamm (wie heute über `devices.list()`).

### API (`/api/devices`)

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/devices` | Liste inkl. Wert, Protokoll, Einstellungen (ohne Passwort) |
| POST | `/devices` | Anlegen → 201 |
| PUT | `/devices/{id}` | Stammdaten ändern (Name, Typ, Protokoll, Einstellungen, Einheit, min/max) |
| DELETE | `/devices/{id}` | Löschen → 204; 409 `device_in_use` mit `details: [{id, name}]` der Workflows |
| PUT | `/devices/{id}/value` | Sensor bedienen (bisher `PUT /devices/{id}`) |

- `PUT /devices/{id}` mit Body `{value}` wird auf `/value` verlegt; Frontend und `docs/api-contract.md` ziehen nach.
- Typwechsel in die andere Art (Sensor ↔ Aktor) wird mit 409 abgelehnt, solange ein gespeicherter Workflow das Gerät
  verwendet.
- „Verwendet“ = ein Block `wait_sensor`, `condition` oder `set_actuator` in einer gespeicherten Workflow-Definition
  hat `params.device == id`.
- Name darf nicht leer sein; `min <= max`; `unit/min/max` nur bei `number`.

### Frontend

- `contract.ts`: `DeviceSchema` um `protocol`, `config`, `simulated` erweitern; neue `DeviceInput`; `ApiClient` bekommt
  `createDevice`, `updateDevice`, `deleteDevice`. `realClient` und `mockClient` implementieren das (Mock: Speicher,
  gleiche Löschsperre gegen die Mock-Workflows, gleiche ID-Erzeugung).
- **Neue Ansicht `src/devices/DevicesView.tsx`** (Tab „Geräte“), aufgebaut wie `SkillsView`:
  Tabelle (Name, Art, Typ, Protokoll, Adresse = Topic bzw. Node-ID, aktueller Wert) und Dialog zum Anlegen/Bearbeiten.
  Im Dialog: Name, Typ (Auswahl zeigt Art), Protokoll, danach nur die Felder des gewählten Protokolls; bei `number`
  Einheit/min/max. Löschen mit Bestätigung; bei 409 Toast mit den Namen der Workflows.
- **Geräteleiste:** filtert auf die `deviceId`s der Blöcke im Editor-Store (aktueller, auch ungespeicherter Stand).
  Hat der Workflow keine Geräte: Hinweis „Noch keine Geräte im Workflow – im Block (Warte auf Sensor, Bedingung,
  Aktor setzen) auswählen.“ Neben „Adapter: virtuell“ steht künftig je Gerät ein kleines Protokoll-Badge
  (MQTT/OPC UA/virtuell) mit Hinweis „simuliert“.
- **Lampenfarbe:** heute an `id.includes('rot')` erkannt; bleibt so (Nicht-Ziel), neue Lampen sind grün, außer die
  ID enthält „rot“.
- Eigenschaften-Panel bleibt: Gerätewahl über die (jetzt verwaltete) Geräteliste; Query-Key `['devices']` wird nach
  Anlegen/Bearbeiten/Löschen invalidiert.

### Tests

- Backend: Repo + API (Anlegen, ID-Kollision, Validierung je Protokoll, Passwort nie in der Antwort, Löschsperre 409,
  Artwechsel-Sperre, Startbestand, Sensor setzen über `/value`, Aktor setzen weiterhin 409). ruff, mypy, pytest im
  Container.
- Frontend: Vitest für Mock-Client (CRUD, Löschsperre), Filterlogik der Geräteleiste, Mapping; E2E: Gerät anlegen,
  im Block wählen, erscheint in der Geräteleiste. `pnpm check` grün, Screenshot bei 1280 px.

## Dem Umsetzer überlassen

- Genaues Layout von Tabelle und Dialog (an `SkillsView` orientieren).
- Wo die Funktion „verwendet in Workflows“ liegt (Repo-Funktion, die gespeicherte Definitionen durchsucht, ist nahe).
- Ob die Geräteleiste die Liste per Hook (`useWorkflowDeviceIds`) bezieht.

## Entscheidungen von Claude (bitte prüfen)

- ID automatisch aus dem Namen, danach unveränderlich (Workflows verweisen auf die ID).
- `virtual` bleibt als drittes Protokoll; die bisherigen sieben Geräte werden damit übernommen.
- Wert-Endpunkt wird nach `/devices/{id}/value` verlegt, damit `PUT /devices/{id}` die Stammdaten ändert.
- Passwort write-only.
- Aktoren in der Geräteleiste weiterhin nur Anzeige.
- Geräteleiste filtert nach dem aktuellen Editor-Stand, nicht nach dem gespeicherten Workflow.
