import { useState } from 'react'
import { useMe } from './shared/auth/useMe'
import { WiWorkbench } from './features/wi-workbench/WiWorkbench'
import { LevelSystem } from './features/level-system/LevelSystem'
import { MasterData } from './features/master-data/MasterData'
import { RuleSetViewer } from './features/rule-set/RuleSetViewer'
import { SopPanel } from './features/sop/SopPanel'
import { ExportPanel } from './features/export/Export'
import { UsersPanel } from './features/users/UsersPanel'

const TABS = [
  { id: 'wi', label: '① WI 工時表' },
  { id: 'level', label: '② Level System' },
  { id: 'master', label: '③ 主數據' },
  { id: 'ruleset', label: '④ Rule-set' },
  { id: 'sop', label: '⑤ SOP 版本' },
  { id: 'export', label: '⑥ 匯出' },
  { id: 'users', label: '⑦ 使用者' },
] as const

export default function App() {
  const [tab, setTab] = useState<string>('wi')
  const { data: me } = useMe()

  return (
    <div className="pb-10">
      <header className="bg-gradient-to-br from-slate-800 to-slate-900 text-white px-4 py-3">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <p className="text-[0.65rem] text-amber-300/90 uppercase tracking-wider">v2 · React + TS · API 驅動</p>
            <h1 className="text-xl font-bold">MOST Workbench</h1>
          </div>
          <span className="text-sm">👤 {me?.employee_no ?? '…'} {me ? `· ${me.roles.join(',') || 'viewer'}` : ''}</span>
        </div>
      </header>

      <nav className="bg-white border-b sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 flex flex-wrap gap-1 py-2 text-sm">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)} aria-selected={tab === t.id}
              className={`px-3 py-1.5 rounded-lg border ${tab === t.id ? 'bg-slate-900 text-white' : ''}`}>
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-4 py-4">
        {tab === 'wi' ? <WiWorkbench />
          : tab === 'level' ? <LevelSystem />
          : tab === 'master' ? <MasterData />
          : tab === 'ruleset' ? <RuleSetViewer />
          : tab === 'sop' ? <SopPanel />
          : tab === 'export' ? <ExportPanel />
          : tab === 'users' ? <UsersPanel />
          : <div className="bg-white rounded-xl border p-6 text-slate-500">
              {TABS.find(t => t.id === tab)?.label}：待遷移（藍本見 docs/html_con/v2-workbench.html）。
            </div>}
      </main>
    </div>
  )
}
