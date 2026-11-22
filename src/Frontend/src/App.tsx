import { ReactFlowProvider } from '@xyflow/react'
import { CellsView } from '@/cells/CellsView'
import { AppHeader, MockBanner } from '@/components/AppHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DeviceBar } from '@/devices/DeviceBar'
import { DevicesView } from '@/devices/DevicesView'
import { RunLog } from '@/run/RunLog'
import { ResultsView } from '@/results/ResultsView'
import { useRunPolling } from '@/run/useRun'
import { SkillsView } from '@/skills/SkillsView'
import { Canvas } from '@/workflow/components/Canvas'
import { CellLive } from '@/workflow/components/CellLive'
import { Palette } from '@/workflow/components/Palette'
import { PropertiesPanel } from '@/workflow/components/PropertiesPanel'
import { Toolbar } from '@/workflow/components/Toolbar'

function WorkflowEditor({ pollError }: { pollError: Error | null }) {
  return (
    <ReactFlowProvider>
      <div className="grid h-full min-h-0 grid-rows-[auto_1fr_220px]">
        <Toolbar />
        <div className="grid min-h-0 grid-cols-[180px_1fr_270px]">
          <div className="min-h-0 border-r bg-slate-50">
            <Palette />
          </div>
          <div className="min-h-0">
            <Canvas />
          </div>
          <div className="min-h-0 border-l bg-slate-50">
            <PropertiesPanel />
          </div>
        </div>
        <div className="flex min-h-0 border-t bg-white">
          <div className="min-h-0 min-w-0 flex-1">
            <RunLog pollError={pollError} />
          </div>
          <CellLive />
          <div className="min-h-0 w-[400px] shrink-0 border-l">
            <DeviceBar />
          </div>
        </div>
      </div>
    </ReactFlowProvider>
  )
}

export default function App() {
  const poll = useRunPolling()

  return (
    <div className="flex h-dvh min-w-[1200px] flex-col bg-slate-100 text-slate-900">
      <AppHeader />
      <MockBanner />
      <Tabs defaultValue="editor" className="flex min-h-0 flex-1 flex-col gap-0">
        <TabsList className="mx-3 mt-2">
          <TabsTrigger value="editor">Workflow editor</TabsTrigger>
          <TabsTrigger value="cells">Cell control</TabsTrigger>
          <TabsTrigger value="devices">Devices</TabsTrigger>
          <TabsTrigger value="skills">Skills</TabsTrigger>
          <TabsTrigger value="results">Robot &amp; Fine-tune</TabsTrigger>
        </TabsList>
        <TabsContent value="editor" className="mt-2 min-h-0 flex-1 border-t bg-white">
          <WorkflowEditor pollError={poll.error} />
        </TabsContent>
        <TabsContent value="devices" className="min-h-0 flex-1 overflow-auto">
          <DevicesView />
        </TabsContent>
        <TabsContent value="skills" className="min-h-0 flex-1 overflow-auto">
          <SkillsView />
        </TabsContent>
        <TabsContent value="cells" className="min-h-0 flex-1 overflow-auto">
          <CellsView />
        </TabsContent>
        <TabsContent value="results" className="min-h-0 flex-1 overflow-auto">
          <ResultsView />
        </TabsContent>
      </Tabs>
    </div>
  )
}
