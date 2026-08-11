import { useState, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useUploadImport, useMapColumns, useCreateProfile, useSubmitImport, type UploadOut, type PreviewOut, type PreviewRow, type ProfileOut, type SubmitOut, type MatchOption, type RowMatch } from './api'
import { useWorkspace } from '../../shared/workspace'
import { useWiStore } from '../wi-workbench/store'
import { ApiError } from '../../shared/api/client'

// ── ADR-025 D10：範本命中的採用判定（前端只渲染後端算好的值，絕不自算 TMU）──────────
// 一列可採用 ⇔ 目前選中的範本選項有後端重算出的 TMU 且無 error。
// computed_tmu === null（＋error）＝命中但算不出（例：無 active 字典）→ 不可採用、不顯示任何數字。
const isAdoptable = (opt: MatchOption | undefined): boolean =>
  !!opt && opt.computed_tmu !== null && opt.error == null
// 取某列「目前選中」的範本選項（最佳命中或其候選之一）
function optionOf(m: RowMatch, tid: string | undefined): MatchOption {
  if (!tid || m.template_id === tid) return m
  return m.candidates.find(c => c.template_id === tid) ?? m
}
const rowMatch = (r: PreviewRow): RowMatch | null => (r.match ?? null)

const FIELD_ZH: Record<string, string> = {
  description: '描述（必）', part_no: '料號', hand: '手', seconds: '秒（工時）',
  quantity: '次數', element_class: '類別', notes: '備註',
}
const txt = (v: unknown) => (v === null || v === undefined ? '' : String(v))

const STEP_LABELS = ['上傳', '對應欄位', '預覽', '提交'] as const
const STEP_KEYS = ['upload', 'map', 'preview', 'done'] as const

