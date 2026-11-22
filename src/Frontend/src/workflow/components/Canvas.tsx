import '@xyflow/react/style.css'
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  useReactFlow,
  type EdgeTypes,
  type NodeTypes,
  type OnSelectionChangeParams,
} from '@xyflow/react'
import { useCallback, type DragEvent } from 'react'
import type { WorkflowNodeType } from '@/api/contract'
import { BLOCKS, DND_MIME } from '../blocks'
import type { FlowEdge, FlowNode } from '../flow'
import { useEditor } from '../store'
import { BlockNode } from './BlockNode'
import { SmartEdge } from './SmartEdge'

const nodeTypes = {
  start: BlockNode,
  prompt: BlockNode,
  waitSensor: BlockNode,
  setActuator: BlockNode,
  wait: BlockNode,
  condition: BlockNode,
  end: BlockNode,
} satisfies NodeTypes

const edgeTypes = { default: SmartEdge } satisfies EdgeTypes

const isBlockType =(value: string): value is WorkflowNodeType => value in BLOCKS

export function Canvas() {
  const nodes = useEditor((s) => s.nodes)
  const edges = useEditor((s) => s.edges)
  const onNodesChange = useEditor((s) => s.onNodesChange)
  const onEdgesChange = useEditor((s) => s.onEdgesChange)
  const onConnect = useEditor((s) => s.onConnect)
  const addBlock = useEditor((s) => s.addBlock)
  const select = useEditor((s) => s.select)
  const { screenToFlowPosition } = useReactFlow<FlowNode, FlowEdge>()

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault()
      const type = event.dataTransfer.getData(DND_MIME)
      if (!isBlockType(type)) return
      addBlock(type, screenToFlowPosition({ x: event.clientX - 110, y: event.clientY - 30 }))
    },
    [addBlock, screenToFlowPosition],
  )

  const onSelectionChange = useCallback(
    ({ nodes: selected }: OnSelectionChangeParams<FlowNode, FlowEdge>) => select(selected[0]?.id ?? null),
    [select],
  )

  return (
    <div className="h-full w-full" data-testid="canvas">
      <ReactFlow<FlowNode, FlowEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onSelectionChange={onSelectionChange}
        isValidConnection={(c) => c.source !== c.target}
        deleteKeyCode={['Delete', 'Backspace']}
        forceColorMode="light"
        fitView
        fitViewOptions={{ padding: '24px', maxZoom: 1.1 }}
        minZoom={0.3}
        aria-label="Workflow-Editor"
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
        <Controls position="bottom-left" />
      </ReactFlow>
    </div>
  )
}
