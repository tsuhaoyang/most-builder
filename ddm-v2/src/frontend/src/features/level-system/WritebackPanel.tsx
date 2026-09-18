// ADR-036 F2/F3：作業版產線視角「實際結果」區塊 ＋ 離線差異套用（走正門）。
// 顯示 LB 回寫的實際站別／人／件數與三種差異標記（cross_station／missing／offline_conflict），
// 並列出 offline 差異供 IE 勾選套用。文案一律使用者語言（「這一步被排到第 3 站，2 個人做」）。
// 純消費 useLbWriteback/useFetchWriteback/useApplyOffline；t() 產物不入 store。
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../shared/api/client'
import { useWiStore } from '../wi-workbench/store'
import { useRowNarr } from '../wi-workbench/useRowNarr'
import { useLbWriteback, useFetchWriteback, useApplyOffline } from './api'

export function WritebackPanel({ worksheetId, editable }: { worksheetId: string; editable: boolean }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const rows = useWiStore(s => s.rows)
  const rowNarr = useRowNarr()
  const wb = useLbWriteback(worksheetId)
  const fetchWb = useFetchWriteback(worksheetId)
  const applyWb = useApplyOffline(worksheetId)

  const [form, setForm] = useState({ lb_project_id: '', lb_version_id: '', lb_result_id: '' })
  const [showForm, setShowForm] = useState(false)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [applyMsg, setApplyMsg] = useState<string | null>(null)

  // wi_row_id → 「第 n 步『敘述』」的使用者語言標籤
  const stepLabel = useMemo(() => {
    const m: Record<string, string> = {}
    rows.forEach((r, i) => { m[r.id] = t('levelSystem.jobs.writeback.stepLabel', { n: i + 1, name: rowNarr(r) }) })
    return m
  }, [rows, rowNarr, t])
  const label = (id: string) => stepLabel[id] ?? id.slice(0, 8)

  async function doFetch() {
    setApplyMsg(null)
    try {
      await fetchWb.mutateAsync(form)
      await qc.invalidateQueries({ queryKey: ['lb-writeback-latest', worksheetId] })
      setShowForm(false)
    } catch (e) {
      setApplyMsg(t('levelSystem.jobs.writeback.fetchFailed', { message: (e as ApiError).humanMessage || String(e) }))
    }
  }

  async function doApply() {
    if (checked.size === 0 || !wb.data) return
    setApplyMsg(null)
    try {
      const res = await applyWb.mutateAsync({ snapshot_id: wb.data.snapshot_id, wi_row_ids: [...checked] })
      const propagated = res.propagated.length
        ? t('levelSystem.jobs.writeback.propagated', { steps: res.propagated.map(label).join(t('levelSystem.listSeparator')) })
        : ''
      setApplyMsg(t('levelSystem.jobs.writeback.applied', { count: res.applied.length }) + (propagated ? ` ${propagated}` : ''))
      setChecked(new Set())
      await qc.invalidateQueries({ queryKey: ['lb-writeback-latest', worksheetId] })
      await qc.invalidateQueries({ queryKey: ['worksheet', worksheetId] })
    } catch (e) {
      // 任一 E → 後端整批 rollback，一列都不套
      setApplyMsg(t('levelSystem.jobs.writeback.applyFailed', { message: (e as ApiError).humanMessage || String(e) }))
    }
  }

  // 取得表單（重新取得結果）
  const fetchForm = (
    <div className="flex flex-wrap items-center gap-1 text-[11px]" data-testid="writeback-fetch-form">
      {(['lb_project_id', 'lb_version_id', 'lb_result_id'] as const).map(k => (
        <input key={k} className="border rounded px-1 py-0.5 w-28" placeholder={t(`levelSystem.jobs.writeback.field.${k}`)}
          value={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} />
      ))}
      <button data-testid="writeback-fetch-go" className="px-2 py-0.5 rounded bg-sky-600 text-white disabled:opacity-50"
        disabled={fetchWb.isPending || !form.lb_project_id || !form.lb_version_id || !form.lb_result_id}
        onClick={doFetch}>{t('levelSystem.jobs.writeback.refetch')}</button>
    </div>
  )

  // 無快照：引導取得（不報錯）
  if (wb.isError || (!wb.isLoading && !wb.data)) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-2 space-y-1" data-testid="writeback-panel">
        <div className="text-xs text-slate-500">{t('levelSystem.jobs.writeback.noSnapshot')}</div>
        {editable && (showForm ? fetchForm
          : <button data-testid="writeback-fetch-open" className="text-xs px-2 py-1 border rounded" onClick={() => setShowForm(true)}>
              {t('levelSystem.jobs.writeback.fetch')}
            </button>)}
        {applyMsg && <div className="text-[11px] text-red-700">{applyMsg}</div>}
      </div>
    )
  }
  if (wb.isLoading || !wb.data) return null

  const { summary, diff, fetched_at, applied_at } = wb.data
  const busy = summary.unattended_machine_policy === 'busy'

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-2 space-y-2" data-testid="writeback-panel">
      {/* 來源座標 + 政策 + 重新取得 */}
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
        <span className="font-semibold">{t('levelSystem.jobs.writeback.title')}</span>
        <span>{t('levelSystem.jobs.writeback.source', { project: summary.project_id, version: summary.version_id, result: summary.result_id })}</span>
        {fetched_at && <span>{t('levelSystem.jobs.writeback.fetchedAt', { at: new Date(fetched_at).toLocaleString() })}</span>}
        {busy && <span data-testid="writeback-policy-busy" className="px-1 rounded bg-amber-100 text-amber-800">{t('levelSystem.jobs.writeback.policyBusy')}</span>}
        {editable && (showForm ? fetchForm
          : <button data-testid="writeback-refetch" className="ml-auto px-2 py-0.5 border rounded" onClick={() => setShowForm(true)}>{t('levelSystem.jobs.writeback.refetch')}</button>)}
      </div>

      {/* 每個 motion 的實際站別／人／件數（使用者語言）＋差異標記 */}
      <div className="space-y-1" data-testid="writeback-placements">
        {Object.entries(diff.motions).map(([wi, mp]) => (
          <div key={wi} data-testid={`writeback-motion-${wi}`} className="flex flex-wrap items-center gap-2 text-[11px] border-b border-slate-100 py-0.5">
            <span className="flex-1 min-w-0 truncate">{label(wi)}</span>
            <span className="text-slate-700">
              {mp.stations.length > 1
                ? t('levelSystem.jobs.writeback.stationsMulti', { workers: mp.workers.length })
                : t('levelSystem.jobs.writeback.station', { n: (mp.stations[0] ?? 0) + 1, workers: mp.workers.length })}
            </span>
            {mp.units_total != null && <span className="text-slate-500">{t('levelSystem.jobs.writeback.units', { n: mp.units_total })}</span>}
            {mp.cross_station && <span data-testid="mark-cross" className="px-1 rounded bg-red-100 text-red-800">{t('levelSystem.jobs.writeback.crossStation')}</span>}
            {mp.offline_conflict && <span className="px-1 rounded bg-amber-100 text-amber-800">{t('levelSystem.jobs.writeback.offlineConflict')}</span>}
          </div>
        ))}
        {diff.missing.map(m => (
          <div key={m.wi_row_id} data-testid="writeback-missing" className="text-[11px] text-slate-500 py-0.5">
            {label(m.wi_row_id)} — {t(`levelSystem.jobs.writeback.missing.${m.reason}`, t('levelSystem.jobs.writeback.missing.no_result'))}
          </div>
        ))}
      </div>

      {/* 離線差異套用（走正門） */}
      {editable && diff.offline_diffs.length > 0 && (
        <div className="border-t border-slate-200 pt-1 space-y-1" data-testid="writeback-offline-diffs">
          <div className="text-[11px] font-semibold text-slate-700">{t('levelSystem.jobs.writeback.offlineTitle')}</div>
          {diff.offline_diffs.map(od => (
            <label key={od.wi_row_id} className="flex items-center gap-2 text-[11px]">
              <input type="checkbox" data-testid={`writeback-offline-${od.wi_row_id}`}
                checked={checked.has(od.wi_row_id)}
                onChange={e => setChecked(s => { const n = new Set(s); e.target.checked ? n.add(od.wi_row_id) : n.delete(od.wi_row_id); return n })} />
              <span className="flex-1 truncate">{label(od.wi_row_id)}</span>
              <span className="text-slate-500">{t('levelSystem.jobs.writeback.offlineVals', { most: String(od.most_offline), lb: String(od.lb_offline) })}</span>
            </label>
          ))}
          <button data-testid="writeback-apply-offline" className="text-xs px-2 py-1 rounded bg-sky-600 text-white disabled:opacity-50"
            disabled={applyWb.isPending || checked.size === 0}
            onClick={doApply}>{t('levelSystem.jobs.writeback.applyOffline')}</button>
        </div>
      )}
      {applied_at && <div className="text-[11px] text-emerald-700">{t('levelSystem.jobs.writeback.appliedAt', { at: new Date(applied_at).toLocaleString() })}</div>}
      {applyMsg && <div data-testid="writeback-apply-msg" className="text-[11px] text-slate-700">{applyMsg}</div>}
    </div>
  )
}
