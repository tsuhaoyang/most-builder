import { useEffect, useState } from 'react'
import type { OptionRow } from './api'
import type { SectionSpec } from './paramSchema'

/**
 * 帶型區塊編輯（A 三分量 ＋ M 的 ladder/foot/rotation/hand）。
 *
 * **整組替換**：帶界必須整體遞增無重疊，逐筆編輯會產生非法中間態，
 * 故後端只提供 `PUT /params/{param}/bands`（ADR-023 §2）。此元件因此採
 * 「本地編輯草稿 → 按『儲存帶』一次送出」模式，而非逐格自動儲存。
 */

const cellOf = (row: OptionRow, key: string) => {
  const v = row[key]
  return v === null || v === undefined ? '' : String(v)
}

export function BandEditor({ section, items, readOnly, onSave }: {
  section: SectionSpec
  items: OptionRow[]
  readOnly: boolean
  /** 回 'aborted'＝未寫入（例如轉去建草稿）→ 保留編輯內容與 dirty，不顯示成功。 */
  onSave: (items: Record<string, unknown>[]) => Promise<'saved' | 'aborted'>
}) {
  // 帶型欄位不含 id；送出時只送 schema 欄位（後端 extra='forbid'）
  const cols = section.fields
  const toDraft = (rows: OptionRow[]) =>
    rows.map(r => Object.fromEntries(cols.map(c => [c.key, r[c.key] ?? null])) as Record<string, unknown>)

  const [draft, setDraft] = useState<Record<string, unknown>[]>(() => toDraft(items))
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  // 切換區塊/重新載入 → 重置草稿（未儲存的編輯不跨區塊殘留）
  useEffect(() => { setDraft(toDraft(items)); setDirty(false); setErr(null); setOk(false) },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, section.key])

  const setCell = (i: number, key: string, raw: string) => {
    const spec = cols.find(c => c.key === key)!
    let v: unknown = raw
    if (spec.type === 'int' || spec.type === 'float') {
      v = raw === '' ? null : spec.type === 'int' ? parseInt(raw, 10) : parseFloat(raw)
      if (typeof v === 'number' && Number.isNaN(v)) v = raw
    }
    setDraft(d => d.map((r, idx) => (idx === i ? { ...r, [key]: v } : r)))
    setDirty(true); setOk(false)
  }

  const addRow = () => {
    const blank = Object.fromEntries(cols.map(c => [
      c.key,
      c.type === 'bool' ? c.key === 'is_active' : c.nullable ? null : c.key === 'sort_order' ? draft.length : 0,
    ]))
    setDraft(d => [...d, blank])
    setDirty(true); setOk(false)
  }

  const removeRow = (i: number) => { setDraft(d => d.filter((_, idx) => idx !== i)); setDirty(true); setOk(false) }

  const save = async () => {
    setBusy(true); setErr(null); setOk(false)
    try {
      const result = await onSave(draft)
      if (result === 'aborted') return   // 編輯內容保留；訊息由上層對話框呈現
      setDirty(false); setOk(true)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3" data-testid="dict-band-editor">
      <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
        <p className="font-medium">帶界規則</p>
        <p>上界必須遞增、不得重疊；開放帶（上界留空）僅能在末位。整組一起送出，按「儲存帶」才生效。</p>
        {section.requireOpenEnded && (
          <p className="mt-1 text-amber-800">
            ⚠️ 本分量物理上無上界，<b>末帶必須是開放帶</b>（上界留空）；末帶若為有限值，超界輸入會被引擎靜默夾取到末帶而不報錯。
          </p>
        )}
        {section.groupField && (
          <p className="mt-1">本表依「{cols.find(c => c.key === section.groupField)?.label}」分組，各組各自成一組遞增帶序。</p>
        )}
      </div>

      <div className="bg-white rounded-xl border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 text-left">
              {cols.map(c => <th key={c.key} className="p-2 font-medium">{c.label}</th>)}
              {!readOnly && <th className="p-2 font-medium">操作</th>}
            </tr>
          </thead>
          <tbody>
            {draft.map((row, i) => (
              <tr key={i} className="border-t">
                {cols.map(c => (
                  <td key={c.key} className="p-1">
                    {c.type === 'bool' ? (
                      <input
                        type="checkbox" disabled={readOnly} checked={!!row[c.key]}
                        onChange={e => { setDraft(d => d.map((r, idx) => idx === i ? { ...r, [c.key]: e.target.checked } : r)); setDirty(true); setOk(false) }}
                      />
                    ) : (
                      <input
                        type={c.type === 'text' ? 'text' : 'number'}
                        step={c.type === 'float' ? 'any' : 1}
                        disabled={readOnly}
                        aria-label={`${c.label} 第 ${i + 1} 列`}
                        placeholder={c.nullable ? '（開放）' : ''}
                        className="w-28 border rounded px-2 py-1 text-sm disabled:bg-slate-100"
                        value={cellOf(row as OptionRow, c.key)}
                        onChange={e => setCell(i, c.key, e.target.value)}
                      />
                    )}
                  </td>
                ))}
                {!readOnly && (
                  <td className="p-1">
                    <button onClick={() => removeRow(i)} className="px-2 py-1 rounded border border-red-300 text-red-600 text-xs hover:bg-red-50">
                      刪除
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {draft.length === 0 && (
              <tr><td colSpan={cols.length + 1} className="p-4 text-slate-400">（無帶）</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {err && <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 whitespace-pre-wrap">{err}</p>}
      {ok && <p className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">帶已儲存</p>}

      {!readOnly && (
        <div className="flex items-center gap-2">
          <button onClick={addRow} className="px-3 py-1 rounded border text-sm">+ 增加一帶</button>
          <button
            onClick={() => void save()} disabled={busy || !dirty}
            className="px-3 py-1 rounded bg-sky-600 text-white text-sm disabled:opacity-40"
          >
            {busy ? '儲存中…' : '儲存帶'}
          </button>
          {dirty && <span className="text-xs text-amber-600">有未儲存的變更</span>}
        </div>
      )}
    </div>
  )
}
