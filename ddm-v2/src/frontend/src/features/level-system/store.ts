import { create } from 'zustand'
import { useWiStore } from '../wi-workbench/store'
import { blankCell, rowsIn, rowsInWcub, subGroupsOf, cs, wcub, canAssignWcub, type LevelCell, type GroupMeta } from './logic'

interface LevelState {
  levelMap: Record<string, LevelCell>
  groupMeta: Record<string, GroupMeta>
  gseq: number
  // WP12（ADR-035）：worker_cub 是與 groupMeta/countersignature 完全獨立的維度。
  // 絕不把 wcub 寫進 groupMeta/countersignature（否則會被 R1–R9/derive 當 sub/cub 送進 level 引擎）。
  workerCubMeta: Record<string, { seq: number }>
  wseq: number
  wcubError: string  // assignWcub 被 freq>1／tool-held 擋下時的錯誤指示（row id 或 ''）
  nbMode: boolean
  nbPick: string[]
  sync: () => void
  patchCell: (id: string, patch: Partial<LevelCell>) => void
  moveTo: (rowId: string, label: string) => void
  createGroup: (type: 'sub' | 'cub', parent: string) => void
  dissolveGroup: (label: string) => void
  // WP12 LB projection tag setters（client propagation UX only；後端才是權威）
  toggleOffline: (rowId: string) => void
  setSegment: (id: string, seg: string) => void
  setStationPin: (id: string, n: number | '') => void
  toggleGeneral: (id: string) => void
  setGeneralRole: (id: string, role: string) => void
  toggleMergeLock: (id: string) => void
  setActionType: (id: string, s: string) => void
  createWcub: () => void
  assignWcub: (rowId: string, label: string) => void
  removeWcub: (label: string) => void
  clearWcubError: () => void
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
  workerCubMeta: {},
  wseq: 0,
  wcubError: '',
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

  // ── WP12（ADR-035）LB projection tags：client 端傳播 UX；後端才是投影權威 ──────
  // offline 切換：連動同 cub（countersignature）與同 wcub（workerCub）成員一起翻轉，
  // 讓「同站/同人」的離線狀態一致（後端仍會重新驗證 E_OFFLINE_INCONSISTENT）。
  toggleOffline: (rowId) => set(s => {
    const lm = { ...s.levelMap }
    const cur = lm[rowId] || blankCell(0)
    const next = !cur.offline
    const cLabel = cs(lm, rowId)
    const wLabel = wcub(lm, rowId)
    rows().forEach(r => {
      const same = r.id === rowId
        || (cLabel && cs(lm, r.id) === cLabel)
        || (wLabel && wcub(lm, r.id) === wLabel)
      if (same) lm[r.id] = { ...(lm[r.id] || blankCell(0)), offline: next }
    })
    return { levelMap: lm }
  }),

  setSegment: (id, seg) => set(s => ({ levelMap: { ...s.levelMap, [id]: { ...(s.levelMap[id] || blankCell(0)), segment: seg } } })),
  setStationPin: (id, n) => set(s => ({ levelMap: { ...s.levelMap, [id]: { ...(s.levelMap[id] || blankCell(0)), stationPin: n } } })),

  toggleGeneral: (id) => set(s => {
    const cur = s.levelMap[id] || blankCell(0)
    const isGeneral = !cur.isGeneral
    // 取消 general 時清掉角色，避免殘留（後端 E_GENERAL_ROLE_* 用得到一致性）
    return { levelMap: { ...s.levelMap, [id]: { ...cur, isGeneral, generalRole: isGeneral ? cur.generalRole : '' } } }
  }),
  setGeneralRole: (id, role) => set(s => ({ levelMap: { ...s.levelMap, [id]: { ...(s.levelMap[id] || blankCell(0)), generalRole: role } } })),
  toggleMergeLock: (id) => set(s => {
    const cur = s.levelMap[id] || blankCell(0)
    return { levelMap: { ...s.levelMap, [id]: { ...cur, mergeLock: !cur.mergeLock } } }
  }),
  setActionType: (id, str) => set(s => ({ levelMap: { ...s.levelMap, [id]: { ...(s.levelMap[id] || blankCell(0)), actionType: str } } })),

  // wcub（同人）群組：獨立於 groupMeta，永不進 level 引擎。
  createWcub: () => set(s => {
    let n = 1; while (s.workerCubMeta['wcub' + n]) n++
    return { workerCubMeta: { ...s.workerCubMeta, ['wcub' + n]: { seq: s.wseq + 1 } }, wseq: s.wseq + 1 }
  }),

  // 指派 wcub：freq>1 或 tool-held 列必須 BLOCK（不指派）並亮錯誤指示。
  assignWcub: (rowId, label) => set(s => {
    const row = rows().find(r => r.id === rowId)
    if (row && !canAssignWcub(row)) return { wcubError: rowId }
    return { levelMap: { ...s.levelMap, [rowId]: { ...(s.levelMap[rowId] || blankCell(0)), workerCub: label } }, wcubError: '' }
  }),
  removeWcub: (label) => set(s => {
    const lm = { ...s.levelMap }; const wm = { ...s.workerCubMeta }
    rows().forEach(r => { if (wcub(lm, r.id) === label) lm[r.id] = { ...(lm[r.id] || blankCell(0)), workerCub: '' } })
    delete wm[label]
    return { levelMap: lm, workerCubMeta: wm }
  }),
  clearWcubError: () => set({ wcubError: '' }),

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

  // 由載入的 worksheet 還原 Level（取代本地狀態）。wcub 屬純 client UX 維度，載入時重置
  // （後端 lb-report 才是投影權威；hydrate 不還原 wcub 分組）。
  hydrate: (levelMap, groupMeta, gseq) => set({ levelMap, groupMeta, gseq, workerCubMeta: {}, wseq: 0, wcubError: '', nbMode: false, nbPick: [] }),
}))
