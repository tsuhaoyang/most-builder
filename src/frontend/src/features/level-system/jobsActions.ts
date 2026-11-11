// 作業版動作（ADR-035 D10 附錄 A.2）→ 對 store 的一組呼叫；每個動作末尾 restampLayers()（A.3 I-1/I-2）。
// 純粹操作 store，不碰後端；後端仍是投影權威。
import { useWiStore, type Row } from '../wi-workbench/store'
import { useLevelStore } from './store'
import { rowsIn, rowsInWcub, cs, canAssignWcub, type LevelCell, type GroupMeta } from './logic'
import { jobsFromStore, proposeBaseline } from './jobs'
import { fmtLevel, normalizeLayers, parseLevel } from './layers'
import type { Job } from './jobsModel'

const L = () => useLevelStore.getState()
const W = () => useWiStore.getState()
const rows = () => W().rows

/** I-1：同一 top-level chain 的 level 字串統一（取首成員）；I-2：排重新編號 1..k。動作末尾一律呼叫。 */
export function restampLayers(): void {
  const st = L()
  const lm = { ...st.levelMap }
  const gm = st.groupMeta
  const model = jobsFromStore(rows(), lm, gm)
  const remap = normalizeLayers(model.jobs)
  for (const job of model.jobs) {
    const target = job.discrete ? job.discrete : fmtLevel(remap.get(job.row) ?? job.row, job.rowHi ? Math.max(remap.get(job.rowHi) ?? job.rowHi, remap.get(job.row) ?? job.row) : null)
    for (const id of [...job.steps, ...job.generalSteps]) {
      lm[id] = { ...(lm[id]), level: target }
    }
  }
  useLevelStore.setState({ levelMap: lm })
}

function job(jobId: string): Job | undefined {
  return jobsFromStore(rows(), L().levelMap, L().groupMeta).jobs.find(j => j.id === jobId)
}

// ── 排 ──────────────────────────────────────────────────────────────
export function setLayer(j: Job, row: number, rowHi?: number | null): void {
  const st = L()
  for (const id of [...j.steps, ...j.generalSteps]) {
    st.patchCell(id, { level: fmtLevel(row, rowHi ?? null) })
  }
  restampLayers()
}
export function mergeUp(j: Job): void {
  if (j.row <= 1) return
  setLayer(j, j.row - 1)
}
export function ownRow(j: Job): void {
  setLayer(j, j.row + 0.5)
}
export function joinLayerOf(j: Job, target: Job): void {
  if (j.id === target.id) return
  setLayer(j, target.row)
}
export function placeBetween(j: Job, afterLayer: number): void {
  setLayer(j, afterLayer + 0.5)
}
export function setLate(j: Job, rowHi: number | null): void {
  if (rowHi != null && rowHi < j.row) return
  setLayer(j, j.row, rowHi)
}

// ── 名稱 ────────────────────────────────────────────────────────────
export function rename(j: Job, name: string): void {
  const nm = name.trim()
  if (!nm) return
  const ids = new Set([...j.steps, ...j.generalSteps])
  W().updateRows((r: Row) => (ids.has(r.id) ? { ...r, wiGroup: nm } : r))
  restampLayers()
}

// ── 同一工站（cub）────────────────────────────────────────────────
export function setSameStation(j: Job, on: boolean, subset?: string[]): void {
  const st = L()
  if (subset && subset.length && j.subLabel) {
    // 子集巢狀 cub
    if (on) {
      const cub = st.createGroup('cub', j.subLabel)
      subset.forEach(id => st.moveTo(id, cub))
    } else {
      subset.forEach(id => st.moveTo(id, j.subLabel!))
      _dissolveEmptyCubs()
    }
    restampLayers()
    return
  }
  if (on) {
    const cub = st.createGroup('cub', '')
    // sub → cub：所有成員（含巢狀）搬入；再 dissolve 舊 sub
    const oldSub = j.subLabel
    j.steps.forEach(id => st.moveTo(id, cub))
    if (oldSub) st.dissolveGroup(oldSub)
  } else if (j.cubLabel) {
    if (j.steps.length > 1) {
      const sub = st.createGroup('sub', '')
      j.steps.forEach(id => st.moveTo(id, sub))
    } else {
      j.steps.forEach(id => st.moveTo(id, ''))
    }
    st.dissolveGroup(j.cubLabel)
  }
  restampLayers()
}

// ── 同一個人（wcub）──────────────────────────────────────────────
export function setSamePerson(j: Job, on: boolean, subset?: string[]): void {
  const st = L()
  const targets = subset && subset.length ? subset : j.steps
  if (on) {
    if (!targets.every(id => canAssignWcub(rows().find(r => r.id === id)!))) return  // 被擋，不做
    const w = j.wcubLabel ?? st.createWcub()
    targets.forEach(id => st.assignWcub(id, w))
  } else {
    targets.forEach(id => st.patchCell(id, { workerCub: '' }))
  }
  restampLayers()
}

// ── 離線 ────────────────────────────────────────────────────────────
export function setOffline(j: Job, on: boolean, subset?: string[]): void {
  const st = L()
  const targets = subset && subset.length ? subset : [...j.steps, ...j.generalSteps]
  targets.forEach(id => st.patchCell(id, { offline: on }))
  restampLayers()
}

