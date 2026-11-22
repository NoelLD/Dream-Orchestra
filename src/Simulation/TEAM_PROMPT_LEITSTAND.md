# Prompt: Leitstand (Steuerungszentrale) für die zwei Zellen-Experimente

> Für Claude Code in einer frischen Session im Repo `Dream-Orchestra`, Branch `master`. Block komplett kopieren.
> Simulations-API: Branch `simulation-api` (`git show origin/simulation-api:src/Simulation/README.md`).

```text
Du arbeitest im Repo Dream-Orchestra (Hackathon "Dream Labs Track", Abgabe heute 16:30). Baue im Frontend einen Tab
"Leitstand": die Steuerungszentrale der Demo. Ändere nichts in src/Simulation. Backend nur als dünner Durchgriff
(wie src/Backend/app/api/simulation.py). Stil wie die bestehenden Ansichten.

Worum es geht: Zwei Experimente in der MuJoCo-Simulation, je eine eigene Zelle:
  1. "Fließband": Band fördert Alu-Rohlinge bis zur Lichtschranke, der Roboter legt sie in eine blaue KLT-Kiste.
  2. "CNC": Maschine mit Hubtür, Übergabeplatte und Ampel. Roboter legt Rohteil auf die Platte -> Prüfung ->
     Zyklus (Tür zu, Platte rein, Ampel gelb, Fertigteil raus, Tür auf, Ampel grün) -> Roboter legt Fertigteil ab.
Kernidee für die Jury: Dream-1 liefert nur Bewegungen. Die Simulation MISST, ob der Griff geklappt hat und ob der Arm
die Zelle berührt hat. Erst dann gibt der Leitstand den nächsten Schritt frei (grün), sonst rot und Stopp.

Simulations-API (Port 3001; Backend reicht durch unter /api/cells/...):
- GET  /cells                              -> [{cell, tasks:[{task, arm, prompt}]}]   cells: "conveyor", "cnc"
- POST /cells/{cell}/session               -> startet die Live-Zelle (vorherige wird beendet)
- GET  /cells/session                      -> {cell, status, sim_seconds, busy, sensors{...}, last_result, events[]}
    sensors conveyor: part_at_light_barrier, belt_on
    sensors cnc: door_open, door_closed, tray_out, tray_in, raw_part_on_tray, finished_part_on_tray,
                 machine_running, machine_done, stack_light ("red"|"yellow"|"green"|null), cycles
- POST /cells/session/action {action}      -> door_open | door_close | belt_on | belt_off | cycle_start |
                                              light_red | light_yellow | light_green | light_off
- POST /cells/session/task {task, seed}    -> belt_to_klt (Fließband) | cnc_load | cnc_unload (CNC)
- GET  /cells/session/frame.jpg?view=overview|robot   (Live-Bild, alle 150–250 ms neu laden)
- DELETE /cells/session

Layout (1280 px, eine Seite, kein Scrollen auf Desktop):
- Oben: Umschalter Fließband | CNC (startet die Session), Status-Badge, Simulationszeit.
- Mitte links groß: Übersichtskamera. Rechts daneben klein: Roboterkamera mit Beschriftung "Was das Modell sieht".
- Rechts: Anlagen-Schema mit Live-Signalen als Lampen/Schalter: Lichtschranke, Band an/aus, Tür (offen/zu/fährt),
  Platte (draußen/drin), Ampel (echte Farbe), Rohteil/Fertigteil auf Platte, Zyklen-Zähler.
  Aktoren sind Knöpfe (Tür auf/zu, Band an/aus, Zyklus starten) -> man kann eingreifen und sehen, was passiert.
- Unten: Task-Knöpfe (z. B. "Rohteil auf Platte legen") + Ergebnis-Karte der letzten Prüfung: bestanden/nicht,
  Grund, Kontakte (collisions), Hubhöhe, Greif-Abweichung. Daneben das Ereignis-Protokoll (events, neueste oben).
- Immer sichtbar: "Bewegung: geskripteter Referenz-Controller (kein Dream-1)" solange mode = mock.
  Grün/Rot der Freigabe groß und eindeutig. Gesperrter Zyklus (z. B. "kein Rohteil auf der Platte") deutlich zeigen.

Demo-Choreografie (für die Live-Demo, 3 min): CNC wählen -> "Zyklus starten" ohne Teil -> ROT, gesperrt (der
Leitstand verhindert Unsinn) -> "Rohteil auf Platte legen" -> Prüfung grün -> "Zyklus starten" -> Tür zu, gelb,
Fertigteil kommt raus -> "Fertigteil ablegen". Dann Fließband: Lichtschranke schaltet, Band stoppt, Teil in die KLT.

Technik: React Query mit Polling (state 300 ms, Bilder 200 ms), Fehler als Toast, Mock-Client mit festen Beispielwerten
im Testmodus (klar als "SIMULIERTE API" markiert). pnpm check grün, Screenshot bei 1280 px.
```
