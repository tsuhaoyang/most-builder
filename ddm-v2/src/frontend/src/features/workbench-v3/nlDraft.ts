// NL Draft（F-05）型別與 CycleState patch 轉換
// 型別/nlDraftPatch 搬自 wi-workbench/WiWorkbench.tsx（Phase 3 收斂時由該處改用本模組）
import type { CycleState } from '../wi-workbench/cycle'

export interface NlDraftSlot {
  slot_index: number
  field: string
  chosen: { option_code: string; score: number; source: string } | null
  needs_review?: boolean
}

export interface NlDraftRes {
  suggested_seq?: string | null
  slots?: NlDraftSlot[]
  overall_confidence?: number
  context?: Record<string, unknown>
}

/** NL slot field → 顯示標籤（結果面板用） */
export const NL_FIELD_LABELS: Record<string, string> = {
  a_code: 'A1 距離',
  b_code: 'B1 身體',
  g_code: 'G 取得',
  a_code2: 'A2 距離',
  b_code2: 'B2 身體',
  p_base_code: 'P 放置',
  a_code3: 'A3 距離',
}

/** F-05 badge 四態：明確(exact)／推斷(longest_match/retrieval)／預設(default)／待確認(缺) */
export function sourceBadge(source: string): string {
  switch (source) {
    case 'exact': return '明確'
    case 'longest_match':
    case 'retrieval': return '推斷'
    case 'default': return '預設'
    default: return '推斷'
  }
}

/** 覆蓋模式：套用全部建議（含 suggested_seq）。A-slot 反向對映需 lexicon，維持既有限制不套用。 */
export function nlDraftPatch(res: NlDraftRes): Partial<CycleState> {
  const patch: Partial<CycleState> = {}
  if (res.suggested_seq === 'GM' || res.suggested_seq === 'CM') {
    patch.seq = res.suggested_seq
  }
  for (const slot of (res.slots ?? [])) {
    if (!slot.chosen) continue
    const code = slot.chosen.option_code
    switch (slot.field) {
      case 'g_code': patch.g = code; break
      case 'b_code': patch.b1 = code; break
      case 'b_code2': patch.b4 = code; break
      case 'p_base_code': patch.p_base = code; break
      // A-slot reverse-mapping skipped (distance→ASlot requires lexicon lookup)
    }
  }
  return patch
}

/** 只填空白模式：僅套用目前為空/預設的鍵；不切換 seq（使用者已有內容） */
export function nlDraftPatchFillEmpty(res: NlDraftRes, cur: CycleState): Partial<CycleState> {
  const patch: Partial<CycleState> = {}
  for (const slot of (res.slots ?? [])) {
    if (!slot.chosen) continue
    const code = slot.chosen.option_code
    switch (slot.field) {
      case 'g_code': if (!cur.g) patch.g = code; break
      case 'b_code': if (!cur.b1) patch.b1 = code; break
      case 'b_code2': if (!cur.b4) patch.b4 = code; break
      case 'p_base_code': if (!cur.p_base) patch.p_base = code; break
    }
  }
  return patch
}
