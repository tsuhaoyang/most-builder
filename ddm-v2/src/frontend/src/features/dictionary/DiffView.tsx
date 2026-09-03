import { useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { resolveErrorMessage } from '../../shared/i18n/errorMessage'
import type { TFunction } from 'i18next'
import type { DiffChanged, DiffSection, RuleSetDiff } from './api'

/**
 * 版本值差異呈現（ADR-023 D7 / H-1）。
 *
 * 覆核者要回答的問題是「按下發布之後，**線上的值**會從什麼變成什麼」，
 * 所以 TMU／數值欄最顯眼，文案欄次之，`row_counts` 讓「整批被換掉的區塊」一眼可見。
 *
 * **前端不計算差異**（守則 §7 第 3 條）：全部用後端回的 `diff`。本檔只做「呈現後端已算好的
 * 事實」——讀 `summary` 選一句文案不是推導值，判準是「這個數字是誰算的」。
 *
 * 三個邊界狀態必須誠實區分，不得都顯示成「無差異」：
 * 沒有比較對象（compared_with_self）／逐欄相同（identical）／取不到（載入失敗）。
 *
 * ## 為什麼 `identical` 不夠用，還需要「值未變動」這條分支
 *
 * 實測：`clone_draft` 會在 `name_zh` 後綴「 (草稿)」，所以**剛 clone 出來、一個字都沒改的
 * 草稿也不是 `identical`**（`header_changed: ["name_zh"]`、區塊 0/0/0）。若只有 `identical`
 * 一種「安全」呈現，這種最常見的情況會顯示成一般差異，覆核者反而要自己看懂
 * 「0 筆變更但不是 identical」代表什麼。
 *
 * 但「僅表頭變動」**不等於**「值未變動」：後端 `HEADER_FIELDS` 含 `multiplier`，
 * 而乘數等比縮放該版本每一個 TMU。見 `VALUE_AFFECTING_HEADER_FIELDS`。
 */

/**
 * 區塊名與欄位名的顯示文字都在 `dictionary.diffSection.*` / `dictionary.field.*`
 * （後者與 `paramSchema.ts` 的欄位標籤**共用同一份**——兩邊本來各抄一份同樣的
 * 中文，改一邊忘另一邊就會出現「同一個欄位在編輯器叫 A、在差異頁叫 B」）。
 * 後端若回一個對照表沒有的鍵，沿用原始鍵名（不隱形變空白）。
 */

/**
 * 直接決定 TMU 的欄位 —— 這些變了，線上工時就變。
 * 呈現優先序最高（守則：覆核者關心的是「值」而不是文案）。
 */
const VALUE_FIELDS = new Set([
  'multiplier', 'base_tmu', 'delta_tmu', 'index_value', 'fixed_tmu', 'tmu', 'index',
  'fixed_seconds', 'max_value', 'max_cm', 'max_deg', 'max_diameter_cm', 'revolutions',
])

/**
 * 版本表頭中**會影響計算結果**的欄位。
 *
 * 語意必須與後端 `rule_set_diff.HEADER_FIELDS`（目前 `("name_zh", "multiplier")`）對齊：
 * 該元組列出「表頭上會被 diff 的欄」，本集合則是其中「改了會讓工時變動」的子集。
 * - `multiplier`：**等比縮放該版本的每一個 TMU** → 屬於此集合
 * - `name_zh`：純標示，不參與計算 → 不屬於
 *
 * ⚠️ 後端若新增第三個 header 欄，**這裡是唯一要跟著改的地方**——
 * 判斷「值有沒有變」的邏輯只讀這個常數，不得在別處另寫一份清單。
 */
const VALUE_AFFECTING_HEADER_FIELDS = new Set(['multiplier'])

const fieldLabel = (t: TFunction, f: string) => t(`dictionary.field.${f}`, { defaultValue: f })
const sectionLabel = (t: TFunction, s: string) => t(`dictionary.diffSection.${s}`, { defaultValue: s })

function Val({ v }: { v: unknown }) {
  const { t } = useTranslation()
  if (v === null || v === undefined) return <span className="text-slate-400">{t('dictionary.diff.none')}</span>
  if (typeof v === 'boolean') return <>{v ? t('dictionary.diff.yes') : t('dictionary.diff.no')}</>
  if (v === '') return <span className="text-slate-400">{t('dictionary.diff.empty')}</span>
  return <>{String(v)}</>
}

/** 前 → 後。數值欄用較強的視覺權重。 */
function Delta({ field, before, after }: { field: string; before: unknown; after: unknown }) {
  const { t } = useTranslation()
  const strong = VALUE_FIELDS.has(field)
  return (
    <div className={`flex flex-wrap items-baseline gap-1 ${strong ? 'text-sm' : 'text-xs'}`}>
      <span className={strong ? 'font-medium text-slate-700' : 'text-slate-500'}>
        {fieldLabel(t, field)}
      </span>
      <span className={strong ? 'text-red-700 line-through' : 'text-slate-400 line-through'}><Val v={before} /></span>
      <span className="text-slate-400">→</span>
      <span className={strong ? 'font-semibold text-emerald-700' : 'text-slate-600'}><Val v={after} /></span>
      {strong && <span className="text-[10px] text-amber-700 border border-amber-300 rounded px-1">{t('dictionary.diff.affectsTime')}</span>}
    </div>
  )
}

/** 數值欄排前面 */
const sortFields = (fields: Record<string, { before: unknown; after: unknown }>) =>
  Object.entries(fields).sort(([a], [b]) => {
    const av = VALUE_FIELDS.has(a) ? 0 : 1
    const bv = VALUE_FIELDS.has(b) ? 0 : 1
    return av !== bv ? av - bv : a.localeCompare(b)
  })

function ChangedRow({ item }: { item: DiffChanged }) {
  const hasValueChange = Object.keys(item.fields).some(f => VALUE_FIELDS.has(f))
  return (
    <li className="py-1">
      <div className="flex items-start gap-2">
        <span className={`font-mono text-xs shrink-0 ${hasValueChange ? 'text-slate-800 font-semibold' : 'text-slate-500'}`}>
          {item.key}
        </span>
        <div className="space-y-0.5">
          {sortFields(item.fields).map(([f, d]) => (
            <Delta key={f} field={f} before={d.before} after={d.after} />
          ))}
        </div>
      </div>
    </li>
  )
}

function SectionBlock({ name, sec, counts }: {
  name: string
  sec: DiffSection
  counts?: { before: number; after: number }
}) {
  const { t } = useTranslation()
  const added = sec.added ?? []
  const removed = sec.removed ?? []
  const changed = sec.changed ?? []
  const bulk = counts && counts.before !== counts.after
  return (
    <details className="border rounded-lg" open={changed.some(c => Object.keys(c.fields).some(f => VALUE_FIELDS.has(f)))}>
      <summary className="px-3 py-2 text-sm cursor-pointer select-none flex flex-wrap items-center gap-2">
        <span className="font-medium">{sectionLabel(t, name)}</span>
        {added.length > 0 && <span className="text-xs px-1.5 rounded bg-emerald-100 text-emerald-800">+{added.length}</span>}
        {removed.length > 0 && <span className="text-xs px-1.5 rounded bg-red-100 text-red-800">−{removed.length}</span>}
        {changed.length > 0 && <span className="text-xs px-1.5 rounded bg-amber-100 text-amber-800">{t('dictionary.diff.changedCount', { n: changed.length })}</span>}
        {counts && (
          <span className={`text-xs ${bulk ? 'text-amber-700 font-medium' : 'text-slate-400'}`}>
            {t('dictionary.diff.rowCounts', { before: counts.before, after: counts.after })}
          </span>
        )}
      </summary>
      <div className="px-3 pb-2 space-y-2">
        {changed.length > 0 && (
          <ul className="divide-y">{changed.map(c => <ChangedRow key={c.key} item={c} />)}</ul>
        )}
        {added.length > 0 && (
          <div className="text-xs">
            <span className="text-emerald-800 font-medium">{t('dictionary.diff.addedLabel')}</span>
            <span className="font-mono text-slate-600">{added.map(a => a.key).join(t('dictionary.listSeparator'))}</span>
          </div>
        )}
        {removed.length > 0 && (
          <div className="text-xs">
            <span className="text-red-800 font-medium">{t('dictionary.diff.removedLabel')}</span>
            <span className="font-mono text-slate-600">{removed.map(r => r.key).join(t('dictionary.listSeparator'))}</span>
          </div>
        )}
      </div>
    </details>
  )
}

/** 血緣揭露：base 不是本版的 clone 來源時，diff 混了既有落差與本次編輯。 */
function Lineage({ d }: { d: RuleSetDiff }) {
  const { t } = useTranslation()
  if (d.base_is_source === false) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="diff-lineage-warning">
        <p className="font-medium">{t('dictionary.diff.lineageTitle')}</p>
        {/* 後端已備 lineage_note，優先顯示它 */}
        <p>{d.lineage_note ?? t('dictionary.diff.lineageFallback', { base: d.base_code, source: d.source_code })}</p>
      </div>
    )
  }
  if (d.source_code === null) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600" data-testid="diff-lineage-unknown">
        <Trans i18nKey="dictionary.diff.lineageUnknown" values={{ base: d.base_code }} components={{ b: <b /> }} />
      </div>
    )
  }
  return null
}

