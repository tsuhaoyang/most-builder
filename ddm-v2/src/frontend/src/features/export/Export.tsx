import { useState } from 'react'
import { TMU_SEC } from '../../shared/config'
import { useWorkspace } from '../../shared/workspace'
import { useWiPreview, useLbApi, downloadExcel, downloadCsv } from './api'

export function ExportPanel() {
  const ACTIVE_WS = useWorkspace(s => s.activeWs)
  const { data, isLoading, error } = useWiPreview(ACTIVE_WS)
  const lbApi = useLbApi(ACTIVE_WS)
  const [result, setResult] = useState('')

  if (isLoading) return <div className="bg-white rounded-xl border p-6 text-slate-500">載入中…</div>
  if (error) return <div className="bg-white rounded-xl border p-6 text-red-600">載入失敗：{(error as Error).message}</div>

  const total = data?.total_tmu ?? 0
  return (
    <div className="bg-white rounded-xl border p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-semibold">匯出</h2>
        <span className="text-sm">共 {data?.rows.length ?? 0} 列 · 合計 <b className="text-emerald-600">{total}</b> TMU（≈ {(total * TMU_SEC).toFixed(2)} 秒）· 狀態 {data?.status}</span>
      </div>
      <p className="text-xs text-slate-500">下載 Excel（含工序、工時與 Level 關係欄）或輸出給線平衡 (LB)。內容為已儲存的 worksheet（React 端 WI 存檔遷移後即反映本地編輯）。</p>
      <div className="flex flex-wrap gap-2">
        <button className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm" onClick={() => downloadExcel(ACTIVE_WS)}>下載 Excel</button>
        <button className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm" onClick={() => downloadCsv(ACTIVE_WS)}>下載 LB CSV</button>
        <button className="px-3 py-1.5 bg-violet-600 text-white rounded text-sm disabled:opacity-40" disabled={lbApi.isPending}
          onClick={() => lbApi.mutate(undefined, { onSuccess: r => setResult(JSON.stringify(r, null, 2)), onError: e => setResult('失敗：' + (e as Error).message) })}>
          送 LB API（接口 · dry-run）
        </button>
      </div>
      {result && <pre className="font-mono text-xs bg-slate-50 p-2 rounded max-h-72 overflow-auto">{result}</pre>}
    </div>
  )
}
