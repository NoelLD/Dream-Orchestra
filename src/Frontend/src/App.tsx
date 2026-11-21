import { ReactFlowProvider } from '@xyflow/react'
import { AppHeader, MockBanner } from '@/components/AppHeader'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DeviceBar } from '@/devices/DeviceBar'
import { DevicesView } from '@/devices/DevicesView'
import { RunLog } from '@/run/RunLog'
import { useRunPolling } from '@/run/useRun'
import { SkillsView } from '@/skills/SkillsView'
import { Canvas } from '@/workflow/components/Canvas'
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
        <div className="grid min-h-0 grid-cols-[1fr_400px] border-t bg-white">
          <div className="min-h-0 min-w-0">
            <RunLog pollError={pollError} />
          </div>
          <div className="min-h-0 border-l">
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
          <TabsTrigger value="editor">Workflow-Editor</TabsTrigger>
          <TabsTrigger value="devices">Geräte</TabsTrigger>
          <TabsTrigger value="skills">Skills</TabsTrigger>
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
      </Tabs>
    </div>
  )
}
