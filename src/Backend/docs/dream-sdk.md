# Dream-Labs-SDK (`dreamlabs-client==1.1.7`, Import `dream`)

Im Backend-Container untersucht (`inspect.signature`, Docstrings). Nichts hier ist geraten; was unklar ist, steht unter
„Offene Fragen“. Das Backend ruft die SDK **derzeit nicht direkt** auf, siehe „Folge für das Backend“.

## Aufbau

- `dream.DreamClient(api_key=None)` – eine Fassade für alles; Key aus Argument, sonst `DREAM_API_KEY` bzw.
  `~/.dreamlabs/credentials`. Untermodule: `dream.datasets`, `dream.fine_tuning`, `dream.models`.
- Fehler (alle erben von `dream.DreamError`): `DreamConfigError`, `DreamAuthError`, `DreamBadRequest`,
  `DreamServerError` (`code`, `reason`, `retryable`, `retry_after_s`), `DreamSessionExpired`, `DreamTimeout`,
  `DreamProtocolError`, `DreamObservationError`, `DreamActionError`; nur beim Upload `dream.errors.DreamDatasetError`,
  `DreamUploadError`.

## Modelle

| Aufruf | Rückgabe | Kosten |
|---|---|---|
| `dream.models.list_models(*, api_key=None)` / `client.get_models()` | `list[Model]` (`id`, `owner` public/mine, `base_model`, `embodiment`, `servable`, `created_at`, `cameras`) | keine (Katalog) |

Checkpoint-IDs: `dreamlabs/dream-1-beta` (öffentlich), Fine-Tunes `dream-1-ft:<uid8>-<suffix>`.

## Inferenz (Ausführung)

| Aufruf | Zweck |
|---|---|
| `client.policy(config: dict)` | Modell wählen; `config["checkpoint"]` Pflicht, optional `embodiment`, `strict`, `timeout_ms` (15000), `execution_horizon`, `action_hz`, `robot`, `ik`. Sendet nichts. Ein Client hält genau eine Policy. |
| `client.set_observation(frames: Mapping[str, str], observation: Mapping[str, Any], *, timestamp=None)` | Jeder Kamera-Tick: `frames` = `video.<rolle>` → base64-JPEG; `observation` = `state.<teil>` + `prompt`. Kein Netz. |
| `client.get_action(*, commanded=None) -> dict` | Fragt den nächsten Aktions-Chunk ab (Fine-Tune: `per_key` mit `action.<teil>`, 48 Zeilen ≈ 1,6 s; YAM: `q_r_chunk`/`q_l_chunk`). Erster Aufruf öffnet die Sitzung, ggf. `DreamServerError` `pool_warming` → `retry_after_s` warten. |
| `client.refill_due(executed, remaining) -> bool` | Pacing: wann der nächste `get_action()` fällig ist. |
| `client.reset_episode()` / `client.close()` | Episode beenden / Sitzung freigeben. |

**Wichtig:** Es gibt **keinen** „Lauf mit Status“. `get_action()` meldet weder Erfolg noch Ende; Erfolg, Zeitlimit
und Stopp müssen von außen kommen (Simulation).

Kosten: jeder `get_action()` ist ein abgerechneter Aufruf. Laut Simulations-README ca. 0,0014 $ (Basis) bzw.
0,0028 $ (Fine-Tune) pro Aufruf – an der Abrechnung noch zu prüfen.

## Training

| Aufruf | Zweck | Kosten |
|---|---|---|
| `client.add_embodiment(name, config) -> Embodiment` | Roboterkörper registrieren (`state`, `action`, `video`) | keine bekannt |
| `client.validate_dataset(path, config) -> Report` | Lokale Prüfung (LeRobot v2.1/v3.x, Videos via FFmpeg) | lokal |
| `client.upload_dataset(path, name, embodiment) -> Dataset` | Zip nach S3, Status `ready_to_process` → `processing` → `processed`/`failed`; braucht Extra `[datasets]` | laut Sim-README kostenlos |
| `client.get_dataset_status(id)`, `get_datasets()`, `retry_dataset(id)` | Status abfragen | keine |
| `client.finetune(dataset, suffix, *, steps=None, learning_rate=None, batch_size=None, use_eef=False, lr_schedule=None, resume_from=None, base_share=None) -> dict` | Job queuen; `steps` 500–10000 in 100er-Schritten (Standard 1000) | **kostet**; laut Sim-README 0,20 $/Step |
| `client.get_finetuning_status(job_id) -> dict` | `status` queued/running/succeeded/failed/cancelled, `fine_tuned_model` sobald fertig | keine |
| `dream.fine_tuning.cancel(job_id)` | Abbruch; laut Docstring wird ein gequeueter Job meist mit `conflict` abgelehnt | – |

## Folge für das Backend

Der Simulationsdienst (`src/Simulation`, Branch `simulation-api`) kapselt die SDK: Steuerschleife mit
`set_observation`/`get_action`, Erfolgsprüfung, Zeitlimit, Stopp, sowie Datasets und Fine-Tuning. Das Backend
spricht daher per HTTP mit ihm (`app/dream/simulation.py`) und nicht mit der SDK. Direkte SDK-Aufrufe im Backend nur
wie hier belegt.

## Offene Fragen

1. Exakter Preis pro `get_action()` und pro Fine-Tune-Step (Zahlen stammen aus dem Simulations-README).
2. Kostet `add_embodiment` oder `upload_dataset` etwas?
3. Wie lange dauert `pool_warming` bei Fine-Tunes realistisch (Sim-README: „bis zu 1 h“)?
