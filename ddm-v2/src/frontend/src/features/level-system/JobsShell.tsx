// ADR-035 D10 F3/F4：作業版外殼（作業版 = 給非 IE 的「工序整理」視圖）。
// 掛 LbPreview（dry-run，取得 report.rows 供卡片秒數/chips）；持有 selectedJobId 給 JobDrawer。
// 預覽節流（debounce + latest-wins）與 422 toast 由 F6 補；此處先 useEffect 直打，失敗靜默忽略。
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { useWiStore } from '../wi-workbench/store'
import { useRowNarr } from '../wi-workbench/useRowNarr'
import { buildSaveBody } from '../wi-workbench/savePayload'
import { useLevelStore } from './store'
import { useLbPreview, type LbReport } from './api'
import { derive } from './logic'
import { applyBaseline } from './jobsActions'
import { JobsFlow } from './JobsFlow'
import { JobDrawer } from './JobDrawer'

export function JobsShell({ activeWs }: { activeWs: string }) {
  const { t } = useTranslation()
  const { data: me } = useMe()
  const editable = canEdit(me)
  const rows = useWiStore(s => s.rows)
  const levelMap = useLevelStore(s => s.levelMap)
  const groupMeta = useLevelStore(s => s.groupMeta)
  const rowNarr = useRowNarr()

  const preview = useLbPreview(activeWs)
  const [report, setReport] = useState<LbReport | null>(null)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [baseline, setBaseline] = useState<{ jobCount: number } | null>(null)
  const [baselineWs, setBaselineWs] = useState<string>('')

  // baseline（附錄 A.4）：每個 worksheet 載入後套用一次（hydrate 完、rows 就緒）。
  useEffect(() => {
    if (!editable || !rows.length || baselineWs === activeWs) return
    setBaselineWs(activeWs)
    const res = applyBaseline()
    if (res.applied) setBaseline({ jobCount: res.jobCount })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWs, rows.length, editable])

  function undoBaseline() {
    // 還原＝重載 worksheet（hydrate 覆蓋本地 store，回到未套用狀態）
    setBaseline(null)
    setBaselineWs('')  // 允許再次套用（若使用者未存檔）
    useWiStore.getState().setRows([...useWiStore.getState().rows])  // 觸發重渲染；實際還原走重載
  }

  // 掛載 + rows/levelMap/groupMeta 變動 → dry-run 預覽。無 debounce（F6 補）；失敗靜默。
  useEffect(() => {
    if (!rows.length) { setReport(null); return }
    const payload = derive(rows, levelMap, groupMeta, rowNarr)
    const baseRevision = useWiStore.getState().revisionNo
    const body = buildSaveBody(rows, payload, baseRevision)
    preview.mutate(body, {
      onSuccess: r => setReport(r),
      onError: () => { /* F6：422 toast；此處先靜默 */ },
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, levelMap, groupMeta])

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-3">
      <div>
        <h3 className="font-semibold text-sm mb-1">{t('levelSystem.jobs.title')}</h3>
        <p className="text-xs text-slate-500 mb-2">{t('levelSystem.jobs.subtitle')}</p>
        {baseline && (
          <div className="flex items-center gap-2 text-xs bg-sky-50 border border-sky-200 rounded px-2 py-1 mb-2" data-testid="baseline-notice">
            <span className="text-sky-800">{t('levelSystem.jobs.baseline.applied', { count: baseline.jobCount })}</span>
            <button className="text-sky-700 underline" onClick={undoBaseline}>{t('levelSystem.jobs.baseline.undo')}</button>
          </div>
        )}
        <JobsFlow
          report={report}
          editable={editable}
          onSelect={setSelectedJobId}
          selectedJobId={selectedJobId}
        />
      </div>
      <div className="rounded-xl border border-slate-200 bg-slate-50/40 p-2">
        <JobDrawer jobId={selectedJobId} report={report} editable={editable} />
      </div>
    </div>
  )
}
