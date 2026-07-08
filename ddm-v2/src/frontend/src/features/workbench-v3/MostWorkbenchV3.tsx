// MOST 工作台 v3 — 三層組裝 Shell (F-03)
// Tab 1: 動作模組  Tab 2: WI 組成  Tab 3: 製程途程
import { useWorkbenchV3Store } from './store'
import { ActionModuleWorkspace } from './ActionModuleWorkspace'
import { WIPoolWorkspace } from './WIPoolWorkspace'
import { ProcessWorkspace } from './ProcessWorkspace'

const TABS = [
  { id: 'tab1' as const, label: '動作模組' },
  { id: 'tab2' as const, label: 'WI 組成' },
  { id: 'tab3' as const, label: '製程途程' },
]

export function MostWorkbenchV3() {
  const { activeTab, setActiveTab, pendingModules, pendingWiIds } = useWorkbenchV3Store()

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Tab header */}
      <div className="bg-white rounded-xl border">
        <div className="flex">
          {TABS.map((t, idx) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`relative px-5 py-3 text-sm font-medium transition-colors border-b-2 ${
                activeTab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
              } ${idx === 0 ? 'rounded-tl-xl' : ''}`}
            >
              {t.label}
              {/* Badge: pending modules waiting in Tab 2 */}
              {t.id === 'tab2' && pendingModules.length > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-600 text-white text-[10px] rounded-full flex items-center justify-center">
                  {pendingModules.length}
                </span>
              )}
              {/* Badge: pending WI IDs waiting in Tab 3 (F-03 跨層傳送 E-07) */}
              {t.id === 'tab3' && pendingWiIds.length > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-600 text-white text-[10px] rounded-full flex items-center justify-center">
                  {pendingWiIds.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0">
        {activeTab === 'tab1' && <ActionModuleWorkspace />}
        {activeTab === 'tab2' && <WIPoolWorkspace />}
        {activeTab === 'tab3' && <ProcessWorkspace />}
      </div>
    </div>
  )
}
