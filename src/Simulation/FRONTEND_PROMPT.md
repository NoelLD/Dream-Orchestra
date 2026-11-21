# Prompt: Frontend an den Simulations-Dienst anbinden

> Für Claude Code (oder ein anderes Coding-Tool) in einer frischen Session im Repo `Dream-Orchestra`.
> Den Block unten komplett kopieren.

```text
Du arbeitest im Repo Dream-Orchestra (Hackathon "Dream Labs Track", Abgabe So 16:30). Ich baue das Frontend
(src/Frontend, Nginx auf http://localhost:8080). Bitte binde die Simulation an. Ändere nichts in src/Simulation
und nichts im Backend ohne Rückfrage – diese Teile bauen andere.

Lies zuerst:
1. src/Simulation/README.md – der API-Vertrag des Simulations-Dienstes (FastAPI, Port 3001).
2. Die laufende API-Doku: http://localhost:3001/docs (Dienst starten mit `docker compose up -d --build simulation`).
3. Die Testkonsole http://localhost:3001/demo und ihren Quelltext src/Simulation/app/static/demo.html –
   eine Referenz-Implementierung aller Aufrufe (kein Produkt-Design, nur zum Abschauen).

Was die Simulation kann:
- Ein Skill-Lauf (z. B. "pick-banana") lässt Dream-1 zwei YAM-Roboterarme in MuJoCo steuern. Die Simulation
  entscheidet, ob er geklappt hat (Dream-1 selbst meldet keinen Erfolg).
- Modus "mock" = geskripteter Ablauf ohne API-Kosten. Muss in der Oberfläche deutlich als "SIMULIERTE API"
  erkennbar sein. Modus "dream" = echte Dream-1-API, kostet Credits.
- Mehrere Versuche pro Lauf (max_attempts, recovery_prompts), Budget-Grenze, Serien-Evaluation mit Erfolgsquote.

Bitte baue (Anforderungen aus Konzept.md / Orchestrierungsanforderungen.md in Klammern):
1. Live-Kachel: GET http://localhost:3001/frame.jpg alle 300–500 ms neu laden (F16). Ist ein Lauf aktiv,
   zeigt sie sein aktuelles Kamerabild.
2. Prompt-Block ausführen (F5/F6): POST /runs mit {skill, prompt, mode, checkpoint, timeout_s, max_attempts,
   recovery_prompts}; Antwort 202 {run_id}. Dann GET /runs/{run_id} jede Sekunde, bis status terminal ist:
   succeeded | failed | timeout | stopped | error. Zwischenstatus: queued, warming (Modell startet, kann dauern),
   running, finalizing. Aktiven Block hervorheben, Status + Versuche (attempts[]) anzeigen.
3. Stopp-Knopf, immer sichtbar (F7): POST /runs/{run_id}/stop. Endet nach max. ~2 s mit status "stopped".
4. Ablaufprotokoll (F14): pro Lauf Zeitstempel, Skill, Status, success, api_calls, cost_usd, duration_s,
   error. Nach Ende das Video: GET /runs/{run_id}/video (MP4).
5. Credit-Zähler (F15): GET /budget → {budget_usd, spent_usd, remaining_usd}. Vor dem Start schätzen:
   Prompt-Blöcke × max_attempts × ~20 Aufrufe × 0,0014 $. Bei 402 "budget_exhausted" klar anzeigen.
6. Evaluations-Ansicht: GET /evals (Liste), GET /evals/{eval_id} → summary[] pro Variante mit success_rate,
   ci95 [unten, oben], first_attempt_rate, cost_per_success_usd. Darstellen als Punkt mit Intervall-Linie
   pro Variante (0–100 %), dazu "nur 1. Versuch" als zweiter Marker; immer mit dem Hinweis
   "gemessen in der Simulation, kleine Stichprobe".
7. Skill-Auswahl aus GET /skills (name, description, default_prompt, success_check, mock_available).

Regeln:
- Fehler kommen als {"error": "<code>", "detail": "<Text>"} (400/402/404/409/501/502/503) – nie abstürzen,
  im Protokoll anzeigen. 409 "busy" = es läuft schon ein Lauf (active_run_id mitgeliefert).
- Es läuft immer nur ein Lauf gleichzeitig; Evaluationen belegen den Lauf-Slot.
- Der API-Key existiert nur im Simulations-Container (.env). Niemals im Frontend, in URLs oder im Log.
- CORS ist für http://localhost:8080 und http://127.0.0.1:8080 freigegeben. Andere Origins:
  SIM_CORS_ORIGINS im Simulations-Dienst setzen lassen.
- Basis-URL konfigurierbar machen (Standard http://localhost:3001), nicht hart verdrahten.

Arbeitsweise: Erst lesen und mir einen kurzen Plan zeigen (welche Dateien, welche Komponenten), dann bauen.
Teste gegen den laufenden Dienst mit mode "mock" (kostenlos); "dream" nur nach meiner Freigabe.
Nicht committen oder pushen ohne meinen Auftrag.
```
