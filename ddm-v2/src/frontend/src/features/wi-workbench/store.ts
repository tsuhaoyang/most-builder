import { create } from 'zustand'

export interface Row {
  id: string
  narr: string
  tmu: number
  seconds: number
  freq: number
  handCode: string
  payload: unknown
}

interface WiState {
  rows: Row[]
  addRow: (r: Row) => void
  delRow: (id: string) => void
  totalTmu: () => number
}

// Model（編輯器/列的本地狀態）；伺服器狀態走 TanStack Query
export const useWiStore = create<WiState>((set, get) => ({
  rows: [],
  addRow: (r) => set((s) => ({ rows: [...s.rows, r] })),
  delRow: (id) => set((s) => ({ rows: s.rows.filter((x) => x.id !== id) })),
  totalTmu: () => get().rows.reduce((a, r) => a + r.tmu * (r.freq || 1), 0),
}))
