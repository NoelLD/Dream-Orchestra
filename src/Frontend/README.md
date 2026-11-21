# DreamOrchestra – Frontend

Visueller Workflow-Editor für Dream-1-Roboterabläufe. Man baut Abläufe aus Blöcken (Prompt an Dream-1, Warte auf Sensor, Aktor setzen, Bedingung, Schleife), startet sie und verfolgt live, welcher Block gerade läuft. Sensoren und Aktoren sind im Hackathon virtuelle Schalter und Anzeigen.

Anforderungen: [`Konzept.md`](../../Konzept.md) · API-Vertrag mit dem Backend: [`docs/api-contract.md`](../../docs/api-contract.md)

## Starten

Voraussetzung ist nur Docker. Node muss nicht auf dem Rechner installiert sein. Alle Befehle laufen im Repo-Wurzelordner.

```sh
docker compose --profile dev up -d --build    # alles inkl. Dev-Server
```

| Adresse | Was |
|---|---|
| http://localhost:5173 | Entwicklung mit Hot Reload, **Testmodus** (simulierte API) |
| http://localhost:8080 | Produktions-Build über nginx, **echte API** |

## Testmodus vs. echte API

- **Testmodus** (`VITE_API_MODE=mock`, Standard auf Port 5173): Das Backend wird im Browser nachgespielt. Es gibt keine Credits, kein Dream-1 und keine Datenbank. Oben steht dann dauerhaft das gelbe Banner **„SIMULIERTE API“**.
- **Echte API** (Standard auf Port 8080): Das Frontend ruft `/api/...` auf, nginx leitet unverändert an das Backend weiter. Banner und Badge zeigen den Modus, den das Backend über `GET /api/status` meldet (`mock`, `sim` oder `real`).

## Demo in 1 Minute (Testmodus)

1. http://localhost:5173 öffnen. Der Beispiel-Ablauf „Pick-and-Place“ ist geladen.
2. **Lauf starten**: Der Block „Greifen“ leuchtet blau, nach ca. 3 s wartet „Objekt in Kiste?“.
3. In der Geräteleiste **Lichtschranke** einschalten. Der Ablauf läuft über die Schleife zurück zu „Greifen“.
4. **Weitere Objekte** ausschalten. Der Lauf endet mit „erfolgreich“, das Protokoll zeigt jeden Schritt.
5. Der rote **STOPP**-Knopf oben rechts bricht jederzeit ab.

## Prüfen

```sh
docker compose --profile dev exec frontend-dev pnpm check          # lint + typecheck + Unit-Tests + build
docker compose --profile dev --profile e2e run --rm e2e            # Browser-Tests (Playwright), Screenshots in e2e/screenshots/
```

## Technik

Vite, React, TypeScript (strict), React Flow, Tailwind + shadcn/ui, zustand, zod, TanStack Query, Vitest, Playwright. Aufbau, Regeln und alle Befehle stehen in [`CLAUDE.md`](CLAUDE.md).
