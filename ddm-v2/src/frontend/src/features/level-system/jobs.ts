// 反投影：store（levelMap／groupMeta）→ 作業模型（ADR-035 D10 附錄 A.1）。純函式、無副作用、
// 相同輸入相同輸出（job 順序、id 穩定）。不看敘述文字。
import type { Row } from '../wi-workbench/store'
import { blankCell, cs, rowsIn, rowsInWcub, wcub, type GroupMeta, type LevelCell } from './logic'
import type { Job, JobModel, StepTag } from './jobsModel'
import { parseLevel } from './layers'

type LM = Record<string, LevelCell>
type GM = Record<string, GroupMeta>

/** topOf(id)：該列所屬 top-level chain 的 key（巢狀 cub 成員屬其外層 sub；Spec §5.3）。'' = 未分組。 */
function topOf(rows: Row[], lm: LM, gm: GM, id: string): string {
  const c = cs(lm, id)
  if (!c) return ''
  const parent = (gm[c]?.parent || '').trim()
  if (parent && rowsIn(rows, lm, parent).length > 0) return parent
  return c
}

export function jobsFromStore(rows: Row[], lm: LM, gm: GM): JobModel {
  const idx = (id: string) => rows.findIndex(r => r.id === id)
  const cell = (id: string) => lm[id] || blankCell(idx(id))

  // 1–3：分 chain（非通用），通用列附掛或自成
  const chainMembers = new Map<string, string[]>()   // chainKey → rowId[]（rows 序）
  const generalOf = new Map<string, string[]>()       // chainKey → 附掛的通用 rowId[]
  const standaloneGeneral: string[] = []              // 自成作業的通用列

  for (const r of rows) {
    const m = cell(r.id)
    if (m.isGeneral) continue  // 通用列稍後處理
    const top = topOf(rows, lm, gm, r.id)
    const key = top || `row:${r.id}`
    if (!chainMembers.has(key)) chainMembers.set(key, [])
    chainMembers.get(key)!.push(r.id)
  }

  // 通用列附掛：wiGroup 非空且恰有一條 chain 的第一成員 wiGroup 相同 → 附掛；否則自成
  const firstWiGroup = new Map<string, string>()
  for (const [key, ids] of chainMembers) {
    const wg = (rows[idx(ids[0])]?.wiGroup || '').trim()
    if (wg) firstWiGroup.set(key, wg)
  }
  for (const r of rows) {
    if (!cell(r.id).isGeneral) continue
    const wg = (r.wiGroup || '').trim()
    const matches = wg ? [...firstWiGroup].filter(([, g]) => g === wg).map(([k]) => k) : []
    if (matches.length === 1) {
      const k = matches[0]
      if (!generalOf.has(k)) generalOf.set(k, [])
      generalOf.get(k)!.push(r.id)
    } else {
      standaloneGeneral.push(r.id)
    }
  }

  const jobs: Job[] = []
  const stepTags: Record<string, StepTag> = {}

  const buildJob = (key: string, steps: string[], generalSteps: string[]): Job => {
    const first = steps[0] ?? generalSteps[0]
    const fm = cell(first)
    const chainType = gm[key]?.type
    const parsed = parseLevel(fm.level?.trim() ? fm.level : String(idx(first) + 1))
    // sameStation
    const sameStation = chainType === 'cub'
    // samePerson：steps 非空且全部同一非空 wcub W，且 rowsInWcub(W) ⊆ steps
    let samePerson = false
    let wcubLabel: string | null = null
    if (steps.length) {
      const ws = steps.map(id => wcub(lm, id))
      const w0 = ws[0]
      if (w0 && ws.every(x => x === w0)) {
        const inW = rowsInWcub(rows, lm, w0).map(r => r.id)
        if (inW.every(id => steps.includes(id))) {
          samePerson = true
          wcubLabel = w0
        }
      }
    }
    const offline = steps.length > 0 && steps.every(id => !!cell(id).offline)
    const pins = steps.map(id => cell(id).stationPin).filter(v => v !== '' && v != null)
    const pin = steps.length > 0 && pins.length === steps.length && new Set(pins).size === 1 ? Number(pins[0]) : null

    return {
      id: key,
      name: rows[idx(first)]?.wiGroup ?? null,
      steps, generalSteps,
      row: Number.isNaN(parsed.lo) ? 1e6 : parsed.lo,
      rowHi: !parsed.discrete && parsed.hi > parsed.lo ? parsed.hi : null,
      discrete: parsed.discrete,
      sameStation, samePerson, offline, pin,
      cubLabel: chainType === 'cub' ? key : null,
      subLabel: chainType === 'sub' ? key : null,
      wcubLabel,
    }
  }

  for (const [key, steps] of chainMembers) {
    const generalSteps = generalOf.get(key) || []
    const job = buildJob(key, steps, generalSteps)
    jobs.push(job)
    // stepTags：只放與作業層級不同的資訊
    for (const id of steps) {
      const m = cell(id)
      const t: StepTag = {}
      const c = cs(lm, id)
      if (c !== key && gm[c]?.type === 'cub') t.cub = c
      if (!job.samePerson && m.workerCub) t.wcub = m.workerCub
      if (!job.offline && m.offline) t.offline = true
      if (job.pin == null && m.stationPin !== '' && m.stationPin != null) t.pin = Number(m.stationPin)
      if (m.segment) t.segment = m.segment
      if (m.mergeLock) t.mergeLock = true
      if (m.actionType) t.actionType = m.actionType
      if (m.coefficient !== 1) t.coefficient = m.coefficient
      if (Object.keys(t).length) stepTags[id] = t
    }
    for (const id of generalSteps) {
      const m = cell(id)
      const t: StepTag = {}
      if (m.generalRole) t.generalRole = m.generalRole
      if (m.segment) t.segment = m.segment
      if (Object.keys(t).length) stepTags[id] = t
    }
  }

  // 自成作業的通用列
  for (const gid of standaloneGeneral) {
    const m = cell(gid)
    const parsed = parseLevel(m.level?.trim() ? m.level : String(idx(gid) + 1))
    jobs.push({
      id: `gen:${gid}`, name: rows[idx(gid)]?.wiGroup ?? null, steps: [], generalSteps: [gid],
      row: parsed.lo, rowHi: null, discrete: parsed.discrete,
      sameStation: false, samePerson: false, offline: false, pin: null,
      cubLabel: null, subLabel: null, wcubLabel: null,
    })
    const t: StepTag = {}
    if (m.generalRole) t.generalRole = m.generalRole
    if (Object.keys(t).length) stepTags[gid] = t
  }

  // 5：顯示排號 1..k（不含 discrete）
  const layerVals = [...new Set(jobs.filter(j => !j.discrete).map(j => j.row))].sort((a, b) => a - b)
  const layers = layerVals.map((_v, i) => i + 1)

  // 6：Job 排序 (row, index(first))
  const firstIdxOf = (j: Job) => idx(j.steps[0] ?? j.generalSteps[0])
  jobs.sort((a, b) => (a.row - b.row) || (firstIdxOf(a) - firstIdxOf(b)))

  return { jobs, stepTags, layers }
}

