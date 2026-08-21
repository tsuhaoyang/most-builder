import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useMe, canEdit } from './shared/auth/useMe'
import { useLocaleSync } from './shared/i18n/useLocaleSync'
import { ImportModal } from './features/import/ImportModal'
import { WiWorkbench } from './features/wi-workbench/WiWorkbench'
import { LevelSystem } from './features/level-system/LevelSystem'
import { DictionaryPage } from './features/dictionary/DictionaryPage'
import { UsersPanel } from './features/users/UsersPanel'
import { AppLayout } from './features/layout/AppLayout'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { MostWorkbenchV3 } from './features/workbench-v3/MostWorkbenchV3'
import { CasesPage } from './features/cases/CasesPage'
import { DictionariesPage } from './features/dictionaries/DictionariesPage'
import { WISetBuilderPage } from './features/wi-project/WISetBuilderPage'
import { CaseContextBar } from './features/cases/CaseContextBar'
import { ErrorBoundary } from './shared/ui/ErrorBoundary'
import { WorksheetRequiredNotice } from './shared/ui/WorksheetRequiredNotice'
import { useWorkspace } from './shared/workspace'

export default function App() {
  const { t } = useTranslation()
  const [tab, setTab] = useState<string>('dashboard')
  const [importOpen, setImportOpen] = useState(false)
  const { data: me } = useMe()
  const activeWs = useWorkspace(s => s.activeWs)
  useLocaleSync(me) // ADR-032 D3.2：/me 到達後伺服器 locale 成為權威值

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
      // 'wi'（WiWorkbench 工時表編輯器）僅由分析案件的「編輯工時表／新建案件」入口到達
      //（ADR-021 Phase 3：案件情境頁＝CaseContextBar＋編輯器；無 activeWs 時導回分析案件）
      case 'wi':
        return activeWs ? (
          <>
            <CaseContextBar />
            <WiWorkbench />
          </>
        ) : (
          <WorksheetRequiredNotice />
        )
      case 'level':   return <LevelSystem />
      case 'ruleset': return <DictionaryPage />
      case 'case':    return <CasesPage />
      case 'users':        return <UsersPanel />
      case 'dictionaries': return <DictionariesPage />
      default:
        return (
          <div className="bg-white rounded-xl border p-6 text-slate-500 text-sm">
            {t('app.tabInProgress', { tab })}
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
          reset 目標與當前 tab 相同時 setTab 是 no-op → 改 full reload（review #4）。
          全域 WorksheetBar 已去全域化（ADR-021 Phase 3）：工序表情境只存在於分析案件的編輯情境。
          該元件已刪除（見 features/cases/NewCaseModal.tsx）；此處保留名字只為說明現況的由來。 */}
      <ErrorBoundary
        key={tab}
        onReset={() => {
          if (tab === 'dashboard') window.location.reload()
          else setTab('dashboard')
        }}
      >
        {renderContent()}
      </ErrorBoundary>
    </AppLayout>
  )
}
