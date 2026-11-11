import { useMemo, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { canEdit as canEditFn, useMe } from '../../shared/auth/useMe'
import { ApiError } from '../../shared/api/client'
import { BandEditor } from './BandEditor'
import { OptionDialog } from './OptionDialog'
import { PARAMS, getParam, type SectionSpec } from './paramSchema'
import {
  useOptionMutations, useParamOptions, useRuleSetVersions, useSynonyms, useSynonymMutations,
  type OptionRow, type RuleSetSummary, type Synonym,
} from './api'

/**
 * L2：字典選項編輯（對照 v3-dict-editor.png）。
 *
 * 分頁標籤沿用 v3 的七參數；v2 額外有分頁內次級 tab（A/P/M），因為 v2 是 12 張
 * 不同構子表而非 v3 的單一泛型表（ADR-023 §2）。
 */

const STATUS_CODES = ['draft', 'published', 'retired']
const statusLabel = (t: TFunction, v: string) =>
  STATUS_CODES.includes(v) ? t(`dictionary.status.${v}`) : v

function VersionBadge({ v }: { v: RuleSetSummary }) {
  const { t } = useTranslation()
  if (v.is_active) return <span className="px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-800">{t('dictionary.active')}</span>
  const tone = v.status === 'draft' ? 'bg-amber-100 text-amber-800' : 'bg-slate-200 text-slate-600'
  return <span className={`px-2 py-0.5 rounded text-xs ${tone}`}>{statusLabel(t, v.status)}</span>
}

const dash = <span className="text-slate-300">—</span>

function cell(row: OptionRow, key: string | null) {
  if (!key) return dash
  const v = row[key]
  if (v === null || v === undefined || v === '') return dash
  if (typeof v === 'boolean') return v ? '✓' : dash
  return String(v)
}

/**
 * 同義詞欄：可增刪的別名層（ADR-024 §5）。
 *
 * ⚠️ 這裡的 onAdd/onDelete **刻意不經 clone-on-write gate**——同義詞可直接後補到
 * published/certified 版本（ADR-014 特例）。`readOnly` 只在「無編輯權 或 retired 終態」
 * 時為 true，此時退回純顯示（與值編輯按鈕的停用條件對齊，但語意是「別名可直接寫，
 * 唯獨終態不可」）。
 */
function SynonymCell({ code, syns, readOnly, onAdd, onDelete }: {
  code: string
  syns: Synonym[]
  readOnly: boolean
  onAdd: (raw: string) => Promise<boolean>
  onDelete: (synId: string) => void
}) {
  const { t } = useTranslation()
  const [raw, setRaw] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    const v = raw.trim()
    if (!v || busy) return
    setBusy(true)
    try {
      const ok = await onAdd(v)
      if (ok) setRaw('')   // 失敗（409/422）保留輸入供修正
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-1" data-testid={`syn-cell-${code}`}>
      {syns.map(s => (
        <span
          key={s.id}
          data-testid={`syn-chip-${s.id}`}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-xs"
        >
          {s.synonym_raw}
          {!readOnly && (
            <button
              onClick={() => onDelete(s.id)}
              aria-label={t('dictionary.optionEditor.synDeleteAria', { name: s.synonym_raw })}
              data-testid={`syn-del-${s.id}`}
              className="text-slate-400 hover:text-red-600 leading-none"
            >×</button>
          )}
        </span>
      ))}
      {syns.length === 0 && readOnly && dash}
      {!readOnly && (
        <span className="inline-flex items-center gap-1">
          <input
            value={raw}
            onChange={e => setRaw(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void submit() } }}
            disabled={busy}
            placeholder={t('dictionary.optionEditor.synPlaceholder')}
            aria-label={t('dictionary.optionEditor.synAddAria', { code })}
            data-testid={`syn-input-${code}`}
            className="border rounded px-1 py-0.5 text-xs w-16"
          />
          <button
            onClick={() => void submit()}
            disabled={busy || !raw.trim()}
            data-testid={`syn-add-${code}`}
            className="px-1.5 py-0.5 rounded border text-xs disabled:opacity-40"
          >{t('dictionary.optionEditor.synAdd')}</button>
        </span>
      )}
    </div>
  )
}

