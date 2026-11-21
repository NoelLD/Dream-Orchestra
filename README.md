# DreamOrchestra

Der Container enthält Python 3.12 und das Dream-Labs-SDK. `src/test_dream_api.py` ruft den Modellkatalog ab und zeigt die SDK-Version und die Anzahl der verfügbaren Checkpoints an.

## Setup

1. Docker starten und in den Ordner mit `compose.yaml` wechseln (`implementierung/`).
2. Falls `.env` fehlt, `.env.template` als `.env` kopieren. Den API-Key als `DREAM_API_KEY` in `.env` eintragen. [Dream-Labs-Plattform](https://platform.dreamlabs.ai/)
3. Image bauen und den Test starten.

   ```sh
   docker compose run --rm --build api-test
   ```

Ohne Compose in PowerShell `./start.ps1` ausführen. Der Quellcode aus `src/` wird beim Build ins Image kopiert. Nach Codeänderungen den Startbefehl erneut ausführen.

## Umgebungsvariablen

Die Werte in `.env` als `NAME=Wert` ohne Anführungszeichen eintragen. Die optionalen URLs nur ändern, wenn Dream Labs für den Zugang andere Adressen vorgibt.

| Variable | Zweck | Standard |
| --- | --- | --- |
| `DREAM_API_KEY` | API-Key für die Authentifizierung | Pflichtfeld |
| `DREAM_API_URL` | Plattform mit dem Modellkatalog. Der Test verwendet diese URL. | `https://platform.dreamlabs.ai` |
| `DREAM_GATEWAY_URL` | Gateway für künftige Inferenzaufrufe | `https://api.dreamlabs.ai` |
| `DREAM_DATA_URL` | Dienst für Datensätze und Fine-Tuning-Jobs | `https://data.dreamlabs.ai` |

`.env` bleibt lokal. `.env.template` kann mit dem Projekt geteilt werden.