/**
 * baseline（附錄 A.4）：所有列 cs=='' 且至少一列 wiGroup 非空 → 依 rows 序把「連續同名非通用」段成 sub、
 * 各作業各自一排。回傳可套用的動作清單（動作在 jobsActions 定義）；不符條件 → null。
 * 純計算：只回「該做什麼」的描述，不改 store（呼叫端執行）。
 */
export interface BaselineAction { kind: 'group'; ids: string[]; name: string; row: number }

export function proposeBaseline(rows: Row[], lm: LM): BaselineAction[] | null {
  const anyGroup = rows.some(r => cs(lm, r.id) !== '')
  if (anyGroup) return null
  const anyName = rows.some(r => (r.wiGroup || '').trim())
  if (!anyName) return null

  const actions: BaselineAction[] = []
  let rowNo = 0
  let i = 0
  const cell = (id: string) => lm[id] || blankCell(0)
  while (i < rows.length) {
    const r = rows[i]
    const wg = (r.wiGroup || '').trim()
    const isGen = cell(r.id).isGeneral
    // 連續同名非通用段
    if (wg && !isGen) {
      const seg = [r.id]
      let j = i + 1
      while (j < rows.length && (rows[j].wiGroup || '').trim() === wg && !cell(rows[j].id).isGeneral) {
        seg.push(rows[j].id)
        j++
      }
      rowNo++
      actions.push({ kind: 'group', ids: seg, name: wg, row: rowNo })
      i = j
    } else {
      rowNo++
      actions.push({ kind: 'group', ids: [r.id], name: wg, row: rowNo })
      i++
    }
  }
  return actions
}
