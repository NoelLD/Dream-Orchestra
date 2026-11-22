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
