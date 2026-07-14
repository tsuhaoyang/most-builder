import { useState, useEffect } from 'react'
import { useMe, canEdit } from './shared/auth/useMe'
import { ImportModal } from './features/import/ImportModal'
import { WiWorkbench } from './features/wi-workbench/WiWorkbench'
import { LevelSystem } from './features/level-system/LevelSystem'
import { RuleSetViewer } from './features/rule-set/RuleSetViewer'
import { UsersPanel } from './features/users/UsersPanel'
import { WorksheetBar } from './features/catalog/WorksheetBar'
import { AppLayout } from './features/layout/AppLayout'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { MostWorkbenchV3 } from './features/workbench-v3/MostWorkbenchV3'
import { CasesPage } from './features/cases/CasesPage'
import { DictionariesPage } from './features/dictionaries/DictionariesPage'
import { WISetBuilderPage } from './features/wi-project/WISetBuilderPage'
import { ErrorBoundary } from './shared/ui/ErrorBoundary'

export default function App() {
  const [tab, setTab] = useState<string>('dashboard')
  const [importOpen, setImportOpen] = useState(false)
  const { data: me } = useMe()

  // Allow CasesPage (and future features) to request a tab switch via custom event
  useEffect(() => {
    const handler = (e: Event) => {
      const target = (e as CustomEvent<string>).detail
      if (target) setTab(target)
    }
    window.addEventListener('ddm:switch-tab', handler)
    return () => window.removeEventListener('ddm:switch-tab', handler)
  }, [])

  const renderContent = () => {
    switch (tab) {
      case 'dashboard':    return <DashboardPage />
      case 'workbench-v3': return <MostWorkbenchV3 />
      case 'wi-project':   return <WISetBuilderPage />
      // 'wi'（WiWorkbench 工時表編輯器）僅由分析案件的「編輯工時表」入口到達
      //（ADR-021；Phase 3 將補完整的案件編輯情境頁）
      case 'wi':      return <WiWorkbench />
      case 'level':   return <LevelSystem />
      case 'ruleset': return <RuleSetViewer />
      case 'case':    return <CasesPage />
      case 'users':        return <UsersPanel />
      case 'dictionaries': return <DictionariesPage />
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
      {importOpen && <ImportModal onClose={() => setImportOpen(false)} />}
      {/* key={tab} remounts the boundary on tab switch → error state auto-clears.
          WorksheetBar 也包進 boundary（review #3）：它的 render 錯誤同樣不得白屏。
          reset 目標與當前 tab 相同時 setTab 是 no-op → 改 full reload（review #4）。 */}
      <ErrorBoundary
        key={tab}
        onReset={() => {
          if (tab === 'dashboard') window.location.reload()
          else setTab('dashboard')
        }}
      >
        {/* WorksheetBar sits above the active feature panel, inside the scrollable main area */}
        <WorksheetBar />
        {renderContent()}
      </ErrorBoundary>
    </AppLayout>
  )
}
