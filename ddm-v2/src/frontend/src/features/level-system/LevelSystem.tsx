// ADR-035 D10：Level System 外殼（thin shell）。作業版（JobsShell，預設）與進階檢視（AdvancedView，IE）
// 二選一切換；worksheet 載入守衛集中在此。內容實作分別在 JobsShell.tsx / AdvancedView.tsx。
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useWiStore } from '../wi-workbench/store'
import { useWorkspace } from '../../shared/workspace'
import { WorksheetRequiredNotice } from '../../shared/ui/WorksheetRequiredNotice'
import { useWorksheetWorkspace } from '../wi-workbench/useWorksheetWorkspace'
import { useLevelStore } from './store'
import { JobsShell } from './JobsShell'
import { AdvancedView } from './AdvancedView'

type View = 'jobs' | 'advanced'

export function LevelSystem() {
  const { t } = useTranslation()
  const activeWs = useWorkspace(s => s.activeWs)
  const worksheet = useWorksheetWorkspace(activeWs)
  const rows = useWiStore(s => s.rows)
  const sync = useLevelStore(s => s.sync)
  const [view, setView] = useState<View>('jobs')

  // 進場/列變動即同步 levelMap（與舊 LevelSystem 一致）
  useEffect(() => { sync() }, [rows]) // eslint-disable-line react-hooks/exhaustive-deps

  // ADR-021 Phase 3：worksheet 情境只能從分析案件進入
  if (!activeWs) return <WorksheetRequiredNotice />

  if (worksheet.isLoading)
    return <div className="bg-white rounded-xl border p-6 text-slate-500">{t('levelSystem.loadingWorksheet')}</div>

  if (worksheet.error)
    return <div className="bg-white rounded-xl border p-6 text-red-600">{t('levelSystem.worksheetLoadFailed', { message: (worksheet.error as Error).message })}</div>

  if (!rows.length)
    return <div className="bg-white rounded-xl border p-6 text-slate-500">{t('levelSystem.noRows')}</div>

  return (
    <div className="bg-white rounded-xl border p-4 space-y-3">
      <div className="flex items-center gap-2">
        <button
          className={`px-2 py-1 rounded text-xs border ${view === 'jobs' ? 'bg-sky-600 text-white border-sky-600' : 'bg-white text-slate-600'}`}
          onClick={() => setView('jobs')}>
          {t('levelSystem.jobs.view.flow')}
        </button>
        <button
          className={`px-2 py-1 rounded text-xs border ${view === 'advanced' ? 'bg-sky-600 text-white border-sky-600' : 'bg-white text-slate-600'}`}
          onClick={() => setView('advanced')}>
          {t('levelSystem.jobs.view.advanced')}
        </button>
      </div>

      {view === 'jobs' ? <JobsShell activeWs={activeWs} /> : <AdvancedView />}
    </div>
  )
}
