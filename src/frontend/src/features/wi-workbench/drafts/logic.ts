// 編輯區的純邏輯（無 React）：分組、計數、與工時表列的對應。e2e 直接 import 測。
import type { WiDraft, WiDraftContent } from './api'
import type { Row } from '../store'

export interface DraftGroup {
  key: string
  /** 作業名稱（同組第一列的 wi_group）；沒有時為 null，畫面顯示「未命名作業」 */
  name: string | null
  drafts: WiDraft[]
  pending: number
  confirmed: number
  committed: number
}

/** 依 group_key 分組；組的順序＝組內最早一列的 sort_order，組內依 order_in_group。 */
export function groupDrafts(drafts: WiDraft[]): DraftGroup[] {
  const byKey = new Map<string, WiDraft[]>()
  for (const d of [...drafts].sort((a, b) => a.sort_order - b.sort_order)) {
    const list = byKey.get(d.group_key)
    if (list) list.push(d)
    else byKey.set(d.group_key, [d])
  }
  return [...byKey.entries()].map(([key, list]) => {
    const sorted = list.sort((a, b) => a.order_in_group - b.order_in_group || a.sort_order - b.sort_order)
    const name = sorted.map(d => contentOf(d).wi_group).find(g => !!g) ?? null
    return {
      key,
      name,
      drafts: sorted,
      pending: sorted.filter(d => d.status === 'pending').length,
      confirmed: sorted.filter(d => d.status === 'confirmed').length,
      committed: sorted.filter(d => d.status === 'committed').length,
    }
  })
}

export function contentOf(d: WiDraft): WiDraftContent {
  return d.content as unknown as WiDraftContent
}

export interface DraftCounts { pending: number; confirmed: number; committed: number }

export function countDrafts(drafts: WiDraft[]): DraftCounts {
  return {
    pending: drafts.filter(d => d.status === 'pending').length,
    confirmed: drafts.filter(d => d.status === 'confirmed').length,
    committed: drafts.filter(d => d.status === 'committed').length,
  }
}

/** 解析時判定不完整（要人補齊才能確認）。後端以 cycle 是否被改過為準；這裡只用來顯示提示。 */
export function parsedIncomplete(d: WiDraft): boolean {
  const snap = d.parse_snapshot as { complete?: boolean } | null | undefined
  return !!snap && snap.complete === false
}

export function parseIssues(d: WiDraft): string[] {
  const snap = d.parse_snapshot as { issues?: unknown } | null | undefined
  return Array.isArray(snap?.issues) ? (snap!.issues as unknown[]).filter((x): x is string => typeof x === 'string') : []
}

export function wiGroupTruncated(d: WiDraft): boolean {
  const snap = d.parse_snapshot as { wi_group_truncated?: boolean } | null | undefined
  return !!snap?.wi_group_truncated
}

/** 草稿內容 → 顯示用的列（只為了沿用 useRowNarr 的預覽句；不進 store）。 */
export function draftAsRow(d: WiDraft): Row {
  const c = contentOf(d)
  const cycle = (c.cycle ?? {}) as { seq?: string }
  return {
    id: d.id,
    seq: cycle.seq === 'CM' ? 'CM' : 'GM',
    handCode: c.hand ?? 'RH',
    freq: c.frequency ?? 1,
    simoGroup: '',
    nv: { obj: c.object_vocab_id ?? '', from: c.from_vocab_id ?? '', to: c.to_vocab_id ?? '' },
    toolVocab: c.tool_vocab_id ?? null,
    subActivity: c.sub_activity ?? null,
    keyParts: c.key_parts ?? null,
    narr: c.narrative ?? '',
    narrEn: null,
    wiGroup: c.wi_group ?? null,
    tmu: 0,
    seconds: 0,
    payload: c.cycle,
  }
}

/**
 * 這個 cycle 有沒有編輯器放不下的內容（載入編輯器再存回會被簡化）。編輯器只支援一個 M 分量、兩個 P 附加。
 */
export function editorWouldSimplify(cycle: unknown): boolean {
  const c = (cycle ?? {}) as { m3?: { m_components?: unknown[] }; p5?: { p_addon_codes?: unknown[] } }
  return (c.m3?.m_components?.length ?? 0) > 1 || (c.p5?.p_addon_codes?.length ?? 0) > 2
}

/** 比較兩個 cycle 是否相同（忽略 rule_set_code：寫入時一律換成工時表的版本）。 */
export function sameCycle(a: unknown, b: unknown): boolean {
  const strip = (x: unknown) => {
    const { rule_set_code: _ignored, ...rest } = (x ?? {}) as Record<string, unknown>
    return JSON.stringify(rest, Object.keys(rest).sort())
  }
  return strip(a) === strip(b)
}

/**
 * 編輯器目前的內容 → 草稿內容（手動新增與「更新草稿」共用）。
 *
 * 編輯草稿時（`base`＋`baseRoundTrip`）：使用者沒動格位（編輯器產出＝原 cycle 載入編輯器後的產出），就**原封保留**
 * 草稿的 cycle——否則「只是打開再存」就會把 AI 的內容改成編輯器的形狀，也會讓後端的「沒人補過」判斷失效（W3）。
 * 格位改了才用編輯器的產出，敘述清空（後端寫入時依 cycle 重建）。
 */
export function editorContent(input: {
  cycle: unknown
  handCode: string
  freq: number
  nv: { obj: string; from: string; to: string }
  wiGroup: string
  base?: WiDraftContent | null
  baseRoundTrip?: unknown
}): WiDraftContent {
  const base = input.base ?? null
  const unchanged = base != null && input.baseRoundTrip !== undefined && sameCycle(input.cycle, input.baseRoundTrip)
  const cycle = unchanged ? base!.cycle : input.cycle
  const vocabSame = base != null
    && (base.object_vocab_id ?? '') === (input.nv.obj || '')
    && (base.from_vocab_id ?? '') === (input.nv.from || '')
    && (base.to_vocab_id ?? '') === (input.nv.to || '')
  return {
    ...(base ?? {}),
    hand: (['RH', 'LH', 'BH'].includes(input.handCode) ? input.handCode : 'RH') as WiDraftContent['hand'],
    frequency: input.freq || 1,
    object_vocab_id: input.nv.obj || null,
    from_vocab_id: input.nv.from || null,
    to_vocab_id: input.nv.to || null,
    wi_group: input.wiGroup.trim() || null,
    narrative: unchanged && vocabSame ? (base?.narrative ?? null) : null,
    cycle: cycle as WiDraftContent['cycle'],
  }
}

/** 寫入工時表後，哪些列的距離狀態從「已確認」被退回（W7b：改了距離輸入）。 */
export function resetDistanceRows(
  before: Array<{ id: string; distanceStatus?: string | null }>,
  after: Array<{ wi_row_id: string; distance_status?: string | null }>,
): string[] {
  const prev = new Map(before.map(r => [r.id, r.distanceStatus ?? null]))
  return after
    .filter(r => prev.get(r.wi_row_id) === 'confirmed' && (r.distance_status ?? null) === null)
    .map(r => r.wi_row_id)
}