/** 選項型表格（代碼｜顯示文字｜WI 句子｜TMU｜同義詞｜啟用｜操作） */
function OptionsTable({ section, items, synonymsFor, synReadOnly, onAddSynonym, onDeleteSynonym, readOnly, onEdit, onDuplicate, onDelete, onToggle }: {
  section: SectionSpec
  items: OptionRow[]
  synonymsFor: (code: string) => Synonym[]
  /** 同義詞控制的唯讀條件（無編輯權或 retired 終態）；與值編輯的 clone 攔截無關。 */
  synReadOnly: boolean
  onAddSynonym: (optionCode: string, raw: string) => Promise<boolean>
  onDeleteSynonym: (synId: string) => void
  readOnly: boolean
  onEdit: (r: OptionRow) => void
  onDuplicate: (r: OptionRow) => void
  onDelete: (r: OptionRow) => void
  onToggle: (r: OptionRow, next: boolean) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="bg-white rounded-xl border overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-slate-100 text-left">
            <th className="p-2 font-medium">{t('dictionary.field.code')}</th>
            <th className="p-2 font-medium">{t('dictionary.field.label_zh')}</th>
            <th className="p-2 font-medium">{t('dictionary.field.sentence_text_zh')}</th>
            <th className="p-2 font-medium">{t('dictionary.field.tmu')}</th>
            <th className="p-2 font-medium">{t('dictionary.optionEditor.colSynonyms')}</th>
            <th className="p-2 font-medium">{t('dictionary.field.is_active')}</th>
            <th className="p-2 font-medium">{t('dictionary.optionEditor.colActions')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map(r => {
            const code = String(r.code ?? '')
            const syn = synonymsFor(code)
            return (
              <tr key={r.id} className="border-t" data-testid={`dict-option-${code}`}>
                <td className="p-2 font-mono text-xs">{code}</td>
                <td className="p-2">{cell(r, 'label_zh')}</td>
                <td className="p-2">{cell(r, 'sentence_text_zh')}</td>
                {/* 各子表 TMU 欄位命名不同（base_tmu/delta_tmu/index_value/fixed_tmu）；X 無此概念 → — */}
                <td className="p-2">{cell(r, section.tmuField)}</td>
                <td className="p-2 text-xs text-slate-600">
                  <SynonymCell
                    code={code}
                    syns={syn}
                    readOnly={synReadOnly}
                    onAdd={raw => onAddSynonym(code, raw)}
                    onDelete={onDeleteSynonym}
                  />
                </td>
                <td className="p-2">
                  <input
                    type="checkbox" checked={!!r.is_active} disabled={readOnly}
                    aria-label={t('dictionary.optionEditor.activeAria', { code })}
                    onChange={e => onToggle(r, e.target.checked)}
                  />
                </td>
                <td className="p-2">
                  <div className="flex gap-1">
                    <button disabled={readOnly} onClick={() => onEdit(r)} className="px-2 py-1 rounded border text-xs disabled:opacity-40">{t('dictionary.optionEditor.edit')}</button>
                    <button disabled={readOnly} onClick={() => onDuplicate(r)} className="px-2 py-1 rounded border text-xs disabled:opacity-40">{t('dictionary.optionEditor.duplicate')}</button>
                    <button disabled={readOnly} onClick={() => onDelete(r)} className="px-2 py-1 rounded border border-red-300 text-red-600 text-xs disabled:opacity-40">{t('dictionary.optionEditor.delete')}</button>
                  </div>
                </td>
              </tr>
            )
          })}
          {items.length === 0 && <tr><td colSpan={7} className="p-4 text-slate-400">{t('dictionary.optionEditor.empty')}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

export function OptionEditor({ code, onBack, onRequestEdit }: {
  code: string
  onBack: () => void
  /**
   * clone-on-write（ADR-023 §3.3 規則 2）：任何寫入前呼叫。
   * 回傳實際可寫入的 code（可能是新建的 draft）；null＝使用者取消。
   */
  onRequestEdit: () => Promise<string | null>
}) {
  const { t } = useTranslation()
  const [paramKey, setParamKey] = useState('A')
  const [sectionKey, setSectionKey] = useState('reach')
  const [dialog, setDialog] = useState<{ row: OptionRow | null } | null>(null)
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null)

  const param = getParam(paramKey)
  const section = param.sections.find(s => s.key === sectionKey) ?? param.sections[0]

  const { data: versions = [] } = useRuleSetVersions()
  const version = versions.find(v => v.code === code)
  const { data, isLoading, error } = useParamOptions(code, paramKey, section.key)
  const { data: synonyms = [] } = useSynonyms(code)
  const { data: me } = useMe()

  const mut = useOptionMutations(code, paramKey, section.key)
  const synMut = useSynonymMutations(code)

  // retired 為終態；其餘狀態的寫入透過 clone-on-write 導向 draft，故按鈕不停用
  const readOnly = !canEditFn(me) || version?.status === 'retired'

  // 契約一致性：paramSchema（本地）與 API 回應的 kind 必須一致，否則會渲染錯的編輯器
  const kindMismatch = !!data && data.kind !== section.kind

  const synMap = useMemo(() => {
    const m = new Map<string, Synonym[]>()
    for (const s of synonyms) {
      if (s.parameter !== paramKey) continue
      const list = m.get(s.option_code) ?? []
      list.push(s)
      m.set(s.option_code, list)
    }
    return m
  }, [synonyms, paramKey])

  const errText = (e: unknown) => e instanceof ApiError ? e.humanMessage : (e as Error).message

  /**
   * 同義詞新增：**直接寫入目標版本，繞過 clone-on-write gate**（ADR-024 §5 推論 2）。
   * 不呼叫 onRequestEdit——這正是同義詞與值變更的差別。回傳 true=成功（清空輸入）。
   * 409 SYNONYM_CONFLICT / 422 VALIDATION_ERROR → 顯示後端 message、保留輸入。
   */
  const addSynonym = async (optionCode: string, raw: string): Promise<boolean> => {
    setMsg(null)
    try {
      await synMut.create.mutateAsync({ parameter: paramKey, option_code: optionCode, synonym_raw: raw })
      setMsg({ tone: 'ok', text: t('dictionary.optionEditor.synAdded', { name: raw }) })
      return true
    } catch (e) {
      setMsg({ tone: 'err', text: t('dictionary.optionEditor.synAddFailed', { message: errText(e) }) })
      return false
    }
  }

  /** 同義詞刪除：同樣繞過 clone gate，直接對目標版本 DELETE。 */
  const deleteSynonym = (synId: string) => {
    setMsg(null)
    void synMut.remove.mutateAsync(synId)
      .then(() => setMsg({ tone: 'ok', text: t('dictionary.optionEditor.synDeleted') }))
      .catch(e => setMsg({ tone: 'err', text: t('dictionary.optionEditor.synDeleteFailed', { message: errText(e) }) }))
  }

  const selectParam = (k: string) => {
    setParamKey(k)
    setSectionKey(getParam(k).sections[0].key)
    setMsg(null)
  }

  /**
   * 過 clone-on-write gate，但**不產生成功訊息**。
   * 供「開啟 dialog」這類尚未寫入任何東西的動作使用——開個表單就宣告「編輯成功」是假回饋。
   * 回傳 false＝不可寫（已取消或已轉去建草稿），呼叫端不應開啟表單。
   */
  const guardedOpen = async (open: () => void): Promise<boolean> => {
    setMsg(null)
    const target = await onRequestEdit()
    // target 為 null（取消／已改去建草稿）或指向別的版本 → 本次不開表單
    if (!target || target !== code) return false
    open()
    return true
  }

  /** 包住每個**實際寫入**：先確保有可寫版本，再執行。 */
  const guarded = async (label: string, run: (target: string) => Promise<unknown>) => {
    setMsg(null)
    const target = await onRequestEdit()
    // 取消／已轉為建立草稿：訊息由 DictionaryPage 的對話框負責，此處不重複也不宣告成功
    if (!target || target !== code) return
    try {
      await run(target)
      setMsg({ tone: 'ok', text: t('dictionary.actionSucceeded', { action: label }) })
    } catch (e) {
      // CERTIFIED_IMMUTABLE / RULE_SET_FROZEN 等結構化錯誤已由 ApiError 取 message 人話
      setMsg({ tone: 'err', text: t('dictionary.actionFailed', { action: label, message: (e as Error).message }) })
    }
  }

  return (
    <div className="space-y-4" data-testid="dict-option-editor">
      {/* 頁首 */}
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={onBack} className="px-2 py-1 rounded border text-sm">{t('dictionary.optionEditor.back')}</button>
        <h2 className="font-semibold">{t('dictionary.optionEditor.title')}</h2>
        {version && <VersionBadge v={version} />}
        <span className="font-mono text-xs text-slate-400">{code}</span>
        {version?.provenance === 'certified_import' && (
          <span
            className="px-2 py-0.5 rounded text-xs bg-violet-100 text-violet-800"
            title={t('dictionary.optionEditor.certifiedTitle')}
          >
            {t('dictionary.provenance.certified_import')}
          </span>
        )}
      </div>

      {/* 參數分頁 */}
      <div className="border-b flex flex-wrap gap-1" role="tablist" aria-label={t('dictionary.optionEditor.paramTablistAria')}>
        {PARAMS.map(p => (
          <button
            key={p.key} role="tab" aria-selected={p.key === paramKey}
            onClick={() => selectParam(p.key)}
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${p.key === paramKey ? 'border-sky-600 text-sky-700 font-medium' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
          >
            {t(`dictionary.param.${p.labelKey}`)}
          </button>
        ))}
      </div>

      {/* 次級區塊（A/P/M） */}
      {param.sections.length > 1 && (
        <div className="flex flex-wrap gap-1" role="tablist" aria-label={t('dictionary.optionEditor.sectionTablistAria')}>
          {param.sections.map(s => (
            <button
              key={s.key} role="tab" aria-selected={s.key === section.key}
              onClick={() => { setSectionKey(s.key); setMsg(null) }}
              className={`px-3 py-1 rounded-full text-xs border ${s.key === section.key ? 'bg-sky-600 border-sky-600 text-white' : 'border-slate-300 text-slate-600 hover:bg-slate-50'}`}
            >
              {t(`dictionary.section.${s.labelKey}`)}
            </button>
          ))}
        </div>
      )}

      {msg && (
        <div className={`rounded-lg border px-3 py-2 text-sm ${msg.tone === 'ok' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {msg.text}
        </div>
      )}

      {isLoading && <div className="bg-white rounded-xl border p-6 text-slate-500">{t('dictionary.optionEditor.loading')}</div>}
      {error && <div className="bg-white rounded-xl border p-6 text-red-600">{t('dictionary.optionEditor.loadError', { message: (error as Error).message })}</div>}

      {data && kindMismatch && (
        <div className="bg-white rounded-xl border p-6 text-red-600 text-sm">
          <Trans
            i18nKey="dictionary.optionEditor.kindMismatch"
            values={{ backend: data.kind, frontend: section.kind }}
            components={{ b: <b /> }}
          />
        </div>
      )}

      {data && !kindMismatch && data.kind === 'options' && (
        <>
          {!readOnly && (
            <button
              onClick={() => void guardedOpen(() => setDialog({ row: null }))}
              className="px-3 py-1 rounded bg-sky-600 text-white text-sm"
            >
              + {t(`dictionary.addLabel.${section.addLabelKey ?? 'fallback'}`)}
            </button>
          )}
          <OptionsTable
            section={section}
            items={data.items}
            readOnly={readOnly}
            synonymsFor={c => synMap.get(c) ?? []}
            synReadOnly={readOnly}
            onAddSynonym={addSynonym}
            onDeleteSynonym={deleteSynonym}
            onEdit={r => void guardedOpen(() => setDialog({ row: r }))}
            onDuplicate={r => void guarded(t('dictionary.action.duplicate'), () => mut.duplicate.mutateAsync(String(r.code)))}
            onDelete={r => {
              if (!window.confirm(t('dictionary.optionEditor.confirmDelete', { code: String(r.code) }))) return
              void guarded(t('dictionary.action.delete'), () => mut.remove.mutateAsync(String(r.code)))
            }}
            onToggle={(r, next) =>
              void guarded(t('dictionary.action.toggleActive'), () =>
                mut.update.mutateAsync({ optionCode: String(r.code), payload: { is_active: next } }))
            }
          />
          <p className="text-xs text-slate-400">
            <Trans i18nKey="dictionary.optionEditor.synNote" components={{ b: <b /> }} />
          </p>
        </>
      )}

      {data && !kindMismatch && data.kind === 'bands' && (
        <BandEditor
          section={section}
          items={data.items}
          readOnly={readOnly}
          onSave={async items => {
            const target = await onRequestEdit()
            // 取消／已轉為建立草稿 → 不寫入、不報錯（訊息由 DictionaryPage 對話框負責），
            // 且**保留使用者的編輯內容與 dirty 狀態**，不假裝已儲存。
            if (!target || target !== code) return 'aborted'
            await mut.replaceBands.mutateAsync(items)
            return 'saved'
          }}
        />
      )}

      {dialog && (
        <OptionDialog
          section={section}
          row={dialog.row}
          onCancel={() => setDialog(null)}
          onSubmit={async payload => {
            if (dialog.row) {
              await mut.update.mutateAsync({ optionCode: String(dialog.row.code), payload })
            } else {
              await mut.create.mutateAsync(payload)
            }
            setDialog(null)
            setMsg({ tone: 'ok', text: t('dictionary.optionEditor.saved') })
          }}
        />
      )}
    </div>
  )
}
