import { useMemo, useState, type ReactNode } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { ConfirmDialog } from './ConfirmDialog'
import { DiffView } from './DiffView'
import { canEdit as canEditFn, canPublish as canPublishFn, useMe } from '../../shared/auth/useMe'
import { describeInUse, exportRuleSet, useRuleSetDiff, useRuleSetVersions, useVersionMutations, type RuleSetSummary } from './api'
import i18n from '../../shared/i18n/i18n'

/**
 * L1：字典版本清單（對照 v3 DictionariesPage 版本區）。
 *
 * 與 v3 的差異：v3 狀態只有「啟用/草稿」兩態，v2 是 `status`（draft/published/retired）
 * × `is_active` 兩維（ADR-023 §3.2），故狀態欄顯示 status 徽章，active 另加綠色「啟用中」。
 */

const STATUS_CODES = ['draft', 'published', 'retired']
const STATUS_STYLE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  published: 'bg-sky-100 text-sky-800',
  retired: 'bg-slate-200 text-slate-600',
}
const PROVENANCE_CODES = ['certified_import', 'manual', 'cloned']

/** 未知的 status／provenance 原樣顯示（後端新增列舉值時不會變成空白）。 */
const statusLabel = (t: TFunction, v: string) =>
  STATUS_CODES.includes(v) ? t(`dictionary.status.${v}`) : v
const provenanceLabel = (t: TFunction, v: string | null | undefined) =>
  v ? (PROVENANCE_CODES.includes(v) ? t(`dictionary.provenance.${v}`) : v) : '—'

interface ConfirmState {
  label: string
  title: string
  body: ReactNode
  confirmLabel: string
  tone: 'warn' | 'danger'
  requireText?: string
  run: () => Promise<unknown>
  /** 把特定錯誤轉成人話（回 null＝沿用一般訊息）。 */
  describeError?: (err: unknown) => string | null
  /** 內嵌此版本相對 active 的差異；載入中/失敗時擋住確認鈕。 */
  showDiffFor?: string
}

// 日期格式跟著 UI 語言走（ADR-032）：原本寫死 'zh-TW'，英文介面會出現
// 「Created: 2026/8/4 下午2:50:58」這種半中文的日期。`i18n.language` 的值域就是
// SUPPORTED_LOCALES（'zh-TW' | 'en'），兩者都是合法 BCP-47 標籤；中文下仍是
// 'zh-TW'，所以中文的呈現逐字不變。
const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(i18n.language) : '—'

function StatusCell({ v }: { v: RuleSetSummary }) {
  const { t } = useTranslation()
  return (
    <span className="flex flex-wrap items-center gap-1">
      <span className={`px-2 py-0.5 rounded text-xs ${STATUS_STYLE[v.status] ?? 'bg-slate-100'}`}>
        {statusLabel(t, v.status)}
      </span>
      {v.is_active && (
        <span className="px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-800">{t('dictionary.active')}</span>
      )}
    </span>
  )
}

const Btn = ({ tone = 'plain', ...p }: { tone?: 'plain' | 'ok' | 'warn' | 'danger' } & React.ButtonHTMLAttributes<HTMLButtonElement>) => {
  const tones = {
    plain: 'border-slate-300 text-slate-700 hover:bg-slate-50',
    ok: 'border-emerald-500 bg-emerald-500 text-white hover:bg-emerald-600',
    warn: 'border-amber-500 bg-amber-500 text-white hover:bg-amber-600',
    danger: 'border-red-300 text-red-600 hover:bg-red-50',
  }
  return (
    <button
      {...p}
      className={`px-2 py-1 rounded border text-xs disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]} ${p.className ?? ''}`}
    />
  )
}

