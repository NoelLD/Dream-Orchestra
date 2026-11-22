# DreamOrchestra Frontend

Visueller Workflow-Editor für Dream-1-Abläufe mit virtuellen Sensoren und Aktoren. Anforderungen: `../../Konzept.md` §2, API-Vertrag: `../../docs/api-contract.md`.

## Stack
- Vite 8, React 19, TypeScript 7 (`strict`, `noUncheckedIndexedAccess`), pnpm 12 über corepack, Node 24 (nur im Container)
- Editor: `@xyflow/react` 13. Änderungen mit `changes.applyTo(...)`, CSS `@xyflow/react/style.css`; `applyNodeChanges` gibt es nicht mehr.
- UI: Tailwind CSS 4 + shadcn/ui (Radix, Preset Nova), Icons lucide-react. Klassen mit `cn` aus `@/lib/utils` (Paket `cn` von shadcn)
- Zustand: zustand 5 (Selektoren, die Arrays bauen, brauchen `useShallow`); Validierung: zod 4; Serverdaten: TanStack Query 5
- Lint: oxlint (aus der Vite-Vorlage; typescript-eslint unterstützt TS 7 noch nicht)
- Tests: Vitest 5 + Testing Library (jsdom), E2E: Playwright 1.65.1

## Ordner
```
src/api/        contract.ts (Editor-Format), backendMapping.ts (Editor <-> Backend-Vertrag), realClient.ts,
                mockClient.ts, mode.ts, client.ts, useBackendStatus.ts (Banner nach Backend-Modus)
src/workflow/   blocks.ts, store.ts (Editor + Laufzustand), flow.ts (Editor <-> JSON), io.ts (Import/Export),
                validate.ts (F4), estimate.ts (F15), sample.ts (Beispiel + leerer Workflow),
                components/ (Canvas, BlockNode, SmartEdge, Palette, Toolbar, PropertiesPanel, WorkflowsDialog)
src/run/        useRun.ts (Polling, Start/Stopp/Pause), RunLog.tsx, labels.ts
src/devices/    DeviceBar.tsx (nur Geräte des Workflows), DevicesView.tsx (Verwaltung), deviceForm.ts, workflowDevices.ts
src/skills/     SkillsView.tsx
src/components/ AppHeader.tsx (STOPP, Mock-Banner), ui/ (shadcn – generiert)
e2e/            Playwright-Specs; Screenshots landen in e2e/screenshots/ (gitignored)
```

## Befehle (immer im Container, aus dem Repo-Wurzelordner)
```sh
docker compose --profile dev up -d --build frontend-dev          # Dev-Server http://localhost:5173
docker compose --profile dev exec frontend-dev pnpm lint
docker compose --profile dev exec frontend-dev pnpm typecheck
docker compose --profile dev exec frontend-dev pnpm test
docker compose --profile dev exec frontend-dev pnpm build
docker compose --profile dev exec frontend-dev pnpm check        # lint + typecheck + test + build
docker compose --profile dev exec frontend-dev pnpm add <paket>
docker compose --profile dev --profile e2e run --rm e2e          # Playwright-E2E + Screenshots
docker compose up -d --build frontend                            # Produktion (nginx) http://localhost:8080
```
shadcn-Komponenten: `docker compose --profile dev exec frontend-dev pnpm dlx shadcn@4.23.0 add <name> -y`

## Ports
| Dienst | Adresse | Zweck |
|---|---|---|
| `frontend-dev` | `127.0.0.1:5173` | Vite-Dev-Server, Hot Reload (Polling, `DEV_POLLING=false` in WSL2) |
| `frontend` | `127.0.0.1:8080` | Produktions-Build über nginx (Container-Port 80) |
| `playwright` | `127.0.0.1:8931/mcp` | Playwright-MCP für Claude Code, öffnet `http://frontend-dev:5173` |

`/api/*` geht im Dev über den Vite-Proxy und in Produktion über nginx unverändert an `http://backend:8000/api/*` (das Präfix bleibt erhalten).

## API-Modus
- `VITE_API_MODE=mock` (Standard in `frontend-dev`): `mockClient.ts` spielt das Backend im Browser nach. Dann ist das Banner „SIMULIERTE API“ dauerhaft sichtbar.
- `VITE_API_MODE=real` (Standard im Produktions-Build, Build-Arg `VITE_API_MODE_PROD`): echtes Backend über `/api`
- Ist der Wert nicht gesetzt, gilt `real`. Ein unbekannter Wert ist ein Fehler.

## Regeln
- Node- und pnpm-Befehle **nur im Container**, nie auf dem Host.
- **Engine-Logik gehört ins Backend** (N3). Das Frontend zeigt Läufe nur an. Ausnahmen: die Prüfung vor dem Start (F4) als schnelles Feedback und der Mock als klar markierter Stellvertreter.
- **Kein Secret im Frontend** (N1): keine Keys in `VITE_*`-Variablen, im Code oder im Protokoll. Das Frontend spricht nur mit `/api`.
- **Mock-Modus immer sichtbar:** Banner und Badge nie entfernen oder abschwächen.
- Verbindlich ist das OpenAPI-Schema des Backends (`http://localhost:8000/docs`). Änderungen am Backend-Format in `src/api/backendMapping.ts` (mit Tests) **und** `docs/api-contract.md` nachziehen; das Editor-Format steht in `src/api/contract.ts`.
- Verhalten testgetrieben: erst ein Test, der scheitert, dann der Code.
- **Vor „fertig“:** `pnpm check` (lint + typecheck + test + build) muss grün sein.
- **UI-Änderungen** mit Playwright-Screenshot prüfen (Dienst `e2e` oder Playwright-MCP) und bei 1280 px kontrollieren, dass nichts abgeschnitten oder verdeckt ist.
- Nur `src/Frontend/`, den Frontend-Teil von `compose.yaml`, `docs/api-contract.md` und Ignore-Dateien ändern. Backend, Simulation und Datenbank nicht anfassen.
- Nicht committen oder pushen ohne Auftrag; keine Container oder Volumes löschen (kein `down -v`).
