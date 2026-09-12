// ADR-035 D10 F5：通知（Notices）純邏輯。把 LbReport 的 errors/warnings/hints + R1–R9 levelIssues
// 收斂成使用者語言的有序清單 [ask, err, warn, info]。純函式（相同輸入相同輸出），不碰 store／後端。
// 顯示字串一律走 t('levelSystem.*')；本檔只組資料，Notices.tsx 負責 render。
import type { LbReport, LbReportDiag, LbHint } from './api'
import type { LevelIssue } from './api'

/** i18next t 的最小型別（避免直接依賴 react-i18next 的完整 TFunction 泛型）。 */
export type TFn = (key: string, opts?: Record<string, unknown>) => string

/** 隱藏警告碼（ADR-035 D10 §7.1）：這些 W_* 是內部投影細節，不打擾使用者。 */
export const HIDDEN_W = [
  'W_AUTO_GROUP_FOR_LOT',
  'W_ACTION_TYPE_FALLBACK',
  'W_NB_UNSUPPORTED',
  'W_SIMO_COLLAPSED',
  'W_TOOL_NAME_EN_MISSING',
] as const

/** 工具 id → 給人看的名稱（底線換空白）。 */
export const humanTool = (id: unknown): string => String(id ?? '').replace(/_/g, ' ')

/**
 * 把一筆 E/W 診斷轉成使用者語言句子。
 * - 走 t('levelSystem.plain.'+d.code, {step, tool, freq, message})。
 * - key 不存在／回空字串 → fall back 到 d.message。
 * - d.wi_row_id 為 null 時 {{step}} 傳 ''，並把結果開頭多餘的「：」或「: 」去掉。
 */
export function plainDiag(
  t: TFn,
  d: LbReportDiag,
  stepOf: (wiRowId: string) => string,
): string {
  const params = (d.params ?? {}) as Record<string, unknown>
  const step = d.wi_row_id ? stepOf(d.wi_row_id) : ''
  const tool = humanTool(params.tool_id)
  const freq = params.freq ?? ''
  const key = 'levelSystem.plain.' + d.code
  const out = t(key, { step, tool, freq, message: d.message })
  // key 缺失時 i18next 會回 key 字串本身；空字串代表刻意隱藏 → fall back message。
  if (!out || out === key) return d.message
  if (!d.wi_row_id) return out.replace(/^：|^: /, '')
  return out
}

export type NoticeType = 'ask' | 'err' | 'warn' | 'info'

export interface Notice {
  type: NoticeType
  key: string
  text: string
  kind?: string          // hint kind（ask/info）
  wiRowIds?: string[]     // 涉及的 wi_row_id（ask/err 用來定位/寫回）
  code?: string           // diag code（err/warn）
  params?: Record<string, unknown>
}

/** 有 yes 動作的提問 hint kinds。H_MACHINE_TIME 另有 no。 */
const ASK_KINDS = ['H_TOOL_EPISODE_SAME_STATION', 'H_LOT_RUN_SEGMENT', 'H_MACHINE_TIME']

export interface BuildNoticesOpts {
  t: TFn
  stepOf: (wiRowId: string) => string   // wi_row_id → 「第 n 步『…』」標籤
}

/**
 * 產生有序通知清單：ask → err → warn → info。
 * - ask：report.hints 中 kind ∈ ASK_KINDS（H_MACHINE_TIME 也在此，另帶 no 動作）。
 * - err：report.errors（plainDiag）＋ levelIssues（R1–R9，原始 message）；plain 為空字串的 code 跳過。
 * - warn：report.warnings（plainDiag），排除 HIDDEN_W。
 * - info：report.hints 中 H_TOOL_DECOMPOSED。
 */
export function buildNotices(
  report: LbReport | null,
  levelIssues: LevelIssue[],
  opts: BuildNoticesOpts,
): Notice[] {
  const { t, stepOf } = opts
  const hints: LbHint[] = report?.hints ?? []

  const ask: Notice[] = []
  const info: Notice[] = []
  for (const h of hints) {
    const params = h.params ?? {}
    const steps = (h.wi_row_ids ?? []).map(stepOf).join(t('levelSystem.listSeparator'))
    const tool = humanTool(params.tool_id)
    const freq = params.freq ?? ''
    const step = h.wi_row_ids?.[0] ? stepOf(h.wi_row_ids[0]) : ''
    const seconds = params.seconds ?? params.x_seconds ?? ''
    if (ASK_KINDS.includes(h.kind)) {
      ask.push({
        type: 'ask',
        key: h.key,
        kind: h.kind,
        wiRowIds: h.wi_row_ids ?? [],
        params,
        text: t(`levelSystem.hints.${h.kind}.text`, { steps, tool, freq, step, seconds }),
      })
    } else if (h.kind === 'H_TOOL_DECOMPOSED') {
      info.push({
        type: 'info',
        key: h.key,
        kind: h.kind,
        wiRowIds: h.wi_row_ids ?? [],
        params,
        text: t(`levelSystem.hints.${h.kind}.text`, { steps, tool, freq, step, seconds }),
      })
    }
  }

  const err: Notice[] = []
  for (const d of report?.errors ?? []) {
    const text = plainDiag(t, d, stepOf)
    if (!text) continue
    err.push({
      type: 'err',
      key: `${d.code}:${d.wi_row_id ?? ''}`,
      code: d.code,
      wiRowIds: d.wi_row_id ? [d.wi_row_id] : [],
      params: (d.params ?? undefined) as Record<string, unknown> | undefined,
      text,
    })
  }
  for (const li of levelIssues) {
    if (!li.message) continue
    err.push({
      type: 'err',
      key: `${li.code}:${li.row_index}`,
      code: li.code,
      wiRowIds: [],
      text: li.message,
    })
  }

  const warn: Notice[] = []
  for (const d of report?.warnings ?? []) {
    if ((HIDDEN_W as readonly string[]).includes(d.code)) continue
    const text = plainDiag(t, d, stepOf)
    if (!text) continue
    warn.push({
      type: 'warn',
      key: `${d.code}:${d.wi_row_id ?? ''}`,
      code: d.code,
      wiRowIds: d.wi_row_id ? [d.wi_row_id] : [],
      params: (d.params ?? undefined) as Record<string, unknown> | undefined,
      text,
    })
  }

  return [...ask, ...err, ...warn, ...info]
}
