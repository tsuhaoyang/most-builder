import { useState } from 'react'
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

const SECTION_ZH: Record<string, string> = {
  a_bands: 'A 距離（帶）',
  b: 'B 身體動作',
  g: 'G 取得控制',
  p_bases: 'P 放置（基礎）',
  p_addons: 'P 放置（附加）',
  m_ladder: 'M 距離階梯',
  m_foot: 'M 腳步',
  m_verbs: 'M 動詞',
  m_rotation: 'M 旋轉',
  m_hand: 'M 手部角度',
  x: 'X 製程時間',
  i: 'I 對位/檢查',
}

const FIELD_ZH: Record<string, string> = {
  name_zh: '版本名稱', multiplier: 'TMU 乘數',
  base_tmu: 'TMU', delta_tmu: '增量 TMU', index_value: '指數', fixed_tmu: '固定 TMU',
  tmu: 'TMU', index: '指數', fixed_seconds: '固定秒數',
  max_value: '上界', max_cm: '上界(cm)', max_deg: '角度上界(°)', max_diameter_cm: '直徑上界(cm)',
  revolutions: '圈數', label_zh: '顯示文字', label_en: '英文標籤',
  sentence_text_zh: 'WI 句子', sort: '排序', sort_order: '排序', is_active: '啟用',
  requires_modifier: '需修飾子', modifier_key: '修飾子', needs_precision: '需精度',
  max_select: '最多可選', display_rule: '顯示規則', pricing_kind: '計價方式',
  mode: '模式', category: '類別', direction_mode: '方向模式', vision_scope: '視覺範圍',
  is_default: '預設值',
}

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

const fieldLabel = (f: string) => FIELD_ZH[f] ?? f

function val(v: unknown) {
  if (v === null || v === undefined) return <span className="text-slate-400">（無）</span>
  if (typeof v === 'boolean') return v ? '是' : '否'
  if (v === '') return <span className="text-slate-400">（空）</span>
  return String(v)
}

