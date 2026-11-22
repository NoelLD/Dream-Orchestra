import { describe, expect, it } from 'vitest'
import { DEFAULT_MOCK_DEVICES } from '@/api/mockClient'
import type { FlowNode } from '@/workflow/flow'
import { devicesInWorkflow, workflowDeviceIds } from './workflowDevices'

const P = { x: 0, y: 0 }
const nodes: FlowNode[] = [
  { id: 's', type: 'start', position: P, data: {} },
  { id: 'w', type: 'waitSensor', position: P, data: { deviceId: 'lichtschranke', operator: 'eq', value: true, timeoutS: null } },
  { id: 'a', type: 'setActuator', position: P, data: { deviceId: '', value: true } },
  { id: 'c', type: 'condition', position: P, data: { deviceId: 'gibtsnicht', operator: 'eq', value: true } },
  { id: 'l', type: 'setActuator', position: P, data: { deviceId: 'lampe', value: true } },
]

describe('Geräte im Workflow', () => {
  it('sammelt die Geräte-IDs der Sensor- und Aktor-Blöcke, leere ignoriert', () => {
    expect(workflowDeviceIds(nodes)).toEqual(new Set(['lichtschranke', 'gibtsnicht', 'lampe']))
  })

  it('filtert die Geräteliste auf den Workflow und ignoriert unbekannte IDs', () => {
    const result = devicesInWorkflow(DEFAULT_MOCK_DEVICES, workflowDeviceIds(nodes))
    expect(result.map((d) => d.id)).toEqual(['lichtschranke', 'lampe'])
    expect(devicesInWorkflow(DEFAULT_MOCK_DEVICES, new Set())).toEqual([])
  })
})
