import { create } from 'zustand'

export interface Row {
  id: string
  seq: 'GM' | 'CM'
  handCode: string
  freq: number
  simoGroup: string
  nv: { obj: string; from: string; to: string }
  narr: string
  tmu: number
  seconds: number
  payload: unknown   // CycleIn
}

interface WiState {
  rows: Row[]
  addRow: (r: Row) => void
  delRow: (id: string) => void
  setRows: (rows: Row[]) => void
  totalTmu: () => number   // SIMO：同群取 max
}

export const useWiStore = create<WiState>((set, get) => ({
  rows: [],
  addRow: (r) => set((s) => ({ rows: [...s.rows, r] })),
  delRow: (id) => set((s) => ({ rows: s.rows.filter((x) => x.id !== id) })),
  setRows: (rows) => set({ rows }),
  totalTmu: () => {
    let total = 0; const groups: Record<string, number> = {}
    for (const r of get().rows) {
      const eff = r.tmu * (r.freq || 1); const g = (r.simoGroup || '').trim()
      if (g) groups[g] = Math.max(groups[g] || 0, eff); else total += eff
    }
    return total + Object.values(groups).reduce((a, b) => a + b, 0)
  },
}))
