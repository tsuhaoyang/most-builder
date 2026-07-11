import { useState } from 'react'
import { useMe, canEdit } from './shared/auth/useMe'
import { ImportModal } from './features/import/ImportModal'
import { WiWorkbench } from './features/wi-workbench/WiWorkbench'
import { LevelSystem } from './features/level-system/LevelSystem'
import { RuleSetViewer } from './features/rule-set/RuleSetViewer'
import { SopPanel } from './features/sop/SopPanel'
import { ExportPanel } from './features/export/Export'
import { UsersPanel } from './features/users/UsersPanel'
import { WorksheetBar } from './features/catalog/WorksheetBar'
import { CatalogPanel } from './features/catalog/CatalogPanel'
import { AppLayout } from './features/layout/AppLayout'
import { MostWorkbenchV3 } from './features/workbench-v3/MostWorkbenchV3'

export default function App() {
  const [tab, setTab] = useState<string>('wi')
  const [importOpen, setImportOpen] = useState(false)
  const { data: me } = useMe()

  const renderContent = () => {
    switch (tab) {
      case 'workbench-v3': return <MostWorkbenchV3 />
      case 'wi':      return <WiWorkbench />
      case 'level':   return <LevelSystem />
      case 'ruleset': return <RuleSetViewer />
      case 'sop':     return <SopPanel />
      case 'export':  return <ExportPanel />
      case 'users':   return <UsersPanel />
      case 'catalog': return <CatalogPanel />
      default:
        return (
          <div className="bg-white rounded-xl border p-6 text-slate-500 text-sm">
            {tab}：功能開發中（待移植自 v3）
          </div>
        )
    }
  }

  return (
    <AppLayout
      activeTab={tab}
      onTabChange={setTab}
      me={me}
      canEdit={canEdit(me)}
      onImportClick={() => setImportOpen(true)}
    >
      {/* WorksheetBar sits above the active feature panel, inside the scrollable main area */}
      <WorksheetBar />
      {importOpen && <ImportModal onClose={() => setImportOpen(false)} />}
      {renderContent()}
    </AppLayout>
  )
}
