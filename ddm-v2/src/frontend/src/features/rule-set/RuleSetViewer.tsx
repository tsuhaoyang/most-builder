import { useState } from 'react'
import { useRuleSetList, useRuleSetFull, type RuleSetFull } from './api'

const BADGE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800', published: 'bg-emerald-100 text-emerald-800', archived: 'bg-slate-200 text-slate-600',
}
const STATUS_ZH: Record<string, string> = { draft: '草稿', published: '已發布', archived: '已封存' }

type Col = { key: string; label: string }
const SECTIONS: { field: keyof RuleSetFull; title: string; cols: Col[]; open?: boolean }[] = [
  { field: 'a_bands', title: 'A — 移動距離（reach/twist/foot）', open: true, cols: [
    { key: 'component', label: '分量' }, { key: 'max_value', label: '上限(cm)' }, { key: 'index', label: '指數' }] },
  { field: 'b', title: 'B — 身體輔助', cols: [
    { key: 'code', label: '代碼' }, { key: 'label_zh', label: '名稱' }, { key: 'index', label: '指數' }, { key: 'is_default', label: '預設' }] },
  { field: 'g', title: 'G — 取得', open: true, cols: [
    { key: 'code', label: '代碼' }, { key: 'label_zh', label: '名稱' }, { key: 'base_tmu', label: '指數' }, { key: 'modifier_key', label: '修飾子' }, { key: 'requires_modifier', label: '需修飾' }] },
  { field: 'p_bases', title: 'P — 放置（基礎）', cols: [
    { key: 'code', label: '代碼' }, { key: 'label_zh', label: '名稱' }, { key: 'category', label: '類別' }, { key: 'direction_mode', label: '方向' }, { key: 'base_tmu', label: '指數' }] },
  { field: 'p_addons', title: 'P — 放置（附加）', cols: [
    { key: 'code', label: '代碼' }, { key: 'label_zh', label: '名稱' }, { key: 'delta', label: '增量' }, { key: 'needs_precision', label: '需精度' }] },
  { field: 'm_verbs', title: 'M — 控制動詞', cols: [
    { key: 'code', label: '代碼' }, { key: 'label_zh', label: '名稱' }, { key: 'pricing_kind', label: '計價方式' }, { key: 'fixed_tmu', label: '固定指數' }] },
  { field: 'm_ladder', title: 'M — 距離階梯', cols: [{ key: 'max_cm', label: '上限(cm)' }, { key: 'tmu', label: '指數' }] },
  { field: 'm_rotation', title: 'M — 旋轉（依直徑）', cols: [{ key: 'max_diameter_cm', label: '直徑上限(cm)' }, { key: 'revolutions', label: '圈數' }, { key: 'tmu', label: '指數' }] },
  { field: 'm_hand', title: 'M — 手部角度', cols: [{ key: 'max_deg', label: '角度上限(°)' }, { key: 'tmu', label: '指數' }] },
  { field: 'x', title: 'X — 程序時間', cols: [
    { key: 'code', label: '代碼' }, { key: 'label_zh', label: '名稱' }, { key: 'mode', label: '模式' }, { key: 'fixed_seconds', label: '固定秒' }] },
  { field: 'i', title: 'I — 對位/校準', cols: [{ key: 'code', label: '代碼' }, { key: 'label_zh', label: '名稱' }, { key: 'index', label: '指數' }] },
]

function cell(v: unknown) {
  if (v === null || v === undefined || v === '') return <span className="text-slate-300">—</span>
  if (typeof v === 'boolean') return v ? '✓' : '—'
  return String(v)
}

function Section({ title, rows, cols, open }: { title: string; rows: Record<string, unknown>[]; cols: Col[]; open?: boolean }) {
  return (
    <details open={open} className="bg-white rounded-xl border">
      <summary className="px-4 py-2 font-medium text-sm cursor-pointer select-none">{title} <span className="text-slate-400">({rows.length})</span></summary>
      <div className="px-4 pb-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="bg-slate-100 text-left">{cols.map(c => <th key={c.key} className="p-1 font-medium">{c.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t">{cols.map(c => <td key={c.key} className="p-1">{cell(r[c.key])}</td>)}</tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={cols.length} className="p-2 text-slate-400">（無）</td></tr>}
          </tbody>
        </table>
      </div>
    </details>
  )
}

export function RuleSetViewer() {
  const { data: list = [] } = useRuleSetList()
  const [code, setCode] = useState('MINIMOST_FACTORY_V1')
  const { data: full, isLoading, error } = useRuleSetFull(code)

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border p-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">Rule-set（規則表）</h2>
          <select className="border rounded px-2 py-1 text-sm" value={code} onChange={e => setCode(e.target.value)}>
            {list.length === 0 && <option value={code}>{code}</option>}
            {list.map(r => <option key={r.code} value={r.code}>{r.name_zh}（{r.code}）</option>)}
          </select>
          {full && <span className={`px-2 py-0.5 rounded text-xs ${BADGE[full.status] ?? ''}`}>{STATUS_ZH[full.status] ?? full.status}</span>}
          {full && <span className="text-sm text-slate-500">TMU 乘數 ×{full.multiplier}</span>}
        </div>
        <p className="text-xs text-slate-500 mt-2">
          這是計算 TMU 的權威依據（唯讀檢視，供 IE 參考）。MiniMOST：TMU = Σ各格指數 × 乘數；秒 = TMU × 0.036。編輯/版本化為後續功能。
        </p>
      </div>

      {isLoading && <div className="bg-white rounded-xl border p-6 text-slate-500">載入規則表…</div>}
      {error && <div className="bg-white rounded-xl border p-6 text-red-600">載入失敗：{(error as Error).message}</div>}
      {full && SECTIONS.map(s => (
        <Section key={String(s.field)} title={s.title} rows={full[s.field] as Record<string, unknown>[]} cols={s.cols} open={s.open} />
      ))}
    </div>
  )
}
