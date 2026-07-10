import { useQueryClient } from '@tanstack/react-query'
import { useVersions, usePublish, useClone } from './api'
import { useWorkspace } from '../../shared/workspace'
import { useMe, canEdit, canPublish } from '../../shared/auth/useMe'

const BADGE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  retired: 'bg-slate-200 text-slate-600',
}
const STATUS_ZH: Record<string, string> = { draft: '草稿', approved: '已核准', retired: '已退役' }

export function SopPanel() {
  const { data: me } = useMe()
  const activeWs = useWorkspace((s) => s.activeWs)
  const setActiveWs = useWorkspace((s) => s.setActiveWs)
  const qc = useQueryClient()
  const { data, isLoading, error } = useVersions(activeWs)
  const publish = usePublish(activeWs)
  const clone = useClone(activeWs)

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['versions'] })
    qc.invalidateQueries({ queryKey: ['worksheet'] })
    qc.invalidateQueries({ queryKey: ['wi-preview'] })
  }
  const switchTo = (id: string | null) => { if (id && id !== activeWs) { setActiveWs(id); refresh() } }

  if (isLoading) return <div className="bg-white rounded-xl border p-6 text-slate-500">載入版本…</div>
  if (error) return <div className="bg-white rounded-xl border p-6 text-red-600">載入失敗：{(error as Error).message}</div>
  if (!data) return null

  const isDraft = data.status === 'draft'
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">SOP 版本</h2>
          <span className="text-sm">作用中 <b>{data.version_no}</b>
            <span className={`ml-2 px-2 py-0.5 rounded text-xs ${BADGE[data.status] ?? ''}`}>{STATUS_ZH[data.status] ?? data.status}</span>
          </span>
          <span className="ml-auto text-xs text-slate-400">SKU {data.sku_id.slice(0, 8)}…</span>
        </div>
        <p className="text-xs text-slate-500">
          發布會凍結此版本（之後不可編輯）；要繼續修改請「另存新檔」開新草稿。切換版本會載入該版本的工時表與 Level。
        </p>
        <div className="flex flex-wrap gap-2">
          <button disabled={!canPublish(me) || !isDraft || publish.isPending}
            onClick={() => publish.mutate(undefined, { onSuccess: refresh })}
            className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm disabled:opacity-40">
            發布此版本{!canPublish(me) && '（需 approver）'}
          </button>
          <button disabled={!canEdit(me) || clone.isPending}
            onClick={() => clone.mutate(undefined, { onSuccess: (r) => { switchTo(r.new_worksheet_id) } })}
            className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm disabled:opacity-40">
            另存新檔（開新草稿）{!canEdit(me) && '（需 analyst）'}
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border p-4">
        <h3 className="font-semibold mb-2 text-sm">同 SKU 全部版本</h3>
        <table className="w-full text-sm">
          <thead><tr className="bg-slate-100 text-left"><th className="p-1">版本</th><th className="p-1">狀態</th><th className="p-1"></th></tr></thead>
          <tbody>
            {data.versions.map((v) => (
              <tr key={v.version_no} className={`border-t ${v.is_current ? 'bg-sky-50' : ''}`}>
                <td className="p-1 font-medium">{v.version_no}{v.is_current && <span className="ml-1 text-xs text-sky-600">● 作用中</span>}</td>
                <td className="p-1"><span className={`px-2 py-0.5 rounded text-xs ${BADGE[v.status] ?? ''}`}>{STATUS_ZH[v.status] ?? v.status}</span></td>
                <td className="p-1">
                  {!v.is_current && v.worksheet_id &&
                    <button className="text-sky-700 underline" onClick={() => switchTo(v.worksheet_id)}>切換至此版本</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
