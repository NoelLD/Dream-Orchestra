# Prompt: Tab "Training" mit Erfolgsprüfung (Fine-Tune pro Roboter, vorher/nachher messen)

> Für Claude Code (oder ein anderes Coding-Tool) in einer frischen Session im Repo `Dream-Orchestra`, Branch `master`.
> Abgeglichen mit `origin/master` 7609716 und dem Simulationsdienst auf Branch `simulation-api`. Block komplett kopieren.

```text
Du arbeitest im Repo Dream-Orchestra (Hackathon "Dream Labs Track", Abgabe So 16:30). Ändere nichts in
src/Simulation (baut jemand anderes). Lies zuerst docs/api-contract.md, src/Backend/app/api/training.py,
src/Frontend/src/skills/SkillsView.tsx (Vorlage für Aufbau und Stil) und src/Simulation/README.md
(Abschnitte "GET /robots", "Evaluation: POST /evals", "Datasets und Fine-Tuning"). Falls src/Simulation auf
master noch alt ist: `git show origin/simulation-api:src/Simulation/README.md`.

Ziel: Ein neuer Tab "Training" zeigt die Geschichte "messen → fine-tunen → wieder messen". Dream-1 meldet keinen
Erfolg – der Simulationsdienst misst ihn (Objekt angehoben/abgelegt laut MuJoCo) und vergleicht Varianten auf
denselben Testszenen (gepaarte Seeds < 1000; Trainingsdaten haben Seeds >= 1000).
Ein Fine-Tune gehört zum ROBOTERTYP, nicht zum Skill (Dream Labs: "Fine-tuning is for new robots, not for
automating a task"). Der Checkpoint eines Roboters gilt für alle seine Skills.

1) Backend (dünner Durchgriff wie in app/api/training.py, Bodies/Antworten unverändert weiterreichen):
   - GET /api/training/robots, GET /api/training/robots/{name}         → Sim GET /robots, /robots/{name}
   - GET /api/training/evals, GET /api/training/evals/{eval_id}       → Sim GET /evals, /evals/{id}
   - POST /api/training/evals (202), POST /api/training/evals/{id}/stop → Sim POST /evals, /evals/{id}/stop
   - FinetuneBody-Beispiel um "robot": "yam-sim" ergänzen (Sim-Feld, optional, Standard yam-sim).
   - Test mit Fake-Transport wie tests/test_simulation_client.py. docs/api-contract.md ergänzen.

2) Frontend: Tab "Training" neben "Skills" (App.tsx), Datei src/training/TrainingView.tsx. ApiClient in
   contract.ts erweitern (listRobots, listDatasets, listEvals, getEval, startEval, stopEval, listFinetunes,
   getFinetune, startFinetune), realClient + mockClient (Mock mit festen Beispieldaten unten, klar als
   "SIMULIERTE API" markiert wie bisher). Drei Karten untereinander:

   a) Roboter: Name, Embodiment, Kameras, Skills, aktiver Checkpoint (null → "Basismodell"), Fine-Tune-Jobs mit
      Status und Fortschritt (GET /finetune/{job_id} alle 30 s, solange queued/running; progress.step/total_steps,
      loss). Knopf "Fine-Tune starten" öffnet Dialog: Dataset (nur status == "processed" aus /datasets), Steps
      (500–10000, Schritt 100), lr_schedule (cosine Standard). Preis groß anzeigen (steps × 0,20 $), Hinweis
      "nicht abbrechbar, Credits werden reserviert", Checkbox "Ich bestätige X $" – erst dann aktiv; Body enthält
      confirm_cost_usd = Preis. Fehler 400 cost_not_confirmed / 409 dataset_not_ready / 502 als Toast.

   b) Datasets: Tabelle Name, Status (generating → validated → uploading → processing → processed | failed),
      Episoden, Frames, Dream-Status. Nur Anzeige (Erzeugen läuft über Modal vom Host aus).

   c) Erfolgsprüfung (Evaluation) – das Herzstück:
      - Formular: Skill (aus /api/skills), Testszenen (trials, Standard 10), Zeitlimit (timeout_s 30), Varianten
        als Zeilen: Label, Checkpoint (Auswahl: "dreamlabs/dream-1-beta", "dreamlabs/dream-1-beta-flash" und der
        aktive Checkpoint des Roboters), max_attempts (1–5). Vorlage-Knopf "Vorher/Nachher": base-1x (Basismodell),
        ft-1x (Roboter-Checkpoint), ft-3x (Roboter-Checkpoint, 3 Versuche). Vor dem Start Kosten schätzen:
        trials × Varianten × ~10 Calls × 0,0014 $ (Fine-Tune 0,0028 $) und anzeigen. mode "dream" kostet Credits,
        "mock" nicht (mock nur für pick-banana/pick-apple).
      - Laufende Evaluation: progress.done/total als Balken, Stop-Knopf, Polling alle 3 s bis status terminal.
      - Ergebnis pro Variante (summary[]): Erfolgsquote "8/10" + Balken mit 95-%-Intervall (ci95 als Fehlerbalken,
        nicht nur der Punkt), first_attempt_rate, cost_per_success_usd, api_calls, errors. Beste Variante hervorheben
        NUR wenn sich die Intervalle nicht überlappen; sonst Hinweis "Unterschied bei n=10 nicht belastbar".
      - Immer sichtbar: "Simulationsergebnis, kleine Stichprobe – keine Aussage über echte Hardware".
      - Liste früherer Evaluationen (GET /evals), anklickbar.

   Mock-Beispieldaten (echte Messung eval_32886def, pick-banana, Seeds 0–9, Simulation):
     beta-1x 8/10 ci95 [0.49, 0.943] cost_per_success 0.0154 · beta-3x 7/10 [0.397, 0.892] 0.0294 (1 error) ·
     flash-1x 10/10 [0.722, 1.0] 0.0064. Robot yam-sim, fine_tuned_model null.

3) Prüfen: pnpm check, Vitest für Kostenrechnung und Intervall-Überlappung, ruff/mypy/pytest im Backend-Container,
   Screenshot bei 1280 px. Nie behaupten, ein Fine-Tune sei besser, bevor eine Evaluation es zeigt.
```
