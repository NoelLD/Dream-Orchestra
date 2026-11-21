# DreamOrchestra

Docker Compose startet das Frontend mit Nginx, das Backend mit Python 3.12, den Simulationsdienst mit Python 3.12, MuJoCo und FastAPI und den SQLite-Datenbankdienst. Die API des Simulationsdienstes beschreibt [`src/Simulation/README.md`](src/Simulation/README.md), die Live-Doku liegt unter `http://localhost:3001/docs`.

## Setup

Docker starten und in den Ordner mit `compose.yaml` wechseln (`implementierung/`). Alle vier Dienste starten mit `docker compose up`. Mit `--build` werden die Images vorher gebaut.

```sh
docker compose up --build
```

Für einen einzelnen Dienst beispielsweise `docker compose up --build backend` ausführen. Die Dienstnamen und lokalen Adressen stehen in der Tabelle.

| Dienst | Quellordner mit Dockerfile | Adresse |
| --- | --- | --- |
| `frontend` | `src/Frontend` | `http://localhost:8080` |
| `backend` | `src/Backend` | `http://localhost:8000/health` |
| `simulation` | `src/Simulation` | `http://localhost:3001/health`, API-Doku `http://localhost:3001/docs` |
| `simulation-gui` (optional, `--profile gui`) | `src/Simulation` | `http://localhost:6080/vnc.html` (MuJoCo-Fenster im Browser) |
| `database` | `src/Database` | `http://database:8081/health` im Compose-Netz |

Compose bindet jeden Quellordner schreibgeschützt ein. Nach Änderungen am Backend oder Simulationsserver den Dienst neu starten, beispielsweise mit `docker compose restart backend`. `docker compose down` stoppt die Dienste.

## SQLite und Datenmodell

Der Dienst `database` legt beim ersten Start `src/Backend/data/dreamorchestra.sqlite3` an. Die Datei bleibt nach `docker compose down` auf dem Host erhalten und wird von Git ignoriert. Über `http://localhost:8000/health/database` prüft das Backend die Verbindung zum Datenbankdienst.

Das Schema liegt in [`src/Backend/models/schema.sql`](src/Backend/models/schema.sql) und enthält als Ausgangspunkt die Tabelle `skills`. Der Datenbankdienst führt das Schema bei jedem Start aus. Neue Tabellen mit `CREATE TABLE IF NOT EXISTS` ergänzen und `docker compose restart database` ausführen. Änderungen an vorhandenen Tabellen brauchen eine gezielte Migration.

Für SQL-Abfragen die SQLite-Shell im Datenbankcontainer öffnen. [Python-Dokumentation zur SQLite-Shell](https://docs.python.org/3.12/library/sqlite3.html#command-line-interface)

```sh
docker compose exec database python -m sqlite3 /data/dreamorchestra.sqlite3
```

## Dream-Labs-Verbindungstest

Falls `.env` fehlt, `.env.template` als `.env` kopieren. Dann `DREAM_API_KEY` eintragen. Der Test ruft den Modellkatalog ab und zeigt SDK-Version und Anzahl der Checkpoints an. [Dream-Labs-Plattform](https://platform.dreamlabs.ai/)

```sh
docker compose run --rm --build backend python test_dream_api.py
```

In PowerShell startet `./start.ps1` den Verbindungstest auch ohne Compose.

## Umgebungsvariablen

Compose übergibt `.env` an den Backend-Dienst. Der Dream-Labs-Verbindungstest benötigt den API-Key. Werte als `NAME=Wert` ohne Anführungszeichen eintragen. Die optionalen URLs nur ändern, wenn Dream Labs für den Zugang andere Adressen vorgibt.

| Variable | Zweck | Standard |
| --- | --- | --- |
| `DREAM_API_KEY` | API-Key für die Authentifizierung | Pflichtfeld |
| `DREAM_API_URL` | Plattform mit dem Modellkatalog. Der Test verwendet diese URL. | `https://platform.dreamlabs.ai` |
| `DREAM_GATEWAY_URL` | Gateway für künftige Inferenzaufrufe | `https://api.dreamlabs.ai` |
| `DREAM_DATA_URL` | Dienst für Datensätze und Fine-Tuning-Jobs | `https://data.dreamlabs.ai` |

`.env` bleibt lokal. `.env.template` kann mit dem Projekt geteilt werden.