export function ImportModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
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

  // ADR-025 D10：逐行採用決定。selected[i]＝該列選中的 template_id；adopted[i]＝是否採用。
  const [selected, setSelected] = useState<Record<number, string>>({})
  const [adopted, setAdopted] = useState<Record<number, boolean>>({})

  // preview 進來時初始化：命中且可算的列預選採用（守則 §2 預選、§7 命中但算不出不放行）
  useEffect(() => {
    if (!preview) { setSelected({}); setAdopted({}); return }
    const sel: Record<number, string> = {}
    const ado: Record<number, boolean> = {}
    preview.rows.forEach((r, i) => {
      const m = rowMatch(r)
      if (m) { sel[i] = m.template_id; ado[i] = isAdoptable(m) }
    })
    setSelected(sel); setAdopted(ado)
  }, [preview])

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
  // 切換單列採用（只有可採用的列才允許勾選）
  function toggleAdopt(i: number) {
    setAdopted(a => ({ ...a, [i]: !a[i] }))
  }
  // 換候選範本：更新選中的 template_id，並依新選項是否可算重設採用狀態
  // （選了一個範本＝明確表示「要這個」→ 可算就採用；換到算不出的候選則不採用）
  function chooseTemplate(i: number, tid: string) {
    if (!preview) return
    const m = rowMatch(preview.rows[i])
    if (!m) return
    setSelected(s => ({ ...s, [i]: tid }))
    setAdopted(a => ({ ...a, [i]: isAdoptable(optionOf(m, tid)) }))
  }
  // 批次：全部採用／全部不採用（全部採用只作用在可採用的列）
  function adoptAll(v: boolean) {
    if (!preview) return
    const next: Record<number, boolean> = {}
    preview.rows.forEach((r, i) => {
      const m = rowMatch(r)
      if (!m) return
      next[i] = v && isAdoptable(optionOf(m, selected[i]))
    })
    setAdopted(next)
  }
  function doSubmit() {
    if (!up || !preview) return
    const wsId = activeWs
    if (!wsId) { setMsg('⚠️ 請先從分析案件開啟工時表，再回來提交'); return }
    setMsg('')
    // 只送「採用」的列，且只送 row_index＋template_id（TMU 一律後端以 active 重算）
    const rowAdoptions = preview.rows.flatMap((_r, i) => {
      const tid = selected[i]
      return adopted[i] && tid ? [{ row_index: i, template_id: tid }] : []
    })
    const baseRevision = useWiStore.getState().revisionNo
    submit.mutate(
      {
        importId: up.import_id,
        body: {
          worksheet_id: wsId,
          row_adoptions: rowAdoptions,
          ...(baseRevision != null ? { base_revision: baseRevision } : {}),
        },
      },
      {
        onSuccess: (d) => {
          setSubmitted(d)
          setMsg('')
          if (typeof d.revision_no === 'number') {
            useWiStore.getState().setRevisionMeta({
              revisionNo: d.revision_no,
              contentHash: d.content_hash ?? null,
            })
          }
          void qc.invalidateQueries({ queryKey: ['worksheet', wsId] })
        },
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409 && e.code === 'WORKSHEET_REVISION_CONFLICT') {
            setMsg('⚠️ 提交衝突：工序表已被更新。請重新載入工時表後再提交。')
            void qc.invalidateQueries({ queryKey: ['worksheet', wsId] })
            return
          }
          fail(e)
        },
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

              {/* ── ADR-025 D10：逐行自動建模建議（範本命中，IE 核對後才落地）── */}
              <MatchPanel
                rows={preview.rows}
                selected={selected}
                adopted={adopted}
                onToggle={toggleAdopt}
                onChoose={chooseTemplate}
                onAdoptAll={adoptAll}
              />

              {/* 原始資料表僅供「參考」（不涉及採用決定）→ 可截斷至前 100 列並明確標註；
                  真正涉及信任邊界的是上方採用面板，那個一律全渲染。兩表性質不同，區別對待。 */}
              <details className="border rounded">
                <summary className="text-xs text-slate-600 px-2 py-1.5 cursor-pointer select-none">
                  檢視正規化後的原始資料（{preview.fields.length} 欄 × {preview.n} 列）
                </summary>
                {preview.rows.length > 100 && (
                  <div className="text-[11px] text-amber-700 bg-amber-50 border-t px-2 py-1">
                    ⚠️ 此參考表僅顯示前 100 列；完整 {preview.n} 列將依「上方採用面板」的設定提交。
                  </div>
                )}
                <div className="overflow-auto max-h-60 border-t">
                  <table className="text-xs w-full">
                    <thead><tr className="bg-slate-100 text-left">{preview.fields.map(f => <th key={f} className="p-1">{FIELD_ZH[f] ?? f}</th>)}</tr></thead>
                    <tbody>
                      {preview.rows.slice(0, 100).map((r, i) => (
                        <tr key={i} className="border-t">{preview.fields.map(f => <td key={f} className="p-1 whitespace-nowrap max-w-[180px] truncate">{txt(r[f])}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
              <div className="flex flex-wrap items-center gap-2">
                <input className="border rounded px-2 py-1 text-sm" placeholder="對應範本名稱" value={profileName} onChange={e => setProfileName(e.target.value)} />
                <button onClick={saveProfile} disabled={createProfile.isPending} className="px-3 py-1.5 bg-emerald-600 text-white rounded text-sm disabled:opacity-40">存為對應範本</button>
                <button onClick={() => setPreview(null)} className="px-3 py-1.5 border rounded text-sm">← 改對應</button>
                <span className="text-xs text-slate-500">{msg}</span>
              </div>
              <div className="border-t pt-3 flex items-center justify-between">
                <div className="text-sm text-slate-600">
                  共 <span className="font-medium">{preview.n}</span> 列可提交至目前工序表
                  <span className="ml-2 text-emerald-700" data-testid="adopt-count">
                    （{preview.rows.filter((_r, i) => adopted[i] && selected[i]).length} 列採用範本自動建模）
                  </span>
                  {!activeWs && (
                    <span className="ml-2 text-amber-600">（請先從分析案件開啟工時表）</span>
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
              <p className="text-slate-500">已提交的列在分析案件的工時表中可見；MOST 草稿欄位需 IE 填入。</p>
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

// ── ADR-025 D10：逐行自動建模建議面板 ──────────────────────────────────────────
// 三種列狀態，視覺明確區分（守則 §7 第 8 條「不確定不放行」）：
//   1) 命中且可算    → 綠框、預選採用、顯示後端算的 TMU、可換候選、可取消
//   2) 命中但算不出  → 琥珀/紅錯誤框、不可勾選、顯示 error（例：無 active 字典），**絕不顯示任何 TMU**
//   3) 完全無命中    → 中性灰、標「須手動建模」、不勾選、不套（維持 stub，IE 事後建模）
function MatchPanel({ rows, selected, adopted, onToggle, onChoose, onAdoptAll }: {
  rows: PreviewRow[]
  selected: Record<number, string>
  adopted: Record<number, boolean>
  onToggle: (i: number) => void
  onChoose: (i: number, tid: string) => void
  onAdoptAll: (v: boolean) => void
}) {
  let nHit = 0, nErr = 0, nManual = 0, nAdopted = 0
  rows.forEach((r, i) => {
    const m = rowMatch(r)
    if (!m) { nManual++; return }
    const opt = optionOf(m, selected[i])
    if (isAdoptable(opt)) { nHit++; if (adopted[i]) nAdopted++ } else nErr++
  })

  return (
    <div data-testid="match-panel" className="border rounded">
      <div className="flex flex-wrap items-center gap-2 px-2.5 py-2 border-b bg-slate-50 text-xs">
        <span className="font-medium text-slate-700">自動建模建議</span>
        <span className="text-emerald-700">命中 {nHit}</span>
        {nErr > 0 && <span className="text-rose-600">命中但無法計算 {nErr}</span>}
        <span className="text-slate-500">須手動建模 {nManual}</span>
        <span className="ml-auto text-slate-500">已採用 <b className="text-emerald-700">{nAdopted}</b> 列</span>
        <button type="button" onClick={() => onAdoptAll(true)} data-testid="adopt-all"
          className="px-2 py-0.5 border rounded hover:bg-white">全部採用</button>
        <button type="button" onClick={() => onAdoptAll(false)} data-testid="adopt-none"
          className="px-2 py-0.5 border rounded hover:bg-white">全部不採用</button>
      </div>
      <div className="overflow-auto max-h-72">
        <table className="text-xs w-full">
          <thead>
            <tr className="bg-white text-left text-slate-500 border-b sticky top-0">
              <th className="p-1.5 w-10">採用</th>
              <th className="p-1.5">描述</th>
              <th className="p-1.5">建議範本</th>
              <th className="p-1.5 w-14">類型</th>
              <th className="p-1.5 w-16 text-right">TMU</th>
              <th className="p-1.5">命中</th>
            </tr>
          </thead>
          <tbody>
            {/* 全渲染（不截斷）：採用/預選/送出都涵蓋全部列，這裡若截斷會讓 >100 列的命中
                被 IE 看不到地自動落盤（ADR-025 §2 明文否決的「自動套用、事後再改」）。 */}
            {rows.map((r, i) => (
              <MatchRow key={i} i={i} row={r} selectedTid={selected[i]} adopted={!!adopted[i]}
                onToggle={onToggle} onChoose={onChoose} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MatchRow({ i, row, selectedTid, adopted, onToggle, onChoose }: {
  i: number
  row: PreviewRow
  selectedTid: string | undefined
  adopted: boolean
  onToggle: (i: number) => void
  onChoose: (i: number, tid: string) => void
}) {
  const desc = txt(row.description) || <span className="text-slate-300">（無描述）</span>
  const m = rowMatch(row)

  // 狀態 3：完全無命中 → 中性灰、須手動建模（非錯誤，是預期路徑）
  if (!m) {
    return (
      <tr data-testid={`match-row-${i}`} className="border-t bg-slate-50/60">
        <td className="p-1.5 text-center text-slate-300">—</td>
        <td className="p-1.5 max-w-[220px] truncate">{desc}</td>
        <td className="p-1.5 text-slate-400" colSpan={4}>
          <span data-testid={`match-manual-${i}`} className="inline-flex items-center gap-1">
            <span className="px-1.5 py-0.5 rounded bg-slate-200 text-slate-600">須手動建模</span>
            無命中範本，提交後由 IE 於工序表建模
          </span>
        </td>
      </tr>
    )
  }

  const opt = optionOf(m, selectedTid)
  const options = [m, ...m.candidates]
  const adoptable = isAdoptable(opt)

  return (
    <tr data-testid={`match-row-${i}`} className={'border-t ' + (adoptable ? '' : 'bg-rose-50/60')}>
      <td className="p-1.5 text-center">
        <input type="checkbox" data-testid={`adopt-checkbox-${i}`}
          checked={adopted} disabled={!adoptable} onChange={() => onToggle(i)}
          className="accent-emerald-600 disabled:opacity-40" />
      </td>
      <td className="p-1.5 max-w-[220px] truncate">{desc}</td>
      <td className="p-1.5">
        {options.length > 1 ? (
          <select data-testid={`match-select-${i}`} value={opt.template_id}
            onChange={e => onChoose(i, e.target.value)}
            className="border rounded px-1 py-0.5 max-w-[180px]">
            {options.map(o => (
              <option key={o.template_id} value={o.template_id}>
                {o.template_name_zh}（{o.seq_kind}{o.computed_tmu !== null ? ` · ${o.computed_tmu} TMU` : ' · 無法計算'}）
              </option>
            ))}
          </select>
        ) : (
          <span className="font-medium text-slate-700">{opt.template_name_zh}</span>
        )}
      </td>
      <td className="p-1.5">
        <span className="px-1.5 py-0.5 rounded bg-sky-100 text-sky-700">{opt.seq_kind}</span>
      </td>
      <td className="p-1.5 text-right" data-testid={`match-tmu-${i}`}>
        {opt.computed_tmu !== null
          ? <span className="font-medium tabular-nums">{opt.computed_tmu}</span>
          : <span data-testid={`match-error-${i}`} className="text-rose-600">無法計算</span>}
      </td>
      <td className="p-1.5">
        {adoptable
          ? <span className="text-slate-500">
              分 {opt.score}<span className="text-slate-400"> · {opt.matched_keywords.join('、') || '—'}</span>
            </span>
          : <span data-testid={`match-error-msg-${i}`} className="text-rose-600">
              {opt.error ?? '目前無法計算此列 TMU'}
            </span>}
      </td>
    </tr>
  )
}
