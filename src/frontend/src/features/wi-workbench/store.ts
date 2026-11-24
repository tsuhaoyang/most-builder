import { create } from 'zustand'
import { useLevelStore } from '../level-system/store'

/** Level／LB 標記的快照（levelMap、groupMeta、workerCubMeta）；用來判斷 level 有沒有未存檔的修改。 */
export function levelSnapshot(): string {
  const s = useLevelStore.getState()
  return JSON.stringify([s.levelMap, s.groupMeta, s.workerCubMeta])
}

export interface Row {
  id: string
  seq: 'GM' | 'CM'
  handCode: string
  freq: number
  simoGroup: string
  /** 情境欄。`component`／`where` 只有本地新加的列帶得到（後端 WiRow 沒有這兩欄）。 */
  nv: { obj: string; from: string; to: string; component?: string; where?: string }
  /** 工具 vocab id（LB 投影工具生命週期用；`wi_rows.tool_vocab_id`）。存檔須帶回，否則工具會被丟掉。 */
  toolVocab: string | null
  /** 站別／零件（顯示與 LB 投影 passthrough；`wi_rows.sub_activity`／`key_parts`）。存檔須帶回。 */
  subActivity: string | null
  keyParts: string | null
  /**
   * 後端中文敘述（`most_cycles.narrative_zh`）。**本地新加的列一律留空**——把 `i18n.t`
   * 的產物凍進 state 會讓那些列永遠停在加入當下的語言。顯示請走 `useRowNarr()`。
   */
  narr: string
  /** 作業名稱（ADR-035 D10；`wi_rows.wi_group`）。本地新加的列由編輯器帶入。 */
  wiGroup: string | null
  /**
   * 後端英文敘述（`most_cycles.narrative_en`）。`null` 代表 API 尚未提供英文欄位值；
   * 空字串則保留後端的明確空值語意，不在前端翻譯或猜測。
   */
  narrEn: string | null
  tmu: number
  seconds: number
  payload: unknown   // CycleIn
  /** ADR-038 D6：每列距離狀態（讀回顯示用；存檔不帶，後端保留既有值，W4） */
  distanceStatus?: 'confirmed' | 'manual' | 'not_applicable' | null
}

interface WiState {
  rows: Row[]
  /** 表上有沒有尚未存檔的修改（讀回工時表時清除；任何本地修改設為 true）。寫入編輯區前要先存檔。 */
  dirty: boolean
  /** 上次讀回或存檔時的 level 快照（level／LB 標記只存在 level store，不經 rows） */
  levelBaseline: string | null
  /** R1：server revision；save 時作 base_revision */
  revisionNo: number | null
  contentHash: string | null
  addRow: (r: Row) => void
  delRow: (id: string) => void
  setRows: (rows: Row[]) => void
  /** 從後端讀回整份工時表（不算本地修改） */
  loadRows: (rows: Row[]) => void
  /** 讀回或存檔成功後：表與 level 都視為已存（記下 level 快照） */
  markClean: () => void
  /** 表或 level 有沒有尚未存檔的修改 */
  hasUnsaved: () => boolean
  updateRows: (patch: (r: Row) => Row) => void
  setRevisionMeta: (meta: { revisionNo: number | null; contentHash?: string | null }) => void
  totalTmu: () => number   // ADR-020：SIMO 標記列（simoGroup 非空）貢獻 0，其餘 Σ(tmu × freq)
}

export const useWiStore = create<WiState>((set, get) => ({
  rows: [],
  dirty: false,
  levelBaseline: null,
  revisionNo: null,
  contentHash: null,
  addRow: (r) => set((s) => ({ rows: [...s.rows, r], dirty: true })),
  delRow: (id) => set((s) => ({ rows: s.rows.filter((x) => x.id !== id), dirty: true })),
  setRows: (rows) => set({ rows, dirty: true }),
  loadRows: (rows) => set({ rows, dirty: false }),
  markClean: () => set({ dirty: false, levelBaseline: levelSnapshot() }),
  hasUnsaved: () => {
    const s = get()
    return s.dirty || (s.levelBaseline !== null && s.levelBaseline !== levelSnapshot())
  },
  updateRows: (patch) => set((s) => ({ rows: s.rows.map(patch), dirty: true })),
  setRevisionMeta: ({ revisionNo, contentHash }) =>
    set({
      revisionNo,
      contentHash: contentHash === undefined ? get().contentHash : contentHash,
    }),
  totalTmu: () => {
    let total = 0
    for (const r of get().rows) {
      if ((r.simoGroup || '').trim()) continue  // ADR-020：SIMO 標記列貢獻 0（時間由主列吸收）
      total += r.tmu * (r.freq || 1)
    }
    return total
  },
}))