export function DiffView({ data, isLoading, error, compact }: {
  data: RuleSetDiff | undefined
  isLoading: boolean
  error: unknown
  /** 內嵌於確認框時用較緊湊的排版 */
  compact?: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(!compact)

  if (isLoading) {
    return <p className="text-sm text-slate-500" data-testid="diff-loading">{t('dictionary.diff.loading')}</p>
  }
  // 取不到差異＝未知，**不得**呈現為「無差異」
  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="diff-error">
        <p className="font-medium">{t('dictionary.diff.errorTitle')}</p>
        <p className="text-xs">{resolveErrorMessage(error, t)}</p>
        <p className="text-xs">{t('dictionary.diff.errorHint')}</p>
      </div>
    )
  }
  if (!data) return null

  const { summary, sections, row_counts, header } = data.diff

  // 邊界狀態一：本版就是目前 active，沒有比較對象（先判斷——此時 identical 也會是 true）
  if (data.compared_with_self) {
    return (
      <div className="rounded-lg border bg-slate-50 px-3 py-2 text-sm text-slate-600" data-testid="diff-self">
        <Trans i18nKey="dictionary.diff.self" values={{ base: data.base_code }} components={{ b: <b /> }} />
      </div>
    )
  }

  const headerEntries = Object.entries(header)

  // 以下兩者皆直接讀後端算好的 summary（前端不重算差異，只是選一句文案呈現）
  const noSectionChanges =
    summary.added === 0 && summary.removed === 0 && summary.changed === 0 &&
    summary.changed_sections.length === 0
  const headerValueFields = summary.header_changed.filter(f => VALUE_AFFECTING_HEADER_FIELDS.has(f))

  return (
    <div className="space-y-2" data-testid="diff-view">
      <div className="text-xs text-slate-600">
        {t('dictionary.diff.baseLabel')}<span className="font-mono">{data.base_code}</span>
        <span className="text-slate-400">{t('dictionary.diff.baseActive')}</span>
      </div>

      <Lineage d={data} />

      {/* 邊界狀態二：確實逐欄相同 */}
      {summary.identical ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800" data-testid="diff-identical">
          <Trans i18nKey="dictionary.diff.identical" values={{ base: data.base_code }} components={{ b: <b />, code: <span className="font-mono" /> }} />
        </div>
      ) : (
        <>
          {/*
            「區塊逐列全同」時還不能宣告值沒變 —— 判準必須兩者同時成立：
            (1) 區塊零增刪改；(2) header 不含任何影響計算的欄位。
            只看 (1) 會在「乘數被改動」時宣告安全，那正是唯一「值全變了但區塊看不出來」的情境。
          */}
          {noSectionChanges && (
            headerValueFields.length === 0 ? (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800" data-testid="diff-values-unchanged">
                <Trans i18nKey="dictionary.diff.valuesUnchanged" components={{ b: <b /> }} />
              </div>
            ) : (
              <div className="rounded-lg border border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900" data-testid="diff-multiplier-warning">
                <p className="font-medium">{t('dictionary.diff.headerWarnTitle')}</p>
                <p>
                  <Trans
                    i18nKey="dictionary.diff.headerWarnBody"
                    values={{ fields: headerValueFields.map(f => fieldLabel(t, f)).join(t('dictionary.listSeparator')) }}
                    components={{ b: <b /> }}
                  />
                </p>
              </div>
            )
          )}

          <div className="rounded-lg border px-3 py-2 text-sm bg-white" data-testid="diff-summary">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-emerald-800">{t('dictionary.diff.added')} <b>{summary.added}</b></span>
              <span className="text-red-800">{t('dictionary.diff.removed')} <b>{summary.removed}</b></span>
              <span className="text-amber-800">{t('dictionary.diff.changed')} <b>{summary.changed}</b></span>
            </div>
            {summary.changed_sections.length > 0 && (
              <p className="text-xs text-slate-600 mt-1">
                {t('dictionary.diff.affectedSections', {
                  sections: summary.changed_sections.map(s => sectionLabel(t, s)).join(t('dictionary.listSeparator')),
                })}
              </p>
            )}
            {summary.header_changed.length > 0 && (
              <p className="text-xs text-slate-600">
                {t('dictionary.diff.headerChanged', {
                  fields: summary.header_changed.map(f => fieldLabel(t, f)).join(t('dictionary.listSeparator')),
                })}
              </p>
            )}
          </div>

          <button
            onClick={() => setOpen(o => !o)}
            className="text-xs text-sky-700 underline"
            data-testid="diff-toggle"
          >
            {open ? t('dictionary.diff.detailCollapse') : t('dictionary.diff.detailExpand')}
          </button>

          {open && (
            <div className="space-y-2 max-h-80 overflow-y-auto" data-testid="diff-detail">
              {headerEntries.length > 0 && (
                <div className="border rounded-lg px-3 py-2">
                  <p className="text-sm font-medium mb-1">{t('dictionary.diff.headerBlock')}</p>
                  {sortFields(Object.fromEntries(headerEntries)).map(([f, d]) => (
                    <Delta key={f} field={f} before={d.before} after={d.after} />
                  ))}
                </div>
              )}
              {Object.entries(sections).map(([name, sec]) => (
                <SectionBlock key={name} name={name} sec={sec} counts={row_counts[name]} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
