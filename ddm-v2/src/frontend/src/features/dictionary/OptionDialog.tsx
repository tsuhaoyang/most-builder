import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { resolveErrorMessage } from '../../shared/i18n/errorMessage'
import type { FieldSpec, SectionSpec } from './paramSchema'
import type { OptionRow } from './api'

/**
 * 選項編輯 dialog（對照 v3-dict-option-edit.png）。
 *
 * 欄位由 `SectionSpec.fields` 驅動＝後端 schema 的 model_fields，
 * 不自行增減欄位（後端 `extra='forbid'`，多送欄位會 422）。
 */

function initial(section: SectionSpec, row: OptionRow | null): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of section.fields) {
    const v = row ? row[f.key] : undefined
    if (v !== undefined) { out[f.key] = v; continue }
    // 新增時的空白值：不猜業務預設，只給型別上的空值
    out[f.key] = f.type === 'bool' ? (f.key === 'is_active') : f.type === 'int' || f.type === 'float' ? (f.nullable ? null : 0) : f.type === 'select' ? (f.choices?.[0]?.value ?? null) : f.nullable ? null : ''
  }
  return out
}

function Field({ spec, value, onChange, disabled }: {
  spec: FieldSpec
  value: unknown
  onChange: (v: unknown) => void
  disabled: boolean
}) {
  const { t } = useTranslation()
  const id = `fld-${spec.key}`
  const common = 'w-full border rounded px-2 py-1 text-sm disabled:bg-slate-100 disabled:text-slate-400'

  const control = () => {
    if (spec.type === 'bool') {
      return (
        <input
          id={id} type="checkbox" disabled={disabled}
          checked={!!value}
          onChange={e => onChange(e.target.checked)}
          className="h-4 w-4"
        />
      )
    }
    if (spec.type === 'select') {
      return (
        <select
          id={id} disabled={disabled} className={common}
          value={value === null || value === undefined ? '' : String(value)}
          onChange={e => onChange(e.target.value === '' ? null : e.target.value)}
        >
          {spec.choices?.map(c => (
            <option key={String(c.value)} value={c.value === null ? '' : c.value}>{t(`dictionary.choice.${c.labelKey}`)}</option>
          ))}
        </select>
      )
    }
    if (spec.type === 'int' || spec.type === 'float') {
      return (
        <input
          id={id} type="number" disabled={disabled} className={common}
          step={spec.type === 'int' ? 1 : 'any'}
          value={value === null || value === undefined ? '' : String(value)}
          onChange={e => {
            const raw = e.target.value
            if (raw === '') { onChange(spec.nullable ? null : '') ; return }
            const n = spec.type === 'int' ? parseInt(raw, 10) : parseFloat(raw)
            onChange(Number.isNaN(n) ? raw : n)
          }}
        />
      )
    }
    return (
      <input
        id={id} type="text" disabled={disabled} className={common}
        value={value === null || value === undefined ? '' : String(value)}
        onChange={e => onChange(e.target.value === '' && spec.nullable ? null : e.target.value)}
      />
    )
  }

  return (
    <div className="grid grid-cols-[7rem_1fr] items-center gap-3">
      <label htmlFor={id} className="text-sm text-slate-600 text-right">{t(`dictionary.field.${spec.labelKey}`)}</label>
      <div>
        {control()}
        {spec.hintKey && <p className="text-xs text-slate-400 mt-0.5">{t(`dictionary.hint.${spec.hintKey}`)}</p>}
      </div>
    </div>
  )
}

export function OptionDialog({ section, row, onCancel, onSubmit }: {
  section: SectionSpec
  /** null＝新增 */
  row: OptionRow | null
  onCancel: () => void
  onSubmit: (payload: Record<string, unknown>) => Promise<void>
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState(() => initial(section, row))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const isEdit = row !== null

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      // 編輯時不送不可變欄位（code 是定址鍵）
      const payload = Object.fromEntries(
        Object.entries(form).filter(([k]) => !(isEdit && section.fields.find(f => f.key === k)?.immutableOnEdit)),
      )
      await onSubmit(payload)
    } catch (e) {
      setErr(resolveErrorMessage(e, t))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-full flex flex-col" data-testid="dict-option-dialog">
        <div className="flex items-center px-4 py-3 border-b">
          <h3 className="font-medium">{isEdit ? t('dictionary.optionDialog.editTitle') : t('dictionary.optionDialog.createTitle')}</h3>
          <button onClick={onCancel} className="ml-auto text-slate-400 hover:text-slate-700" aria-label={t('dictionary.optionDialog.closeAria')}>✕</button>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto">
          {section.fields.map(f => (
            <Field
              key={f.key} spec={f} value={form[f.key]} disabled={busy || (isEdit && !!f.immutableOnEdit)}
              onChange={v => setForm(s => ({ ...s, [f.key]: v }))}
            />
          ))}
          {err && <p className="text-sm text-red-600 whitespace-pre-wrap">{err}</p>}
        </div>

        <div className="flex justify-end gap-2 px-4 py-3 border-t">
          <button onClick={onCancel} disabled={busy} className="px-3 py-1 rounded border text-sm">{t('dictionary.optionDialog.cancel')}</button>
          <button onClick={() => void submit()} disabled={busy} className="px-3 py-1 rounded bg-sky-600 text-white text-sm disabled:opacity-50">
            {busy ? t('dictionary.optionDialog.saving') : t('dictionary.optionDialog.save')}
          </button>
        </div>
      </div>
    </div>
  )
}
