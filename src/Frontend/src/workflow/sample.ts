import type { WorkflowDocument } from '@/api/contract'

/** Demo-Ablauf Pick-and-Place: Start → Greifen → Warte auf Sensor → Bedingung (Schleife) → Ende */
export const SAMPLE_WORKFLOW: WorkflowDocument = {
  schemaVersion: 1,
  name: 'Pick-and-Place (Demo)',
  nodes: [
    { id: 'start', type: 'start', position: { x: 0, y: 20 }, data: {} },
    {
      id: 'greifen',
      type: 'prompt',
      position: { x: 180, y: 0 },
      data: { label: 'Greifen', prompt: 'Greife das Werkstück und lege es in die Kiste', skillId: null, timeoutS: 60, retries: 1 },
    },
    {
      id: 'sensor',
      type: 'waitSensor',
      position: { x: 430, y: 0 },
      data: { label: 'Objekt in Kiste?', deviceId: 'lichtschranke', operator: 'eq', value: true, timeoutS: 30 },
    },
    {
      id: 'weiter',
      type: 'condition',
      position: { x: 680, y: 0 },
      data: { label: 'Weitere Objekte?', deviceId: 'weitere-objekte', operator: 'eq', value: true },
    },
    { id: 'ende', type: 'end', position: { x: 930, y: 20 }, data: {} },
    {
      id: 'stoerung',
      type: 'setActuator',
      position: { x: 430, y: 190 },
      data: { label: 'Störung melden', deviceId: 'lampe-rot', value: true },
    },
    { id: 'abbruch', type: 'end', position: { x: 680, y: 205 }, data: { label: 'Abbruch' } },
  ],
  edges: [
    { id: 'e-start-greifen', source: 'start', target: 'greifen', sourceHandle: 'out' },
    { id: 'e-greifen-sensor', source: 'greifen', target: 'sensor', sourceHandle: 'out' },
    { id: 'e-greifen-stoerung', source: 'greifen', target: 'stoerung', sourceHandle: 'error' },
    { id: 'e-sensor-weiter', source: 'sensor', target: 'weiter', sourceHandle: 'out' },
    { id: 'e-sensor-stoerung', source: 'sensor', target: 'stoerung', sourceHandle: 'error' },
    { id: 'e-weiter-greifen', source: 'weiter', target: 'greifen', sourceHandle: 'true' },
    { id: 'e-weiter-ende', source: 'weiter', target: 'ende', sourceHandle: 'false' },
    { id: 'e-stoerung-abbruch', source: 'stoerung', target: 'abbruch', sourceHandle: 'out' },
  ],
}

/** Ausgangspunkt für „Neu“: Start → Ende (gültig, sofort lauffähig). */
export const EMPTY_WORKFLOW: WorkflowDocument = {
  schemaVersion: 1,
  name: 'Neuer Workflow',
  nodes: [
    { id: 'start', type: 'start', position: { x: 0, y: 40 }, data: {} },
    { id: 'ende', type: 'end', position: { x: 320, y: 40 }, data: {} },
  ],
  edges: [{ id: 'e-start-ende', source: 'start', target: 'ende', sourceHandle: 'out' }],
}

const LOAD = 'put the metal block on the machine tray'
const UNLOAD = 'put the finished part in the green box'

/**
 * CNC-Zyklus in der simulierten Zelle (Backend-Modus sim/real): Prompt-Blöcke mit genau dem Task-Prompt laufen über
 * /cells mit dem geskripteten Referenz-Controller (keine Credits); Zellen-Geräte spiegeln Sensoren und schalten Aktionen.
 */
