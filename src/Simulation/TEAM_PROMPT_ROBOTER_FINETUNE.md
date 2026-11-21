# Prompt: Roboter als eigener Topf (Fine-Tune gehört zum Roboter) + CNC-Demo-Geräte

> Für Claude Code (oder ein anderes Coding-Tool) in einer frischen Session im Repo `Dream-Orchestra`, Branch `master`.
> Abgeglichen mit dem Stand `origin/master` 7609716 (Geräteverwaltung fertig). Den Block unten komplett kopieren.

```text
Du arbeitest im Repo Dream-Orchestra (Hackathon "Dream Labs Track", Abgabe So 16:30). Ändere nichts in
src/Simulation – das baut jemand anderes. Lies zuerst docs/api-contract.md, src/Backend/app/engine/engine.py,
src/Backend/app/schemas/models.py und src/Simulation/README.md.

Entscheidung des Teams (Sa 21.11. abends): Das Konzept sah einen Fine-Tune pro Skill vor. Dream Labs sagt im
offiziellen Tutorial: "Fine-tuning is for new robots, not for automating a task. It teaches Dream-1 your robot's
body." Deshalb gibt es drei Töpfe:

1. Skill/Task = Name + Prompt + Roboter (+ Beschreibung, Status). Ein neuer Task braucht keinen neuen Fine-Tune.
2. Roboter = Name + Embodiment + aktiver Checkpoint (fine_tuned_model). Ein Fine-Tune je Roboter/Zelle, trainiert
   auf Vorführungen aller seiner Tasks (jede Episode mit eigenem Prompt).
3. Geräte = Sensoren/Aktoren – GIBT ES SCHON (Tabelle devices, /api/devices, Ansicht „Geräte“). Nicht umbauen.

Was schon passt und bleiben soll:
- Engine: checkpoint = params.checkpoint or skill.checkpoint (engine.py ~Zeile 219), Status-Lebenszyklus,
  Wiederholungen (retries), sim_timeout_s. Der Simulationsdienst v0.3 ist dazu abwärtskompatibel.
- skills.fine_tuned_model bleibt, wird aber zum optionalen Override (Ausnahmefall: ein Task versagt auf dem
  Roboter-Checkpoint).

Bitte ergänze (klein, abwärtskompatibel, nur CREATE TABLE IF NOT EXISTS / ALTER TABLE ADD COLUMN):
- Tabelle robots (id INTEGER PK, name TEXT UNIQUE, embodiment TEXT, fine_tuned_model TEXT NULL, created_at).
  Startbestand bei leerer Tabelle: name "yam-sim", embodiment "martinkaiser.bln/yam-sim", fine_tuned_model NULL.
  Der Simulationsdienst liefert die Robotertypen schon: GET /robots (name, embodiment, cameras, skills,
  fine_tuned_model, finetune_jobs) und GET /skills hat jetzt "robot". Am einfachsten: "Aus Simulation
  übernehmen" legt auch fehlende Roboter an und übernimmt fine_tuned_model vom Sim-Roboter.
  API /api/robots (GET, POST, PUT /{id}, DELETE /{id} mit 409, solange ein Skill ihn nutzt).
- skills: Spalten robot_id (FK robots, Standard = yam-sim) und default_prompt TEXT. SkillIn/SkillOut erweitern.
  import-simulation übernimmt default_prompt aus GET /skills des Simulationsdienstes.
- Engine: Checkpoint-Reihenfolge params.checkpoint → skill.fine_tuned_model → robot.fine_tuned_model → Basismodell.
  Prompt-Block: leerer Prompt → skill.default_prompt. Ins Protokoll schreiben, welcher Checkpoint benutzt wurde.
  Laufende Workflows nicht stillschweigend auf einen neuen Checkpoint umstellen (Checkpoint beim Laufstart fixieren).
- Training: GET /api/training/finetune/{job_id} – sobald fine_tuned_model gesetzt ist, beim Roboter eintragen
  (nicht mehr beim Skill). Fine-Tune-Knopf in der Roboter-Ansicht, vor dem Start Kosten zeigen und bestätigen
  lassen: 0,20 $ pro Step, mind. 500 Steps = 100 $, nicht abbrechbar (Dienst verlangt confirm_cost_usd).
- Frontend: Tab „Roboter“ (Name, Embodiment, aktiver Checkpoint, Fine-Tune-Status). Skill-Formular: Roboter-Auswahl
  und Standard-Prompt. Mock-Client zieht nach.

CNC-Demo (Praxisbeispiel Maschinenbeschickung) – nur Daten, über die bestehende Geräte-API anlegen:
- Sensor "CNC fertig" (switch), Sensor "CNC Tür offen" (switch, Bestätigung – "fertig" heißt nicht "Tür offen").
- Aktor "CNC Tür" (auf/zu): dafür fehlt ein Aktor-Typ. Vorschlag: Typ `door` (bool, Anzeige auf/zu) ergänzen;
  falls das zu viel ist, vorerst Typ `lamp` mit Namen "CNC Tür" und das offen sagen.
- Beispiel-Workflow "CNC beschicken": Start → Warte auf Sensor cnc-fertig == true (Zeitlimit) → Aktor cnc-tuer = an
  → Warte auf Sensor cnc-tuer-offen == true → Prompt-Block Skill pick-banana (Stellvertreter für "Teil entnehmen")
  → Aktor cnc-tuer = aus → Bedingung weitere-objekte → zurück oder Ende. Fehlerpfad: lampe-rot an, Ende.
- In der Oberfläche/Doku klar sagen: Sicherheit (Türverriegelung, Lichtvorhang, Not-Halt) gehört in eine
  Sicherheitssteuerung, nicht in den Orchestrator; die Geräte hier sind Prozesssignale und simuliert.

Tests: ruff, mypy, pytest im Container (Backend), pnpm check (Frontend). Bestehende Workflows dürfen nicht brechen.
Erfolgsquoten nur gemessen anzeigen (Simulation, mit Intervall) – nie behaupten, der Fine-Tune sei besser, bevor die
Evaluation des Simulationsdienstes (/evals) es zeigt.
```
