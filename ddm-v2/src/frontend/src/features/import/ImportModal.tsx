import { useState } from 'react'
import { useUploadImport, useMapColumns, useCreateProfile, type UploadOut, type PreviewOut, type ProfileOut } from './api'

const FIELD_ZH: Record<string, string> = {
  description: '描述（必）', part_no: '料號', hand: '手', seconds: '秒（工時）',
  quantity: '次數', element_class: '類別', notes: '備註',
}
const txt = (v: unknown) => (v === null || v === undefined ? '' : String(v))

export function ImportModal({ onClose }: { onClose: () => void }) {
  const upload = useUploadImport()
  const mapCols = useMapColumns()
  const createProfile = useCreateProfile()

  const [up, setUp] = useState<UploadOut | null>(null)
  const [sheet, setSheet] = useState(''); const [headerRow, setHeaderRow] = useState(0); const [timeUnit, setTimeUnit] = useState('sec')
  const [colMap, setColMap] = useState<Record<string, number>>({})
  const [preview, setPreview] = useState<PreviewOut | null>(null)
  const [profileName, setProfileName] = useState(''); const [msg, setMsg] = useState('')

  const step: 'upload' | 'map' | 'preview' = preview ? 'preview' : up ? 'map' : 'upload'
  const curSheet = up?.sheets.find(s => s.name === sheet)
  const fail = (e: unknown) => setMsg('⚠️ ' + (e as Error).message)

  function onFile(file: File) {
    setMsg('')
    upload.mutate(file, {
      onSuccess: (d) => {
        setUp(d); setPreview(null)
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

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b sticky top-0 bg-white">
          <h2 className="font-semibold">📥 匯入 Excel
            <span className="ml-2 text-xs text-slate-400">
              {['上傳', '對應欄位', '預覽'].map((s, i) => <span key={s} className={i === ['upload', 'map', 'preview'].indexOf(step) ? 'text-sky-600 font-medium' : ''}>{i ? ' › ' : ''}{s}</span>)}
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
              <p className="text-xs text-slate-500">提交至工時表（含關鍵字→MOST 草稿）為 Phase 2b 規劃功能。本步驟先確認解析與對應正確，並可存對應範本重用。</p>
              <div className="flex flex-wrap items-center gap-2">
                <input className="border rounded px-2 py-1 text-sm" placeholder="對應範本名稱" value={profileName} onChange={e => setProfileName(e.target.value)} />
                <button onClick={saveProfile} disabled={createProfile.isPending} className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm disabled:opacity-40">存為對應範本</button>
                <button onClick={() => setPreview(null)} className="px-3 py-1.5 border rounded text-sm">← 改對應</button>
                <span className="text-xs text-slate-500">{msg}</span>
              </div>
            </>
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