export const CNC_WORKFLOW: WorkflowDocument = {
  schemaVersion: 1,
  name: 'CNC-Zyklus (Zelle)',
  nodes: [
    { id: 'start', type: 'start', position: { x: 0, y: 20 }, data: {} },
    { id: 'laden', type: 'prompt', position: { x: 160, y: 0 }, data: { label: 'Rohteil laden', prompt: LOAD, skillId: null, timeoutS: 120, retries: 0 } },
    { id: 'zyklus', type: 'setActuator', position: { x: 400, y: 0 }, data: { label: 'Maschine starten', deviceId: 'zelle-cnc-maschine', value: true } },
    { id: 'fertig', type: 'waitSensor', position: { x: 620, y: 0 }, data: { label: 'Bearbeitung fertig?', deviceId: 'zelle-maschine-fertig', operator: 'eq', value: true, timeoutS: 90 } },
    { id: 'entladen', type: 'prompt', position: { x: 860, y: 0 }, data: { label: 'Fertigteil entladen', prompt: UNLOAD, skillId: null, timeoutS: 120, retries: 0 } },
    { id: 'gruen', type: 'setActuator', position: { x: 1100, y: 0 }, data: { label: 'Ampel grün', deviceId: 'zelle-ampel-gruen', value: true } },
    { id: 'ende', type: 'end', position: { x: 1320, y: 20 }, data: {} },
    { id: 'rot', type: 'setActuator', position: { x: 620, y: 200 }, data: { label: 'Störung: Ampel rot', deviceId: 'zelle-ampel-rot', value: true } },
    { id: 'abbruch', type: 'end', position: { x: 860, y: 215 }, data: { label: 'Abbruch' } },
  ],
  edges: [
    { id: 'e1', source: 'start', target: 'laden', sourceHandle: 'out' },
    { id: 'e2', source: 'laden', target: 'zyklus', sourceHandle: 'out' },
    { id: 'e3', source: 'zyklus', target: 'fertig', sourceHandle: 'out' },
    { id: 'e4', source: 'fertig', target: 'entladen', sourceHandle: 'out' },
    { id: 'e5', source: 'entladen', target: 'gruen', sourceHandle: 'out' },
    { id: 'e6', source: 'gruen', target: 'ende', sourceHandle: 'out' },
    { id: 'f1', source: 'laden', target: 'rot', sourceHandle: 'error' },
    { id: 'f2', source: 'fertig', target: 'rot', sourceHandle: 'error' },
    { id: 'f5', source: 'zyklus', target: 'rot', sourceHandle: 'error' },
    { id: 'f3', source: 'entladen', target: 'rot', sourceHandle: 'error' },
    { id: 'f4', source: 'rot', target: 'abbruch', sourceHandle: 'out' },
  ],
}

/** Kontrollierter Fehler: Entladen ohne Fertigteil -> die Zelle sperrt -> Fehlerpfad, Ampel rot. */
export const CNC_FAILURE_WORKFLOW: WorkflowDocument = {
  schemaVersion: 1,
  name: 'CNC-Zyklus: Fehlerfall',
  nodes: [
    { id: 'start', type: 'start', position: { x: 0, y: 20 }, data: {} },
    { id: 'entladen', type: 'prompt', position: { x: 160, y: 0 }, data: { label: 'Entladen ohne Fertigteil', prompt: UNLOAD, skillId: null, timeoutS: 60, retries: 0 } },
    { id: 'ende', type: 'end', position: { x: 420, y: 20 }, data: {} },
    { id: 'rot', type: 'setActuator', position: { x: 420, y: 190 }, data: { label: 'Störung: Ampel rot', deviceId: 'zelle-ampel-rot', value: true } },
    { id: 'abbruch', type: 'end', position: { x: 660, y: 205 }, data: { label: 'Abbruch' } },
  ],
  edges: [
    { id: 'e1', source: 'start', target: 'entladen', sourceHandle: 'out' },
    { id: 'e2', source: 'entladen', target: 'ende', sourceHandle: 'out' },
    { id: 'f1', source: 'entladen', target: 'rot', sourceHandle: 'error' },
    { id: 'f2', source: 'rot', target: 'abbruch', sourceHandle: 'out' },
  ],
}

export const SAMPLES = [
  { id: 'pick', label: 'Pick-and-Place (Demo)', doc: SAMPLE_WORKFLOW },
  { id: 'cnc', label: 'CNC-Zyklus (Zelle)', doc: CNC_WORKFLOW },
  { id: 'cnc-fehler', label: 'CNC-Zyklus: Fehlerfall', doc: CNC_FAILURE_WORKFLOW },
] as const
