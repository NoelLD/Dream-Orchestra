# Anforderungen Dream-Orchestra (v0.1, Entwurf)

## Ziel

Eine Oberfläche, in der man Abläufe aus Blöcken zusammensetzt: Dream-1-Prompts, virtuelle Sensoren und Aktoren, Warten und Bedingungen. Der Orchestrator arbeitet die Blöcke nacheinander gegen die Dream-Labs-Simulation ab und zeigt den Fortschritt live.

## Rahmen

- Hackathon, Umsetzung in weniger als 24 Stunden
- Team: Python und Robotik/Steuerung, keine ausgeprägte Web-Frontend-Erfahrung
- Keine realen Roboter, Sensoren oder Aktoren. Der Roboter läuft in der Dream-Labs-Simulation und bekommt echte Prompts. Die Credits stellt der Veranstalter.
- Sensoren und Aktoren sind vorerst nur virtuelle Anzeigen und Schalter in der Oberfläche. Sie zeigen, dass sich externe Geräte einbinden lassen.
- Bedienung über einen Block-Editor
- Demo-Szenario: Pick-and-Place

## Annahmen (prüfen, sobald die API-Beschreibung vorliegt)

- **A1:** Die API kann einen Simulationslauf mit einem Prompt starten, seinen Status abfragen (zum Beispiel „läuft“, „erfolgreich“, „fehlgeschlagen“) und ihn stoppen.
- **A2:** Jeder Lauf verbraucht Credits.
- **A3:** Die Simulation selbst sieht man in der Dream-Labs-Oberfläche; unser Tool zeigt nur den Status.

## Funktionale Anforderungen

Prioritäten: **M** = Pflicht für die Demo, **S** = sollte, **K** = Kür

### Editor

| ID | Prio | Anforderung |
|---|---|---|
| F1 | M | Blöcke auf einer Fläche platzieren und mit Pfeilen verbinden. Blocktypen: *Start*, *Dream-1-Prompt*, *Warte auf Sensor*, *Aktor setzen*, *Warte (Zeit)*, *Ende* |
| F2 | M | Block *Bedingung* (wenn Sensor X, dann Pfad A, sonst B) und Pfeile zurück zu früheren Blöcken. Pick-and-Place braucht die Schleife „nächstes Objekt“. |
| F3 | M | Abläufe als JSON-Datei speichern und laden |
| F4 | M | Prüfung vor dem Start: genau ein Start-Block, keine losen Blöcke, kein leerer Prompt |

### Ausführung

| ID | Prio | Anforderung |
|---|---|---|
| F5 | M | Ablauf starten; der aktive Block wird hervorgehoben |
| F6 | M | Prompt-Block: Prompt an die API senden, Status abfragen, bei „erfolgreich“ weiter. Es gibt ein Zeitlimit pro Block, und Fehler führen auf einen Fehlerpfad oder zum Abbruch. |
| F7 | M | Stopp-Knopf, der immer sichtbar ist: bricht den Ablauf ab und stoppt den laufenden Simulationslauf über die API |
| F8 | S | Pause und Einzelschritt |
| F9 | S | Wiederholungen pro Prompt-Block, falls ein Lauf fehlschlägt |

### Virtuelle Sensoren und Aktoren

| ID | Prio | Anforderung |
|---|---|---|
| F10 | M | Eine Geräteleiste mit virtuellen Sensoren (Schalter, Taster, Zahlenwert), die der Nutzer bedient, und Aktoren (Lampe, Förderband an/aus), die der Ablauf schaltet |
| F11 | M | Eine Geräte-Schnittstelle: Jedes Gerät hat Name, Typ und Wert und dazu einen Adapter. Für den Hackathon gibt es nur den Adapter „virtuell“; später kommen echte Geräte als weiterer Adapter hinzu. |
| F12 | S | „Warte auf Sensor“ mit Bedingung (zum Beispiel `Lichtschranke == an`) und eigenem Zeitlimit |
| F13 | K | Ein zweiter Adapter (zum Beispiel MQTT) als Beleg, dass echte Geräte wirklich anschließbar sind |

### Überwachung

