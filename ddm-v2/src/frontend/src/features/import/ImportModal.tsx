import { useState } from 'react'
import { useUploadImport, useMapColumns, useCreateProfile, useSubmitImport, type UploadOut, type PreviewOut, type ProfileOut, type SubmitOut } from './api'
import { useWorkspace } from '../../shared/workspace'

const FIELD_ZH: Record<string, string> = {
  description: '描述（必）', part_no: '料號', hand: '手', seconds: '秒（工時）',
  quantity: '次數', element_class: '類別', notes: '備註',
}
const txt = (v: unknown) => (v === null || v === undefined ? '' : String(v))

const STEP_LABELS = ['上傳', '對應欄位', '預覽', '提交'] as const
const STEP_KEYS = ['upload', 'map', 'preview', 'done'] as const

export function ImportModal({ onClose }: { onClose: () => void }) {
  const upload = useUploadImport()
  const mapCols = useMapColumns()
  const createProfile = useCreateProfile()
  const submit = useSubmitImport()
  const activeWs = useWorkspace(s => s.activeWs)

  const [up, setUp] = useState<UploadOut | null>(null)
  const [sheet, setSheet] = useState(''); const [headerRow, setHeaderRow] = useState(0); const [timeUnit, setTimeUnit] = useState('sec')
  const [colMap, setColMap] = useState<Record<string, number>>({})
  const [preview, setPreview] = useState<PreviewOut | null>(null)
  const [submitted, setSubmitted] = useState<SubmitOut | null>(null)
  const [profileName, setProfileName] = useState(''); const [msg, setMsg] = useState('')

  const step: 'upload' | 'map' | 'preview' | 'done' =
    submitted ? 'done' :
    preview ? 'preview' :
    up ? 'map' : 'upload'

  const curSheet = up?.sheets.find(s => s.name === sheet)
  const fail = (e: unknown) => setMsg('⚠️ ' + (e as Error).message)

  function onFile(file: File) {
    setMsg('')
    upload.mutate(file, {
      onSuccess: (d) => {
        setUp(d); setPreview(null); setSubmitted(null)
        setSheet(d.suggested_sheet ?? d.sheets[0]?.name ?? '')
        setHeaderRow(d.suggested_header_row ?? 0)
        setColMap({})
      }, onError: fail,
    })
  }
  function applyProfile(p: ProfileOut) {
    if (p.sheet_hint && up?.sheets.some(s => s.name === p.sheet_hint)) setSheet(p.sheet_hint)
    if (p.header_row != null) setHeaderRow(p.header_row)
    if (p.time_unit) setTimeUnit(p.time_unit)
    setColMap(p.column_map ?? {})
  }
  function doPreview() {
    if (!up) return
    if ((colMap.description ?? -1) < 0) { setMsg('⚠️ 「描述」為必填，請先對應欄位'); return }
    setMsg('')
    mapCols.mutate({ importId: up.import_id, body: { sheet, header_row: headerRow, column_map: cleanMap(colMap), time_unit: timeUnit } },
      { onSuccess: setPreview, onError: fail })
  }
  function saveProfile() {
    if (!profileName.trim()) return
    createProfile.mutate({ name: profileName.trim(), sheet_hint: sheet, header_row: headerRow, column_map: cleanMap(colMap), time_unit: timeUnit },
      { onSuccess: () => setMsg('✓ 已存為對應範本（Profile）'), onError: fail })
  }
  function doSubmit() {
    if (!up || !preview) return
    const wsId = activeWs
    if (!wsId) { setMsg('⚠️ 請先在 WI 工作台選擇一個工序表，再回來提交'); return }
    setMsg('')
    submit.mutate(
      { importId: up.import_id, body: { worksheet_id: wsId } },
      {
        onSuccess: (d) => { setSubmitted(d); setMsg('') },
        onError: (e) => fail(e),
      }
    )
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b sticky top-0 bg-white">
          <h2 className="font-semibold">📥 匯入 Excel
            <span className="ml-2 text-xs text-slate-400">
              {STEP_LABELS.map((s, i) => (
                <span key={s} className={i === STEP_KEYS.indexOf(step) ? 'text-sky-600 font-medium' : ''}>
                  {i ? ' › ' : ''}{s}
                </span>
              ))}
            </span>
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-xl leading-none">✕</button>
        </div>

        <div className="p-4 space-y-4">
          {step === 'upload' && (
            <div className="space-y-2">
              <p className="text-sm text-slate-600">選擇 .xlsx 檔。系統會自動偵測分頁與表頭列，再由你確認欄位對應。</p>
              <input type="file" accept=".xlsx" disabled={upload.isPending}
                onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f) }} className="text-sm" />
              {upload.isPending && <p className="text-sm text-slate-500">解析中…</p>}
            </div>
          )}

          {step === 'map' && up && (
            <>
              <div className="flex flex-wrap items-end gap-3 text-sm">
                <label>分頁 <select className="border rounded px-2 py-1" value={sheet} onChange={e => setSheet(e.target.value)}>
                  {up.sheets.map(s => <option key={s.name} value={s.name}>{s.name}（{s.n_rows}×{s.n_cols}）</option>)}
                </select></label>
                <label>表頭列（0 起）<input type="number" min={0} className="border rounded w-20 px-2 py-1" value={headerRow} onChange={e => setHeaderRow(parseInt(e.target.value) || 0)} /></label>
                <label>工時單位 <select className="border rounded px-2 py-1" value={timeUnit} onChange={e => setTimeUnit(e.target.value)}>
                  <option value="sec">秒</option><option value="min">分</option>
                </select></label>
                {up.profiles.length > 0 && (
                  <label>套用範本 <select className="border rounded px-2 py-1" defaultValue="" onChange={e => { const p = up.profiles.find(x => x.id === e.target.value); if (p) applyProfile(p) }}>
                    <option value="">—</option>{up.profiles.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select></label>
                )}
              </div>

              {curSheet && (
                <div className="border rounded overflow-auto max-h-52">
                  <table className="text-xs">
                    <tbody>
                      {curSheet.grid.slice(0, 15).map((row, ri) => (
                        <tr key={ri} className={ri === headerRow ? 'bg-amber-100 font-medium' : ''}>
                          <td className="px-1 text-slate-400 border-r">{ri}</td>
                          {row.map((c, ci) => <td key={ci} className="px-1.5 py-0.5 border-r whitespace-nowrap max-w-[140px] truncate">{txt(c)}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div>
                <h3 className="text-sm font-medium mb-1">欄位對應（我們的欄位 ← Excel 欄）</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
                  {up.target_fields.map(f => (
                    <label key={f} className="flex items-center gap-1">
                      <span className="w-24 text-slate-600">{FIELD_ZH[f] ?? f}</span>
                      <select className="border rounded px-1 py-1 flex-1" value={colMap[f] ?? -1}
                        onChange={e => setColMap({ ...colMap, [f]: parseInt(e.target.value) })}>
                        <option value={-1}>—</option>
                        {curSheet && Array.from({ length: curSheet.n_cols }).map((_, ci) => (
                          <option key={ci} value={ci}>第{ci}欄：{txt(curSheet.grid[headerRow]?.[ci]) || '(空)'}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button onClick={doPreview} disabled={mapCols.isPending} className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm disabled:opacity-40">預覽</button>
                <button onClick={() => { setUp(null); setMsg('') }} className="px-3 py-1.5 border rounded text-sm">重新上傳</button>
                <span className="text-xs text-slate-500">{msg}</span>
              </div>
            </>
          )}

          {step === 'preview' && preview && (
            <>
              <div className="text-sm">正規化 <b>{preview.n}</b> 列（暫存，尚未寫入工時表）。</div>
              {preview.warnings.length > 0 && (
                <div className="text-xs bg-amber-50 border border-amber-200 rounded p-2 max-h-24 overflow-auto">
                  ⚠️ {preview.warnings.length} 則警告：<ul className="list-disc ml-4">{preview.warnings.slice(0, 30).map((w, i) => <li key={i}>{w}</li>)}</ul>
                </div>
              )}
              <div className="border rounded overflow-auto max-h-72">
                <table className="text-xs w-full">
                  <thead><tr className="bg-slate-100 text-left">{preview.fields.map(f => <th key={f} className="p-1">{FIELD_ZH[f] ?? f}</th>)}</tr></thead>
                  <tbody>
                    {preview.rows.slice(0, 100).map((r, i) => (
                      <tr key={i} className="border-t">{preview.fields.map(f => <td key={f} className="p-1 whitespace-nowrap max-w-[180px] truncate">{txt(r[f])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <input className="border rounded px-2 py-1 text-sm" placeholder="對應範本名稱" value={profileName} onChange={e => setProfileName(e.target.value)} />
                <button onClick={saveProfile} disabled={createProfile.isPending} className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm disabled:opacity-40">存為對應範本</button>
                <button onClick={() => setPreview(null)} className="px-3 py-1.5 border rounded text-sm">← 改對應</button>
                <span className="text-xs text-slate-500">{msg}</span>
              </div>
              <div className="border-t pt-3 flex items-center justify-between">
                <div className="text-sm text-slate-600">
                  共 <span className="font-medium">{preview.n}</span> 列可提交至目前工序表
                  {!activeWs && (
                    <span className="ml-2 text-amber-600">（請先在 WI 工作台選擇工序表）</span>
                  )}
                </div>
                <button
                  onClick={doSubmit}
                  disabled={submit.isPending || !activeWs}
                  className="px-4 py-2 bg-sky-600 text-white rounded-lg text-sm hover:bg-sky-700 disabled:opacity-50"
                >
                  {submit.isPending ? '提交中…' : '提交到工序表 →'}
                </button>
              </div>
            </>
          )}

          {step === 'done' && submitted && (
            <div className="space-y-3 text-sm">
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                <p className="font-medium text-green-800">✓ 匯入完成，已建立 {submitted.n_rows} 列</p>
                <div className="mt-2 text-green-700 space-y-1">
                  <p>MOST 草稿已推斷：{submitted.n_with_analysis} 列</p>
                  <p>需人工補 MOST：{submitted.n_need_review} 列</p>
                </div>
              </div>
              {submitted.warnings.length > 0 && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800">
                  <p className="font-medium mb-1">警告（{submitted.warnings.length}）</p>
                  <ul className="list-disc list-inside space-y-0.5">
                    {submitted.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}
              <p className="text-slate-500">已提交的列在 WI 工作台的工序表中可見；MOST 草稿欄位需 IE 填入。</p>
              <button onClick={onClose} className="px-4 py-2 bg-slate-100 rounded-lg hover:bg-slate-200">
                關閉
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function cleanMap(m: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {}
  Object.entries(m).forEach(([k, v]) => { if (v >= 0) out[k] = v })
  return out
}
