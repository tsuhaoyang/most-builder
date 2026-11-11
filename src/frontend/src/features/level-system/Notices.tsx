// ADR-035 D10 F5：通知面板（Notices）。render buildNotices 的有序清單（ask→err→warn→info）。
// 動作走 jobsActions（A.*）與 §7.2 規則；顯示字串一律 t('levelSystem.*')；t/rowNarr 產物不入 store。
import { useTranslation } from 'react-i18next'
import { useWiStore, type Row } from '../wi-workbench/store'
import { useRowNarr } from '../wi-workbench/useRowNarr'
import { useLevelStore } from './store'
import { jobsFromStore } from './jobs'
import * as A from './jobsActions'
import { buildNotices, type Notice } from './notices'
import type { LbReport, LevelIssue } from './api'
import type { Job } from './jobsModel'

interface Props {
  report: LbReport | null
  levelIssues: LevelIssue[]
  editable: boolean
  dismissed: Set<string>
  onDismiss: (key: string) => void
  onGoto: (wiRowId: string) => void
}

export function Notices({ report, levelIssues, editable, dismissed, onDismiss, onGoto }: Props) {
  const { t } = useTranslation()
  const rows = useWiStore(s => s.rows)
  const levelMap = useLevelStore(s => s.levelMap)
  const groupMeta = useLevelStore(s => s.groupMeta)
  const rowNarr = useRowNarr()

  // wi_row_id → 「第 n 步『…』」標籤（rowNarr 產物不入 store）
  const stepOf = (wiRowId: string): string => {
    const i = rows.findIndex(r => r.id === wiRowId)
    if (i < 0) return ''
    const r = rows[i]
    const text = (r && rowNarr(r)) || ''
    return text
      ? t('levelSystem.jobs.stepLabel', { n: i + 1, text })
      : t('levelSystem.jobs.stepShort', { n: i + 1 })
  }

  const notices = buildNotices(report, levelIssues, { t, stepOf })
    // H_MACHINE_TIME 不吃 dismissed（寫回三態後下次預覽自然消失）；其餘依 dismissed 隱藏。
    .filter(n => n.kind === 'H_MACHINE_TIME' || !dismissed.has(n.key))

  // §7.2 動作用：找到含這些 wi_row_id 的 job
  const jobModel = jobsFromStore(rows, levelMap, groupMeta)
  const jobContaining = (ids: string[]): Job | undefined =>
    jobModel.jobs.find(j => {
      const all = new Set([...j.steps, ...j.generalSteps])
      return ids.some(id => all.has(id))
    })

  const onYes = (n: Notice) => {
    const ids = n.wiRowIds ?? []
    if (n.kind === 'H_TOOL_EPISODE_SAME_STATION') {
      const job = jobContaining(ids)
      if (!job) return
      const all = new Set([...job.steps, ...job.generalSteps])
      const subset = ids.filter(id => all.has(id))
      // subset 若等於整個作業步驟 → 整個作業；否則傳子集
      const whole = job.steps.length > 0 && job.steps.every(id => subset.includes(id))
      A.setSameStation(job, true, whole ? undefined : subset)
    } else if (n.kind === 'H_LOT_RUN_SEGMENT') {
      const job = jobContaining(ids)
      if (!job) return
      A.setSameStation(job, true, ids)
      // batch 名稱：以 hint key 尾碼或步數編；此處用 params.k 或 ids 長度
      const k = (n.params?.k as number | undefined) ?? ids.length
      A.setSegment(ids, 'batch' + k)
    } else if (n.kind === 'H_MACHINE_TIME') {
      // yes = 不用顧（unattended=true）
      ids.forEach(id => A.setMachineUnattended(id, true))
    }
    if (n.kind !== 'H_MACHINE_TIME') onDismiss(n.key)
  }

  const onNo = (n: Notice) => {
    if (n.kind === 'H_MACHINE_TIME') {
      // no = 要顧（unattended=false）
      ;(n.wiRowIds ?? []).forEach(id => A.setMachineUnattended(id, false))
      return
    }
    onDismiss(n.key)
  }

  const style: Record<string, string> = {
    ask: 'bg-sky-50 border-sky-200 text-sky-900',
    err: 'bg-red-50 border-red-200 text-red-900',
    warn: 'bg-amber-50 border-amber-200 text-amber-900',
    info: 'bg-slate-50 border-slate-200 text-slate-700',
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-2 space-y-1" data-testid="notices">
      <div className="flex items-baseline gap-2">
        <h4 className="text-sm font-semibold text-slate-700">{t('levelSystem.jobs.notices.title')}</h4>
        <span className="text-[11px] text-slate-400">{t('levelSystem.jobs.notices.hint')}</span>
      </div>
      {notices.length === 0 ? (
        <div className="text-xs text-slate-400 px-1 py-2">{t('levelSystem.jobs.notices.none')}</div>
      ) : (
        <ul className="space-y-1">
          {notices.map(n => (
            <li
              key={n.key}
              data-testid={`notice-${n.key}`}
              className={`flex items-start gap-2 rounded border px-2 py-1.5 text-xs ${style[n.type]}`}>
              <span className="flex-1">{n.text}</span>
              {editable && (
                <div className="flex items-center gap-1 shrink-0">
                  {n.type === 'ask' && (
                    <>
                      <button
                        data-testid="notice-yes"
                        className="text-[11px] border rounded px-1.5 py-0.5 bg-white hover:bg-slate-50"
                        onClick={() => onYes(n)}>
                        {n.kind === 'H_MACHINE_TIME'
                          ? t('levelSystem.hints.H_MACHINE_TIME.yes')
                          : t(`levelSystem.hints.${n.kind}.yes`)}
                      </button>
                      <button
                        data-testid="notice-no"
                        className="text-[11px] border rounded px-1.5 py-0.5 bg-white hover:bg-slate-50"
                        onClick={() => onNo(n)}>
                        {n.kind === 'H_MACHINE_TIME'
                          ? t('levelSystem.hints.H_MACHINE_TIME.no')
                          : t('levelSystem.jobs.notices.no')}
                      </button>
                    </>
                  )}
                  {n.type === 'err' && (n.wiRowIds?.length ?? 0) > 0 && (
                    <button
                      data-testid="notice-goto"
                      className="text-[11px] border rounded px-1.5 py-0.5 bg-white hover:bg-slate-50"
                      onClick={() => onGoto(n.wiRowIds![0])}>
                      {t('levelSystem.jobs.notices.goto')}
                    </button>
                  )}
                  {(n.type === 'warn' || n.type === 'info') && (
                    <button
                      className="text-[11px] border rounded px-1.5 py-0.5 bg-white hover:bg-slate-50"
                      onClick={() => onDismiss(n.key)}>
                      {t('levelSystem.jobs.notices.ok')}
                    </button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