export function VersionList({ onOpen }: { onOpen: (code: string) => void }) {
  const { t } = useTranslation()
  const { data: versions = [], isLoading, error } = useRuleSetVersions()
  const { data: me } = useMe()
  const canEdit = canEditFn(me)
  const canPublish = canPublishFn(me)
  const { publish, activate, retire, unretire, remove } = useVersionMutations()
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const [busy, setBusy] = useState(false)
  const [cErr, setCErr] = useState<string | null>(null)

  const [diffCode, setDiffCode] = useState<string | null>(null)

  // 確認框內嵌的差異（publish/activate）；獨立檢視另有 diffCode
  const confirmDiff = useRuleSetDiff(confirm?.showDiffFor ?? null)
  const panelDiff = useRuleSetDiff(diffCode)
  // 差異未取得（載入中或失敗）→ 不得讓確認鈕可按而假裝沒有差異
  const diffBlocked = !!confirm?.showDiffFor && (confirmDiff.isLoading || !!confirmDiff.error)

  const active = useMemo(() => versions.find(v => v.is_active) ?? null, [versions])

  const run = async (label: string, fn: () => Promise<unknown>) => {
    try {
      await fn()
      setMsg({ tone: 'ok', text: t('dictionary.actionSucceeded', { action: label }) })
    } catch (e) {
      setMsg({ tone: 'err', text: t('dictionary.actionFailed', { action: label, message: (e as Error).message }) })
    }
  }

  const runConfirmed = async () => {
    if (!confirm) return
    setBusy(true); setCErr(null)
    try {
      await confirm.run()
      setMsg({ tone: 'ok', text: t('dictionary.actionSucceeded', { action: confirm.label }) })
      setConfirm(null)
    } catch (e) {
      setCErr(confirm.describeError?.(e) ?? (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  /**
   * activate 的確認文案必須說明「不回溯」：`activate` 只 UPDATE `rule_sets.is_active`，
   * 不碰任何 module/cycle；而 publish 已把 `computed.total_tmu` 寫進 rows JSON 並凍結
   * `rule_set_id`。故誤按後切回去不會修正期間內已落盤的值。
   */
  /** 發布＝兩人覆核的決定點：必須看得到「被覆核的是什麼」（H-1）。 */
  const askPublish = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: t('dictionary.action.publish'),
      title: t('dictionary.versionList.publishTitle'),
      tone: 'warn',
      confirmLabel: t('dictionary.versionList.publishConfirm'),
      showDiffFor: v.code,
      run: () => publish.mutateAsync(v.code),
      body: (
        <>
          <p><Trans i18nKey="dictionary.versionList.publishBody1" values={{ code: v.code }} components={{ code: <span className="font-mono" /> }} /></p>
          <p className="text-xs text-slate-500">{t('dictionary.versionList.publishBody2')}</p>
        </>
      ),
    })
  }

  const askActivate = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: t('dictionary.action.activate'),
      title: t('dictionary.versionList.activateTitle'),
      tone: 'warn',
      confirmLabel: t('dictionary.versionList.activateConfirm'),
      showDiffFor: v.code,
      run: () => activate.mutateAsync(v.code),
      body: (
        <>
          <p>
            <Trans
              i18nKey={active ? 'dictionary.versionList.activateBody1WithActive' : 'dictionary.versionList.activateBody1'}
              values={{ code: v.code, active: active?.code }}
              components={{ code: <span className="font-mono" /> }}
            />
          </p>
          <p className="text-amber-800">
            <Trans i18nKey="dictionary.versionList.activateBody2" components={{ b: <b /> }} />
          </p>
        </>
      ),
    })
  }

  /** 封存可逆（D3b 起有 unretire）→ 一般確認即可，不要求打字。 */
  const askRetire = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: t('dictionary.action.retire'),
      title: t('dictionary.versionList.retireTitle'),
      tone: 'warn',
      confirmLabel: t('dictionary.versionList.retireConfirm'),
      run: () => retire.mutateAsync(v.code),
      body: (
        <>
          <p><Trans i18nKey="dictionary.versionList.retireBody1" values={{ code: v.code }} components={{ code: <span className="font-mono" /> }} /></p>
          <p><Trans i18nKey="dictionary.versionList.retireBody2" components={{ b: <b /> }} /></p>
          <p className="text-xs text-slate-500">
            {t('dictionary.versionList.retireBody3')}
          </p>
        </>
      ),
    })
  }

  /** 解除封存：retired → published，**is_active 維持 false**（解封 ≠ 啟用）。 */
  const askUnretire = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: t('dictionary.action.unretire'),
      title: t('dictionary.versionList.unretireTitle'),
      tone: 'warn',
      confirmLabel: t('dictionary.versionList.unretireConfirm'),
      run: () => unretire.mutateAsync(v.code),
      body: (
        <>
          <p><Trans i18nKey="dictionary.versionList.unretireBody1" values={{ code: v.code }} components={{ code: <span className="font-mono" /> }} /></p>
          <p className="text-amber-800">
            <Trans i18nKey="dictionary.versionList.unretireBody2" components={{ b: <b /> }} />
          </p>
        </>
      ),
    })
  }

  /** 刪除是本頁唯一真正不可逆的操作（實體刪除＋13 張子表級聯）→ 強制打字確認。 */
  const askDelete = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: t('dictionary.action.delete'),
      title: t('dictionary.versionList.deleteTitle'),
      tone: 'danger',
      confirmLabel: t('dictionary.versionList.deleteConfirm'),
      requireText: v.code,
      run: () => remove.mutateAsync(v.code),
      // 被引用時後端回 RULE_SET_IN_USE，把各表引用筆數說成人話
      describeError: describeInUse,
      body: (
        <>
          <p><Trans i18nKey="dictionary.versionList.deleteBody1" values={{ code: v.code }} components={{ b: <b />, code: <span className="font-mono" /> }} /></p>
          <p className="text-red-700"><Trans i18nKey="dictionary.versionList.deleteBody2" components={{ b: <b /> }} /></p>
          <p className="text-xs text-slate-500">
            {t('dictionary.versionList.deleteBody3')}
          </p>
        </>
      ),
    })
  }

  const doExport = async (code: string) => {
    try {
      const data = await exportRuleSet(code)
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      )
      const a = document.createElement('a')
      a.href = url
      a.download = `${code}.json`
      a.click()
      URL.revokeObjectURL(url)
      setMsg({ tone: 'ok', text: t('dictionary.versionList.exported', { file: `${code}.json` }) })
    } catch (e) {
      setMsg({ tone: 'err', text: t('dictionary.versionList.exportFailed', { message: (e as Error).message }) })
    }
  }

  if (isLoading) return <div className="bg-white rounded-xl border p-6 text-slate-500">{t('dictionary.versionList.loading')}</div>
  if (error) return <div className="bg-white rounded-xl border p-6 text-red-600">{t('dictionary.versionList.loadError', { message: (error as Error).message })}</div>

  return (
    <div className="space-y-4" data-testid="dict-version-list">
      <h2 className="text-lg font-semibold">{t('dictionary.versionList.heading')}</h2>

      {msg && (
        <div className={`rounded-lg border px-3 py-2 text-sm ${msg.tone === 'ok' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {msg.text}
        </div>
      )}

      {/* 啟用中版本卡片（v3 active-card） */}
      {active && (
        <div className="bg-white rounded-xl border" data-testid="dict-active-card">
          <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b">
            <span className="px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-800">{t('dictionary.active')}</span>
            <span className="font-medium">{active.name_zh}</span>
            <span className="font-mono text-xs text-slate-400">{active.code}</span>
            <div className="ml-auto flex gap-2">
              <Btn onClick={() => onOpen(active.code)}>{t('dictionary.versionList.editDict')}</Btn>
              <Btn onClick={() => void doExport(active.code)}>{t('dictionary.versionList.exportJson')}</Btn>
            </div>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 px-4 py-2 text-xs text-slate-500">
            <span>{t('dictionary.versionList.source', { value: provenanceLabel(t, active.provenance) })}</span>
            <span>{t('dictionary.versionList.created', { value: fmtDate(active.created_at) })}</span>
            <span>{t('dictionary.versionList.notes', { value: active.notes || '—' })}</span>
          </div>
        </div>
      )}

      {/* 版本表格 */}
      <div className="bg-white rounded-xl border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 text-left">
              <th className="p-2 font-medium">{t('dictionary.versionList.col.name')}</th>
              <th className="p-2 font-medium">{t('dictionary.versionList.col.status')}</th>
              <th className="p-2 font-medium">{t('dictionary.versionList.col.source')}</th>
              <th className="p-2 font-medium">{t('dictionary.versionList.col.created')}</th>
              <th className="p-2 font-medium">{t('dictionary.versionList.col.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {versions.map(v => (
              <tr key={v.code} className="border-t align-top" data-testid={`dict-version-${v.code}`}>
                <td className="p-2">
                  <span className="block">{v.name_zh}</span>
                  <span className="block font-mono text-xs text-slate-400">{v.code}</span>
                </td>
                <td className="p-2"><StatusCell v={v} /></td>
                <td className="p-2 text-slate-600">
                  {provenanceLabel(t, v.provenance)}
                </td>
                <td className="p-2 text-slate-600 whitespace-nowrap">{fmtDate(v.created_at)}</td>
                <td className="p-2">
                  <div className="flex flex-wrap gap-1">
                    {v.status === 'retired' ? (
                      <>
                        <Btn onClick={() => onOpen(v.code)}>{t('dictionary.versionList.view')}</Btn>
                        <Btn tone="ok" disabled={!canPublish} onClick={() => askUnretire(v)}>{t('dictionary.versionList.unretire')}</Btn>
                      </>
                    ) : (
                      <Btn
                        onClick={() => onOpen(v.code)}
                        disabled={!canEdit}
                        title={
                          v.provenance === 'certified_import'
                            ? t('dictionary.versionList.editTitleCertified')
                            : v.status !== 'draft'
                              ? t('dictionary.versionList.editTitlePublished')
                              : undefined
                        }
                      >
                        {t('dictionary.versionList.edit')}
                      </Btn>
                    )}

                    {v.status === 'draft' && (
                      <Btn tone="ok" disabled={!canPublish} onClick={() => askPublish(v)}>
                        {t('dictionary.versionList.publish')}
                      </Btn>
                    )}

                    {v.status === 'published' && !v.is_active && (
                      <Btn tone="ok" disabled={!canPublish} onClick={() => askActivate(v)}>
                        {t('dictionary.versionList.activate')}
                      </Btn>
                    )}

                    {v.status === 'published' && !v.is_active && (
                      <Btn tone="warn" disabled={!canPublish} onClick={() => askRetire(v)}>
                        {t('dictionary.versionList.retire')}
                      </Btn>
                    )}

                    {/* 僅 draft 可刪（D3b）；本頁唯一不可逆操作 → type-to-confirm */}
                    {v.status === 'draft' && (
                      <Btn tone="danger" disabled={!canEdit} onClick={() => askDelete(v)}>
                        {t('dictionary.versionList.delete')}
                      </Btn>
                    )}

                    {(v.status === 'draft' || v.status === 'published') && canEdit && (
                      <Btn onClick={() => setDiffCode(v.code)}>{t('dictionary.versionList.viewDiff')}</Btn>
                    )}

                    {/* 匯出為唯讀操作，viewer 亦可用 */}
                    <Btn onClick={() => void doExport(v.code)}>{t('dictionary.versionList.export')}</Btn>
                  </div>
                </td>
              </tr>
            ))}
            {versions.length === 0 && (
              <tr><td colSpan={5} className="p-4 text-slate-400">{t('dictionary.versionList.empty')}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          body={
            <>
              {confirm.body}
              {confirm.showDiffFor && (
                <div className="pt-2 border-t mt-2">
                  <p className="text-sm font-medium mb-1">{t('dictionary.versionList.whatChanges')}</p>
                  <DiffView
                    data={confirmDiff.data}
                    isLoading={confirmDiff.isLoading}
                    error={confirmDiff.error}
                    compact
                  />
                </div>
              )}
            </>
          }
          confirmLabel={confirm.confirmLabel}
          tone={confirm.tone}
          requireText={confirm.requireText}
          busy={busy}
          error={cErr}
          blockConfirm={diffBlocked}
          blockReason={confirmDiff.isLoading ? t('dictionary.versionList.diffLoading') : t('dictionary.versionList.diffUnavailable')}
          onCancel={() => { setConfirm(null); setCErr(null) }}
          onConfirm={() => void runConfirmed()}
        />
      )}

      {diffCode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-full flex flex-col" data-testid="dict-diff-panel">
            <div className="flex items-center px-4 py-3 border-b">
              <h3 className="font-medium">{t('dictionary.versionList.diffPanelTitle')}</h3>
              <span className="ml-2 font-mono text-xs text-slate-400">{diffCode}</span>
              <button onClick={() => setDiffCode(null)} className="ml-auto text-slate-400 hover:text-slate-700" aria-label={t('dictionary.versionList.closeAria')}>✕</button>
            </div>
            <div className="p-4 overflow-y-auto">
              <DiffView data={panelDiff.data} isLoading={panelDiff.isLoading} error={panelDiff.error} />
            </div>
            <div className="flex justify-end px-4 py-3 border-t">
              <button onClick={() => setDiffCode(null)} className="px-3 py-1 rounded border text-sm">{t('dictionary.versionList.close')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
