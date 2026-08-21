import { create } from 'zustand'

export interface Row {
  id: string
  seq: 'GM' | 'CM'
  handCode: string
  freq: number
  simoGroup: string
  /** 情境欄。`component`／`where` 只有本地新加的列帶得到（後端 WiRow 沒有這兩欄）。 */
  nv: { obj: string; from: string; to: string; component?: string; where?: string }
  /**
   * 後端敘述（`most_cycles.narrative_zh`）。**本地新加的列一律留空**——把 `i18n.t`
   * 的產物凍進 state 會讓那些列永遠停在加入當下的語言。顯示請走 `useRowNarr()`。
   */
  narr: string
  tmu: number
  seconds: number
  payload: unknown   // CycleIn
}

interface WiState {
  rows: Row[]
  /** R1：server revision；save 時作 base_revision */
  revisionNo: number | null
  contentHash: string | null
  addRow: (r: Row) => void
  delRow: (id: string) => void
  setRows: (rows: Row[]) => void
  setRevisionMeta: (meta: { revisionNo: number | null; contentHash?: string | null }) => void
  totalTmu: () => number   // ADR-020：SIMO 標記列（simoGroup 非空）貢獻 0，其餘 Σ(tmu × freq)
}

export const useWiStore = create<WiState>((set, get) => ({
  rows: [],
  revisionNo: null,
  contentHash: null,
  addRow: (r) => set((s) => ({ rows: [...s.rows, r] })),
  delRow: (id) => set((s) => ({ rows: s.rows.filter((x) => x.id !== id) })),
  setRows: (rows) => set({ rows }),
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
