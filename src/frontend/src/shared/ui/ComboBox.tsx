import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface ComboOption { v: string; l: string }

// 可搜尋下拉：輸入即過濾；找不到且有 onCreate 時顯示「＋新增『…』」。移植 html_con 的 comboBox。
export function ComboBox({ options, value, onPick, placeholder, onCreate }: {
  options: ComboOption[]
  value: string
  onPick: (v: string) => void
  placeholder?: string
  onCreate?: (label: string) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const cur = options.find(o => o.v === value)
  const [text, setText] = useState(cur?.l ?? '')
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 外部 value/options 變動 → 同步顯示文字（例如新增詞彙後選中、或切換列）
  useEffect(() => { setText(options.find(o => o.v === value)?.l ?? '') }, [value, options])

  const ql = q.trim().toLowerCase()
  const filtered = options.filter(o => o.l.toLowerCase().includes(ql)).slice(0, 60)
  const canCreate = !!onCreate && !!q.trim() && !options.some(o => o.l.toLowerCase() === ql)

  return (
    <span className="relative inline-block w-full min-w-0 align-middle">
      <input
        className="w-full min-w-0 border rounded px-1 py-0.5 text-sm"
        value={text} placeholder={placeholder ?? t('comboBox.searchPlaceholder')} autoComplete="off"
        onFocus={() => { setQ(''); setOpen(true) }}
        onChange={e => { setText(e.target.value); setQ(e.target.value); setOpen(true) }}
        onBlur={() => { blurTimer.current = setTimeout(() => setOpen(false), 150) }}
      />
      {open && (
        <div className="absolute left-0 top-full mt-0.5 z-30 w-full min-w-0 bg-white border rounded shadow max-h-52 overflow-auto text-sm">
          {filtered.map(o => (
            <div key={o.v} className="px-2 py-1 hover:bg-slate-100 cursor-pointer truncate"
              title={o.l}
              onMouseDown={e => { e.preventDefault(); onPick(o.v); setText(o.l); setOpen(false) }}>
              {o.l}
            </div>
          ))}
          {canCreate && (
            <div className="px-2 py-1 text-blue-600 hover:bg-blue-50 cursor-pointer"
              onMouseDown={e => { e.preventDefault(); setOpen(false); onCreate!(q.trim()) }}>
              {t('comboBox.addNew', { label: q.trim() })}
            </div>
          )}
          {filtered.length === 0 && !canCreate && <div className="px-2 py-1 text-slate-400">{t('comboBox.noMatch')}</div>}
        </div>
      )}
    </span>
  )
}
