// NL Draft（F-05）型別與 CycleState patch 轉換
// nlDraftPatch 搬自 wi-workbench/WiWorkbench.tsx（Phase 3 收斂時由該處改用本模組）
// 型別收斂到 wi-workbench/aiTypes.ts（D3 過渡契約：OpenAPI 對 nl-draft 200 仍是任意
// 物件，gen:api 補 schema 前以 aiTypes 為前端契約）；含 ai.drafts 權威草稿欄位，
// 供 §18.3「不得自動丟棄額外 action」的多 action UI 使用。
import type { CycleState } from '../wi-workbench/cycle'
import type { AiCycleDraft, NlDraftLegacySlot, NlDraftResponse } from '../wi-workbench/aiTypes'

export type NlDraftSlot = NlDraftLegacySlot
export type NlDraftRes = NlDraftResponse

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

/**
 * 相容欄位（頂層 slots/suggested_seq）是否與權威草稿一致。
 *
 * 後端契約（wi_ai_service）：相容欄位**永遠來自 rule_based**，而 ai.drafts 在
 * DDM_WI_AI_ENABLED=1 時可能來自 LLM——兩者可分歧（如 LLM 判 CM、rule 猜 GM）。
 * 不一致時自動套用相容欄位＝把編輯器覆蓋成 rule 的猜測、卡片卻顯示 LLM 結果。
 * 只比對 nlDraftPatch 實際會套用的鍵（seq/g/b1/b4/p_base）；draft 無 cycle
 * （未完整編譯）視為不一致——沒有權威內容可對照，不得自動套用 rule 猜測。
 */
export function compatMatchesDraft(res: NlDraftRes, draft: AiCycleDraft): boolean {
  const cycle = draft.cycle as {
    seq?: unknown
    g2?: { g_code?: unknown }
    b1?: { b_code?: unknown }
    b4?: { b_code?: unknown }
    p5?: { p_base_code?: unknown }
  } | null
  if (!cycle) return false
  if ((res.suggested_seq === 'GM' || res.suggested_seq === 'CM') && res.suggested_seq !== cycle.seq) return false
  for (const slot of res.slots ?? []) {
    if (!slot.chosen) continue
    const code = slot.chosen.option_code
    switch (slot.field) {
      case 'g_code': if ((cycle.g2?.g_code ?? null) !== code) return false; break
      case 'b_code': if ((cycle.b1?.b_code ?? null) !== code) return false; break
      case 'b_code2': if ((cycle.b4?.b_code ?? null) !== code) return false; break
      case 'p_base_code': if ((cycle.p5?.p_base_code ?? null) !== code) return false; break
    }
  }
  return true
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
