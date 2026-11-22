import { BaseEdge, getBezierPath, type EdgeProps } from '@xyflow/react'

const LOOP_CLEARANCE = 70
const STUB = 24
const SAME_ROW_TOLERANCE = 90

/**
 * Normal: Bezier-Kurve. Rückkante auf etwa gleicher Höhe (Schleife): Weg über die Blöcke
 * hinweg, damit sie nicht hinter den Blöcken verschwindet.
 */
export function SmartEdge(props: EdgeProps) {
  const { sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, style, id } = props

  const isBackward = targetX < sourceX - STUB
  const sameRow = Math.abs(targetY - sourceY) < SAME_ROW_TOLERANCE
  if (!(isBackward && sameRow)) {
    const [path] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition })
    return <BaseEdge id={id} path={path} markerEnd={markerEnd} style={style} />
  }

  const top = Math.min(sourceY, targetY) - LOOP_CLEARANCE
  const right = sourceX + STUB
  const left = targetX - STUB
  const r = 10
  const path = [
    `M ${sourceX},${sourceY}`,
    `L ${right - r},${sourceY}`,
    `Q ${right},${sourceY} ${right},${sourceY - r}`,
    `L ${right},${top + r}`,
    `Q ${right},${top} ${right - r},${top}`,
    `L ${left + r},${top}`,
    `Q ${left},${top} ${left},${top + r}`,
    `L ${left},${targetY - r}`,
    `Q ${left},${targetY} ${left + r},${targetY}`,
    `L ${targetX},${targetY}`,
  ].join(' ')

  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={markerEnd}
      style={{ ...style, strokeDasharray: '6 4' }}
      label="loop"
      labelX={(left + right) / 2}
      labelY={top}
      labelStyle={{ fontSize: 11, fontWeight: 600, fill: '#334155' }}
      labelBgStyle={{ fill: '#f8fafc' }}
      labelBgPadding={[4, 2]}
    />
  )
}