// ── 固定站 ──────────────────────────────────────────────────────────
export function setPin(j: Job, n: number | null): void {
  if (n != null && n < 1) return
  const st = L()
  ;[...j.steps, ...j.generalSteps].forEach(id => st.patchCell(id, { stationPin: n ?? '' }))
  restampLayers()
}

// ── 拆／移步驟 ──────────────────────────────────────────────────────
export function splitSteps(j: Job, ids: string[], name: string): void {
  if (ids.length === 0 || ids.length >= j.steps.length) return
  const st = L()
  ids.forEach(id => st.moveTo(id, ''))
  if (ids.length > 1) {
    const sub = st.createGroup('sub', '')
    ids.forEach(id => st.moveTo(id, sub))
  }
  const nm = name.trim()
  if (nm) {
    const idset = new Set(ids)
    W().updateRows((r: Row) => (idset.has(r.id) ? { ...r, wiGroup: nm } : r))
  }
  _cleanupSource(j)
  restampLayers()
}
export function moveStepsTo(j: Job, target: Job, ids: string[]): void {
  const st = L()
  let destLabel = target.cubLabel ?? target.subLabel
  if (!destLabel && target.steps.length === 1) {
    destLabel = st.createGroup('sub', '')
    st.moveTo(target.steps[0], destLabel)
  }
  ids.forEach(id => st.moveTo(id, destLabel ?? ''))
  if (target.name) {
    const idset = new Set(ids)
    W().updateRows((r: Row) => (idset.has(r.id) ? { ...r, wiGroup: target.name } : r))
  }
  _cleanupSource(j)
  restampLayers()
}

// ── 步驟重排 ────────────────────────────────────────────────────────
export function reorderStep(j: Job, id: string, dir: -1 | 1): void {
  const rs = [...rows()]
  const i = rs.findIndex(r => r.id === id)
  const t = i + dir
  if (i < 0 || t < 0 || t >= rs.length) return
  ;[rs[i], rs[t]] = [rs[t], rs[i]]
  W().setRows(rs)
  L().sync()
  restampLayers()
}

// ── 通用動作 ────────────────────────────────────────────────────────
export function setGeneral(id: string, role: string | null): void {
  const st = L()
  if (role) {
    st.moveTo(id, '')
    st.patchCell(id, { workerCub: '' })
    if (!(st.levelMap[id]?.isGeneral)) st.toggleGeneral(id)
    st.setGeneralRole(id, role)
  } else if (st.levelMap[id]?.isGeneral) {
    st.toggleGeneral(id)
  }
  restampLayers()
}

// ── baseline（附錄 A.4）：hydrate 後套用；回傳是否套用了（供通知條）──
export function applyBaseline(): { applied: boolean; jobCount: number } {
  const st = L()
  const plan = proposeBaseline(rows(), st.levelMap)
  if (!plan) return { applied: false, jobCount: 0 }
  // 候選段成 sub
  for (const seg of plan.actions) {
    const sub = st.createGroup('sub', '')
    seg.ids.forEach(id => L().moveTo(id, sub))
  }
  if (plan.pristine) {
    // 全新：每個 Job（含單列）依出現順序各自一排
    const model = jobsFromStore(rows(), L().levelMap, L().groupMeta)
    const ordered = [...model.jobs].sort((a, b) => {
      const ia = rows().findIndex(r => r.id === (a.steps[0] ?? a.generalSteps[0]))
      const ib = rows().findIndex(r => r.id === (b.steps[0] ?? b.generalSteps[0]))
      return ia - ib
    })
    ordered.forEach((j, k) => {
      for (const id of [...j.steps, ...j.generalSteps]) L().patchCell(id, { level: String(k + 1) })
    })
  }
  restampLayers()
  const jc = jobsFromStore(rows(), L().levelMap, L().groupMeta).jobs.length
  return { applied: true, jobCount: jc }
}

// ── segment ─────────────────────────────────────────────────────────
export function setSegment(ids: string[], name: string): void {
  const st = L()
  ids.forEach(id => st.setSegment(id, name))
  restampLayers()
}

// ── 機台顧不顧（CM x_seconds≥1）三態 ────────────────────────────────
// null=未回答、false=要顧、true=不用顧。patchCell 寫入後 restampLayers（層級不變，僅為一致性）。
export function setMachineUnattended(id: string, val: boolean | null): void {
  L().patchCell(id, { machineUnattended: val })
  restampLayers()
}

// ── helpers ─────────────────────────────────────────────────────────
function _dissolveEmptyCubs(): void {
  const st = L()
  Object.entries(st.groupMeta).forEach(([label, gm]: [string, GroupMeta]) => {
    if (gm.type === 'cub' && rowsIn(rows(), st.levelMap, label).length === 0) {
      st.dissolveGroup(label)
    }
  })
}

function _cleanupSource(j: Job): void {
  const st = L()
  // 來源剩 1 個非通用步驟且為 sub → 拆單列；剩 0 → dissolve
  const label = j.cubLabel ?? j.subLabel
  if (!label) return
  const remaining = rowsIn(rows(), st.levelMap, label)
  if (remaining.length === 1 && j.subLabel) {
    st.moveTo(remaining[0].id, '')
    st.dissolveGroup(label)
  } else if (remaining.length === 0) {
    st.dissolveGroup(label)
  }
}

// unused-import 防護（cs/rowsInWcub/parseLevel/LevelCell 供未來動作；保留匯出面）
export const _internal = { cs, rowsInWcub, parseLevel }
export type { LevelCell }