| ID | Prio | Anforderung |
|---|---|---|
| F14 | M | Ein Ablaufprotokoll mit Zeitstempel, Block, API-Status und Dauer |
| F15 | S | Ein Credit-Zähler pro Ablauf und vor dem Start eine Schätzung (Anzahl der Prompt-Blöcke × Wiederholungen) |
| F16 | K | Die Dream-Labs-Simulationsansicht verlinken oder einbetten |
| F17 | K | Eine KI schlägt aus einem Ziel einen ersten Ablauf vor |

## Nicht-funktionale Anforderungen

- **N1:** Der API-Key steht nur in der `.env`, nie in der Oberfläche, im Protokoll oder im Code.
- **N2:** Es gibt einen Testmodus für die API: ein Stellvertreter, der Statusantworten nachspielt. So entwickelt man ohne Credits und ohne auf die echte API zu warten. Damit die Demo nichts vortäuscht, zeigt die Oberfläche ihn deutlich als „SIMULIERTE API“ an; in der Demo läuft die echte API.
- **N3:** Die Ablauf-Engine ist von der Oberfläche getrennt und mit `pytest` testbar.
- **N4:** API-Fehler und Zeitüberschreitungen bringen das Programm nicht zum Absturz, sondern erscheinen im Protokoll.
- **N5:** Der Abstand zwischen zwei Statusabfragen ist einstellbar, damit keine Ratenlimits gerissen werden.
- **N6:** Das Tool startet lokal mit einem Befehl, auf Basis des vorhandenen Docker-Setups.

## Architektur (Skizze)

```
┌──────────────────────┐   Ablauf als JSON   ┌───────────────────────┐
│ Oberfläche           │ ──────────────────► │ Ablauf-Engine         │
│ Block-Editor,        │ ◄────────────────── │ (Zustandsautomat,     │
│ Geräteleiste,        │   Status, Protokoll │  Python)              │
│ Protokoll, Stopp     │                     └───┬───────────────┬───┘
└──────────────────────┘                         │               │
                                       ┌─────────▼──────┐ ┌──────▼───────────┐
                                       │ Dream-Adapter  │ │ Geräte-Adapter   │
                                       │ echt | Test    │ │ virtuell | (MQTT)│
                                       └────────────────┘ └──────────────────┘
```

Das Herzstück ist die Engine; sie hängt nicht von der Oberfläche ab. Plan B: Wird der Block-Editor in der Zeit nicht fertig, setzt man eine einfache Schrittliste davor. Die liefert dasselbe JSON, und alles andere bleibt unverändert.

## Technik-Vorschlag (noch nicht geprüft)

Eine Python-Oberfläche (zum Beispiel NiceGUI) mit einer fertigen Node-Editor-Bibliothek darin (zum Beispiel Drawflow), damit nur wenig JavaScript nötig ist. Alternative: Node-RED als Editor. Das spart Arbeit, aber dann ist weniger „eigenes Tool“. Ob die Bibliotheken aktuell und passend sind, ist noch zu prüfen.

## Demo-Ablauf (Pick-and-Place)

`Start` → `Warte auf Sensor „Objekt da“` → `Prompt: „Greife das Objekt und lege es in die Kiste“` → `Aktor: Lampe grün` → `Bedingung: „Weitere Objekte?“`

- ja: zurück zu `Warte auf Sensor`
- nein: `Ende`
- Wenn ein Schritt fehlschlägt: `Aktor: Lampe rot` → `Ende`

## Offene Fragen

1. Die echte API: Endpunkte, Statuswerte, Kosten pro Lauf (prüft A1 bis A3)
2. Wonach bewertet die Jury?
3. Kann ein Prompt-Lauf in der Simulation auch ohne eindeutigen Status enden? Dann braucht der Block einen Knopf „manuell als erledigt markieren“.

## Hintergrund: Erkenntnisse aus dem SDK `dreamlabs-client` 1.1.7

- Dream-1 ist ein Steuerungsmodell. Pro Aufruf bekommt es den Prompt, die letzten Kamerabilder und den Gelenkzustand und liefert ein Stück Bewegung (48 Zeilen Gelenkziele).
- Das SDK meldet keinen Erfolg und keinen Abschluss einer Aufgabe. Ob die Simulations-API einen Status liefert, ist deshalb gesondert zu prüfen.
- Ratenlimit pro Sitzung: 3 schnelle Aufrufe, danach einer alle 0,7 s
- Aufrufe werden abgerechnet.