/** 前 → 後。數值欄用較強的視覺權重。 */
function Delta({ field, before, after }: { field: string; before: unknown; after: unknown }) {
  const strong = VALUE_FIELDS.has(field)
  return (
    <div className={`flex flex-wrap items-baseline gap-1 ${strong ? 'text-sm' : 'text-xs'}`}>
      <span className={strong ? 'font-medium text-slate-700' : 'text-slate-500'}>
        {fieldLabel(field)}
      </span>
      <span className={strong ? 'text-red-700 line-through' : 'text-slate-400 line-through'}>{val(before)}</span>
      <span className="text-slate-400">→</span>
      <span className={strong ? 'font-semibold text-emerald-700' : 'text-slate-600'}>{val(after)}</span>
      {strong && <span className="text-[10px] text-amber-700 border border-amber-300 rounded px-1">影響工時</span>}
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
  const added = sec.added ?? []
  const removed = sec.removed ?? []
  const changed = sec.changed ?? []
  const bulk = counts && counts.before !== counts.after
  return (
    <details className="border rounded-lg" open={changed.some(c => Object.keys(c.fields).some(f => VALUE_FIELDS.has(f)))}>
      <summary className="px-3 py-2 text-sm cursor-pointer select-none flex flex-wrap items-center gap-2">
        <span className="font-medium">{SECTION_ZH[name] ?? name}</span>
        {added.length > 0 && <span className="text-xs px-1.5 rounded bg-emerald-100 text-emerald-800">+{added.length}</span>}
        {removed.length > 0 && <span className="text-xs px-1.5 rounded bg-red-100 text-red-800">−{removed.length}</span>}
        {changed.length > 0 && <span className="text-xs px-1.5 rounded bg-amber-100 text-amber-800">變更 {changed.length}</span>}
        {counts && (
          <span className={`text-xs ${bulk ? 'text-amber-700 font-medium' : 'text-slate-400'}`}>
            列數 {counts.before} → {counts.after}
          </span>
        )}
      </summary>
      <div className="px-3 pb-2 space-y-2">
        {changed.length > 0 && (
          <ul className="divide-y">{changed.map(c => <ChangedRow key={c.key} item={c} />)}</ul>
        )}
        {added.length > 0 && (
          <div className="text-xs">
            <span className="text-emerald-800 font-medium">新增：</span>
            <span className="font-mono text-slate-600">{added.map(a => a.key).join('、')}</span>
          </div>
        )}
        {removed.length > 0 && (
          <div className="text-xs">
            <span className="text-red-800 font-medium">刪除：</span>
            <span className="font-mono text-slate-600">{removed.map(r => r.key).join('、')}</span>
          </div>
        )}
      </div>
    </details>
  )
}

/** 血緣揭露：base 不是本版的 clone 來源時，diff 混了既有落差與本次編輯。 */
function Lineage({ d }: { d: RuleSetDiff }) {
  if (d.base_is_source === false) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="diff-lineage-warning">
        <p className="font-medium">⚠ 血緣提醒</p>
        {/* 後端已備 lineage_note，優先顯示它 */}
        <p>{d.lineage_note ?? `比較基準是 ${d.base_code}，但本版是從 ${d.source_code} clone 出來的——下列差異不可全部視為本次改動。`}</p>
      </div>
    )
  }
  if (d.source_code === null) {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600" data-testid="diff-lineage-unknown">
        無 clone 紀錄（例如匯入或認證版本），<b>無法判斷血緣</b>——不能假定本版就是從 {d.base_code} 來的。
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
  const [open, setOpen] = useState(!compact)

  if (isLoading) {
    return <p className="text-sm text-slate-500" data-testid="diff-loading">載入差異…</p>
  }
  // 取不到差異＝未知，**不得**呈現為「無差異」
  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="diff-error">
        <p className="font-medium">無法取得版本差異</p>
        <p className="text-xs">{(error as Error).message}</p>
        <p className="text-xs">未能確認這次會變動什麼，請排除問題後再覆核。</p>
      </div>
    )
  }
  if (!data) return null

  const { summary, sections, row_counts, header } = data.diff

  // 邊界狀態一：本版就是目前 active，沒有比較對象（先判斷——此時 identical 也會是 true）
  if (data.compared_with_self) {
    return (
      <div className="rounded-lg border bg-slate-50 px-3 py-2 text-sm text-slate-600" data-testid="diff-self">
        本版就是目前啟用中的版本（{data.base_code}），<b>沒有可比較的基準</b>。
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
        比較基準：<span className="font-mono">{data.base_code}</span>
        <span className="text-slate-400">（目前啟用中）</span>
      </div>

      <Lineage d={data} />

      {/* 邊界狀態二：確實逐欄相同 */}
      {summary.identical ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800" data-testid="diff-identical">
          與 <span className="font-mono">{data.base_code}</span> <b>逐欄比對完全相同</b>，發布後線上的值不會有任何改變。
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
                <b>值未變動</b>（僅版本名稱不同）——發布後線上的工時不會改變。
              </div>
            ) : (
              <div className="rounded-lg border border-amber-400 bg-amber-50 px-3 py-2 text-sm text-amber-900" data-testid="diff-multiplier-warning">
                <p className="font-medium">⚠ 區塊逐列未變，但版本表頭改了會影響計算的欄位</p>
                <p>
                  {headerValueFields.map(fieldLabel).join('、')} 改變會
                  <b>等比影響本版所有工時</b>，不可因為「各區塊 0 筆變更」就視為沒有影響。
                </p>
              </div>
            )
          )}

          <div className="rounded-lg border px-3 py-2 text-sm bg-white" data-testid="diff-summary">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-emerald-800">新增 <b>{summary.added}</b></span>
              <span className="text-red-800">刪除 <b>{summary.removed}</b></span>
              <span className="text-amber-800">變更 <b>{summary.changed}</b></span>
            </div>
            {summary.changed_sections.length > 0 && (
              <p className="text-xs text-slate-600 mt-1">
                受影響區塊：{summary.changed_sections.map(s => SECTION_ZH[s] ?? s).join('、')}
              </p>
            )}
            {summary.header_changed.length > 0 && (
              <p className="text-xs text-slate-600">
                版本表頭：{summary.header_changed.map(fieldLabel).join('、')}
              </p>
            )}
          </div>

          <button
            onClick={() => setOpen(o => !o)}
            className="text-xs text-sky-700 underline"
            data-testid="diff-toggle"
          >
            {open ? '收合逐欄差異' : '展開逐欄差異'}
          </button>

          {open && (
            <div className="space-y-2 max-h-80 overflow-y-auto" data-testid="diff-detail">
              {headerEntries.length > 0 && (
                <div className="border rounded-lg px-3 py-2">
                  <p className="text-sm font-medium mb-1">版本表頭</p>
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
