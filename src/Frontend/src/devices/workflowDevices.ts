import { useMemo } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { Device } from '@/api/contract'
import type { FlowNode } from '@/workflow/flow'
import { useEditor } from '@/workflow/store'

/** IDs der Geräte, auf die Sensor- und Aktor-Blöcke verweisen (auch ungespeicherter Editor-Stand). */
export function workflowDeviceIds(nodes: readonly FlowNode[]): Set<string> {
  const ids = new Set<string>()
  for (const node of nodes) {
    if ((node.type === 'waitSensor' || node.type === 'condition' || node.type === 'setActuator') && node.data.deviceId !== '') {
      ids.add(node.data.deviceId)
    }
  }
  return ids
}

/** Geräte des Workflows in der Reihenfolge der Geräteliste; unbekannte IDs fallen weg. */
export function devicesInWorkflow(devices: readonly Device[], ids: ReadonlySet<string>): Device[] {
  return devices.filter((d) => ids.has(d.id))
}

export function useWorkflowDeviceIds(): Set<string> {
  const ids = useEditor(useShallow((s) => [...workflowDeviceIds(s.nodes)].sort()))
  return useMemo(() => new Set(ids), [ids])
}
