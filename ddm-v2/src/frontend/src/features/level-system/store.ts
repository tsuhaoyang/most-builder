import { create } from 'zustand'
import { useWiStore } from '../wi-workbench/store'
import { blankCell, rowsIn, subGroupsOf, type LevelCell, type GroupMeta } from './logic'

interface LevelState {
  levelMap: Record<string, LevelCell>
  groupMeta: Record<string, GroupMeta>
  gseq: number
  nbMode: boolean
  nbPick: string[]
  sync: () => void
  patchCell: (id: string, patch: Partial<LevelCell>) => void
  moveTo: (rowId: string, label: string) => void
  createGroup: (type: 'sub' | 'cub', parent: string) => void
  dissolveGroup: (label: string) => void
  setNbMode: (on: boolean) => void
  toggleNbPick: (id: string) => void
  confirmNb: (count: number) => void
  removeNb: (label: string) => void
  hydrate: (levelMap: Record<string, LevelCell>, groupMeta: Record<string, GroupMeta>, gseq: number) => void
}

const rows = () => useWiStore.getState().rows

export const useLevelStore = create<LevelState>((set, get) => ({
  levelMap: {},
  groupMeta: {},
  gseq: 0,
  nbMode: false,
  nbPick: [],

  sync: () => set(s => {
    const ids = new Set(rows().map(r => r.id))
    const lm = { ...s.levelMap }
    rows().forEach((r, i) => { if (!lm[r.id]) lm[r.id] = blankCell(i) })
    Object.keys(lm).forEach(k => { if (!ids.has(k)) delete lm[k] })
    return { levelMap: lm, nbPick: s.nbPick.filter(id => ids.has(id)) }
  }),

  patchCell: (id, patch) => set(s => ({ levelMap: { ...s.levelMap, [id]: { ...(s.levelMap[id] || blankCell(0)), ...patch } } })),

  moveTo: (rowId, label) => set(s => ({
    levelMap: { ...s.levelMap, [rowId]: { ...(s.levelMap[rowId] || blankCell(0)), countersignature: label } },
  })),

  createGroup: (type, parent) => set(s => {
    let n = 1; while (s.groupMeta[type + n]) n++
    return { groupMeta: { ...s.groupMeta, [type + n]: { type, parent: parent || '', seq: s.gseq + 1 } }, gseq: s.gseq + 1 }
  }),

  dissolveGroup: (label) => set(s => {
    const lm = { ...s.levelMap }; const gm = { ...s.groupMeta }
    const parent = gm[label]?.parent || ''
    rowsIn(rows(), lm, label).forEach(r => { lm[r.id] = { ...lm[r.id], countersignature: parent } })
    subGroupsOf(gm, label).forEach(g => { gm[g] = { ...gm[g], parent } })
    delete gm[label]
    return { levelMap: lm, groupMeta: gm }
  }),

  setNbMode: (on) => set({ nbMode: on, nbPick: [] }),
  toggleNbPick: (id) => set(s => ({ nbPick: s.nbPick.includes(id) ? s.nbPick.filter(x => x !== id) : [...s.nbPick, id] })),

  confirmNb: (count) => set(s => {
    if (!s.nbPick.length) return { nbMode: false, nbPick: [] }
    const used = new Set(Object.values(s.levelMap).map(c => (c.number || '').trim()).filter(Boolean))
    let n = 1; while (used.has('nb' + n)) n++
    const label = 'nb' + n
    const lm = { ...s.levelMap }
    s.nbPick.forEach(id => { lm[id] = { ...lm[id], number: label, number_count: count } })
    return { levelMap: lm, nbMode: false, nbPick: [] }
  }),

  removeNb: (label) => set(s => {
    const lm = { ...s.levelMap }
    rows().forEach(r => { if ((lm[r.id]?.number || '').trim() === label) lm[r.id] = { ...lm[r.id], number: '', number_count: '' } })
    return { levelMap: lm }
  }),

  // 由載入的 worksheet 還原 Level（取代本地狀態）
  hydrate: (levelMap, groupMeta, gseq) => set({ levelMap, groupMeta, gseq, nbMode: false, nbPick: [] }),
}))
