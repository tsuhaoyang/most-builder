/**
 * F2（ADR-035 D10 §8.3）純邏輯測試（不用 page／request；不需伺服器）。
 * 由 fixtures/server_node_worksheet.json 的 rows[].level + lb_tags 轉成 levelMap／groupMeta（sub 標籤讀 fixture，
 * 不寫死），作業名用 prototypes/level-jobs/jobs.js::example() 的名稱在測試內注入（不改 fixture）。
 * 直接 import src/ 的純函式（jobsFromStore／proposeBaseline／normalizeLayers／derive）。
 */
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

import { jobsFromStore, proposeBaseline } from '../src/features/level-system/jobs'
import { normalizeLayers } from '../src/features/level-system/layers'
import { derive, type LevelCell, type GroupMeta } from '../src/features/level-system/logic'
import type { Row } from '../src/features/wi-workbench/store'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const FX = path.resolve(HERE, '..', '..', '..', 'docs', 'lb-integration', 'fixtures', 'server_node_worksheet.json')

// 黃金 24 列 → letter → 作業名（prototypes/level-jobs/jobs.js::example()）；不進 fixture，只在測試注入 wiGroup
const JOB_NAME_BY_LETTER: Record<string, string> = {
  A: '把機箱放上輸送帶', B: '預備 8 顆螺絲（離線）', C: '放主板進機箱', D: '掃主板序號',
  E: '裝 CPU 與 DIMM', F: '裝 CPU 與 DIMM', G: '裝 CPU 與 DIMM', H: '裝 CPU 與 DIMM',
  I: '鎖主板 8 顆螺絲', J1: '裝 HDD', J2: '裝 HDD', J3: '裝 HDD', K: '裝 HDD',
  L1: '背板壓合', L2: '背板壓合', L3: '背板壓合', M: '背板壓合',
  N1: 'I/O 擋板熱熔', N2: 'I/O 擋板熱熔', N3: 'I/O 擋板熱熔',
  O: '外觀目檢', P1: 'ICT 測試', P2: 'ICT 測試', P3: 'ICT 測試',
}

interface Built { rows: Row[]; lm: Record<string, LevelCell>; gm: Record<string, GroupMeta>; byLetter: Record<string, string> }

function buildGolden(): Built {
  const fx = JSON.parse(readFileSync(FX, 'utf-8'))
  const rows: Row[] = []
  const lm: Record<string, LevelCell> = {}
  const gm: Record<string, GroupMeta> = {}
  const byLetter: Record<string, string> = {}
  fx.rows.forEach((r: any, index: number) => {
    const id = r.wi_row_id
    const lv = r.level || {}
    const tags = r.lb_tags || {}
    byLetter[r.letter] = id
    rows.push({
      id, seq: r.cycle?.seq_kind === 'CM' ? 'CM' : 'GM', handCode: r.hand || 'RH',
      freq: r.frequency ?? 1, simoGroup: r.simo_group_id || '',
      wiGroup: JOB_NAME_BY_LETTER[r.letter] ?? null,
      nv: { obj: r.object_vocab || '', from: '', to: '' },
      narr: r.cycle?.narrative_en || '', narrEn: r.cycle?.narrative_en || null,
      tmu: r.cycle?.total_tmu ?? 0, seconds: (r.cycle?.total_tmu ?? 0) * 0.036, payload: {},
    } as Row)
    lm[id] = {
      coefficient: lv.coefficient ?? 1, number: lv.number ?? '', number_count: lv.number_count ?? '',
      level: lv.level ?? String(index + 1), countersignature: lv.countersignature ?? '',
      machine_count: 1, manpower: 1,
      workerCub: tags.worker_cub ?? '', offline: tags.offline ?? false, segment: tags.segment ?? '',
      stationPin: tags.station_pin ?? '', isGeneral: tags.is_general ?? false,
      generalRole: tags.general_role ?? '', mergeLock: tags.merge_lock ?? false, actionType: tags.action_type ?? '',
      machineUnattended: tags.machine_unattended ?? null,
    }
    const csv = (lv.countersignature ?? '').trim()
    if (csv && !gm[csv]) {
      gm[csv] = { type: csv.startsWith('cub') ? 'cub' : 'sub', parent: lv.parent_countersignature ?? '', seq: index }
    }
  })
  // I-1：同 chain level 統一（首成員）——與 hydrate 一致
  const topOf = (id: string): string => {
    const c = (lm[id].countersignature || '').trim()
    if (!c) return ''
    const p = (gm[c]?.parent || '').trim()
    return p || c
  }
  const head: Record<string, string> = {}
  rows.forEach(r => { const t = topOf(r.id); if (t && !(t in head)) head[t] = lm[r.id].level })
  rows.forEach(r => { const t = topOf(r.id); if (t) lm[r.id].level = head[t] })
  return { rows, lm, gm, byLetter }
}

// ── (1) 12 作業（附錄 A.5）──
test('golden -> 11 jobs matching A.5', () => {
  const { rows, lm, gm } = buildGolden()
  const model = jobsFromStore(rows, lm, gm)
  // 附錄 A.5：24 列黃金 fixture 對應 **11** 個 top-level 作業（Q1–Q3 不在黃金內、僅原型 example() 有第 12 個）。
  // 實作書 §5/§8.3 的「12」指原型 example()；對 24 列 fixture 為 11（A.5 表本身列 11 列）。
  expect(model.jobs.length).toBe(11)
  const byName = (n: string) => model.jobs.filter(j => (j.name ?? '') === n)
  // 名稱 → 步驟數／同站／同人（對照 A.5）
  const expectJob = (name: string, steps: number, ss: boolean, sp: boolean, offline: boolean, pin: number | null) => {
    const js = byName(name)
    expect(js.length, `作業「${name}」應恰 1 個`).toBe(1)
    const j = js[0]
    const totalSteps = j.steps.length + j.generalSteps.length
    expect(totalSteps, `${name} 步驟數`).toBe(steps)
    expect(j.sameStation, `${name} 同站`).toBe(ss)
    expect(j.samePerson, `${name} 同人`).toBe(sp)
    expect(j.offline, `${name} 離線`).toBe(offline)
    expect(j.pin, `${name} pin`).toBe(pin)
  }
  expectJob('把機箱放上輸送帶', 1, false, false, false, null)  // gen A
  expectJob('預備 8 顆螺絲（離線）', 1, false, false, true, null)  // B offline
  expectJob('放主板進機箱', 1, false, false, false, null)          // C
  expectJob('掃主板序號', 1, false, false, false, null)            // D
  expectJob('裝 CPU 與 DIMM', 4, false, false, false, null)        // E-H (sub2)
  expectJob('鎖主板 8 顆螺絲', 1, true, false, false, null)         // I cub40
  expectJob('裝 HDD', 4, false, false, false, null)               // J1-K sub3
  expectJob('背板壓合', 4, true, false, false, null)               // L1-M cub10
  expectJob('I/O 擋板熱熔', 3, true, true, false, null)            // N1-N3 cub11 + wcub21
  expectJob('外觀目檢', 1, false, false, false, null)              // O
  expectJob('ICT 測試', 3, false, false, false, 6)                // P1-P3 pin 6
})

// ── (2) 反投影不失真 I-4：零動作 → derive() 與 fixture 的 level 六欄＋lb_tags 逐列相等 ──
test('reverse projection lossless (I-4)', () => {
  const { rows, lm, gm } = buildGolden()
  const out = derive(rows, lm, gm, (r) => r.narr)
  const fx = JSON.parse(readFileSync(FX, 'utf-8'))
  out.forEach((e, i) => {
    const lv = fx.rows[i].level || {}
    // level 六欄
    expect(e.ascription).toBe(lv.ascription ?? (lv.countersignature && lv.order !== 1 ? null : 'main') ?? e.ascription)
    expect(e.countersignature).toBe(lv.countersignature ?? null)
    expect(e.parent_countersignature ?? null).toBe(lv.parent_countersignature ?? null)
    expect(e.number ?? null).toBe(lv.number ?? null)
    expect(e.number_count ?? null).toBe(lv.number_count ?? null)
  })
})

// ── (4) normalizeLayers ──
test('normalizeLayers renumbers to 1..k', () => {
  const mk = (row: number, rowHi: number | null = null): any => ({ id: 'x', row, rowHi, discrete: null, steps: ['x'], generalSteps: [] })
  const m = normalizeLayers([mk(1), mk(1), mk(3), mk(5)])
  expect(m.get(1)).toBe(1)
  expect(m.get(3)).toBe(2)
  expect(m.get(5)).toBe(3)
})

// ── (5) proposeBaseline ──
test('proposeBaseline groups consecutive same wiGroup; null when grouped', () => {
  const mkRow = (id: string, wg: string): Row => ({
    id, seq: 'GM', handCode: 'RH', freq: 1, simoGroup: '', wiGroup: wg,
    nv: { obj: '', from: '', to: '' }, narr: id, narrEn: null, tmu: 10, seconds: 0.36, payload: {},
  } as Row)
  const mkCell = (): LevelCell => ({
    coefficient: 1, number: '', number_count: '', level: '1', countersignature: '',
    machine_count: 1, manpower: 1, workerCub: '', offline: false, segment: '', stationPin: '',
    isGeneral: false, generalRole: '', mergeLock: false, actionType: '', machineUnattended: null,
  })
  const rows = [mkRow('a', '裝 HDD'), mkRow('b', '裝 HDD'), mkRow('c', '鎖螺絲')]
  const lm: Record<string, LevelCell> = { a: mkCell(), b: mkCell(), c: mkCell() }
  const actions = proposeBaseline(rows, lm)
  expect(actions).not.toBeNull()
  expect(actions!.length).toBe(2)                 // [a,b] 一組、c 一組
  expect(actions![0].ids).toEqual(['a', 'b'])
  expect(actions![0].row).toBe(1)
  expect(actions![1].ids).toEqual(['c'])
  expect(actions![1].row).toBe(2)
  // 已有群組 → null
  lm.a.countersignature = 'sub1'
  expect(proposeBaseline(rows, lm)).toBeNull()
})

// ── (deterministic) 相同輸入相同輸出 ──
test('jobsFromStore deterministic', () => {
  const { rows, lm, gm } = buildGolden()
  const a = JSON.stringify(jobsFromStore(rows, lm, gm))
  const b = JSON.stringify(jobsFromStore(rows, lm, gm))
  expect(a).toBe(b)
})

// ── (3) 每個 A.2 動作各一案例（走真 zustand store；I-1/I-2 不變量）──
import { useWiStore } from '../src/features/wi-workbench/store'
import { useLevelStore } from '../src/features/level-system/store'
import * as A from '../src/features/level-system/jobsActions'

function loadStores(b: Built): void {
  useWiStore.setState({ rows: b.rows, revisionNo: 1, contentHash: null })
  useLevelStore.getState().hydrate(b.lm, b.gm, b.rows.length,
    Object.fromEntries(Object.values(b.lm).filter(c => c.workerCub).map(c => [c.workerCub, { seq: 0 }])), 0)
}
function model() {
  const st = useLevelStore.getState()
  return jobsFromStore(useWiStore.getState().rows, st.levelMap, st.groupMeta)
}
function jobByName(n: string) {
  return model().jobs.find(j => (j.name ?? '') === n)!
}
function invariantsHold(): void {
  const m = model()
  // I-2：非 discrete 排為 1..k 連續整數
  const rowsSet = [...new Set(m.jobs.filter(j => !j.discrete).map(j => j.row))].sort((a, b) => a - b)
  rowsSet.forEach((r, i) => expect(r).toBe(i + 1))
}

test('A2 mergeUp then ownRow', () => {
  loadStores(buildGolden())
  const d = jobByName('掃主板序號')       // row 2
  A.mergeUp(d)
  expect(jobByName('掃主板序號').row).toBe(1)  // 併到第 1 排
  invariantsHold()
  A.ownRow(jobByName('掃主板序號'))
  invariantsHold()
})

test('A2 setSameStation on/off (sub<->cub)', () => {
  loadStores(buildGolden())
  const hdd = jobByName('裝 HDD')         // sub → cub
  expect(hdd.sameStation).toBe(false)
  A.setSameStation(hdd, true)
  expect(jobByName('裝 HDD').sameStation).toBe(true)
  invariantsHold()
  A.setSameStation(jobByName('裝 HDD'), false)
  expect(jobByName('裝 HDD').sameStation).toBe(false)
  invariantsHold()
})

test('A2 setSamePerson blocked when job contains a tool/lot row', () => {
  loadStores(buildGolden())
  // 「裝 CPU 與 DIMM」(E-H) 含 F（scanner Pattern B）→ canAssignWcub 為 false → 整組被擋，不套用
  const cpu = jobByName('裝 CPU 與 DIMM')
  A.setSamePerson(cpu, true)
  expect(jobByName('裝 CPU 與 DIMM').samePerson).toBe(false)  // 被擋（含工具列）
  invariantsHold()
})

test('A2 setOffline / setPin', () => {
  loadStores(buildGolden())
  const c = jobByName('放主板進機箱')
  A.setOffline(c, true)
  expect(jobByName('放主板進機箱').offline).toBe(true)
  A.setPin(jobByName('放主板進機箱'), 3)
  expect(jobByName('放主板進機箱').pin).toBe(3)
  invariantsHold()
})

test('A2 rename', () => {
  loadStores(buildGolden())
  A.rename(jobByName('外觀目檢'), '最終檢查')
  expect(jobByName('最終檢查')).toBeTruthy()
  invariantsHold()
})

// ── F2b：補齊 A.2 其餘動作各一案例（I-1/I-2/I-3）──
function i3Holds(): void {
  // I-3：通用列 countersignature=='' 且 workerCub==''
  const st = useLevelStore.getState()
  for (const [id, c] of Object.entries(st.levelMap)) {
    if (c.isGeneral) {
      expect((c.countersignature || '').trim()).toBe('')
      expect((c.workerCub || '').trim()).toBe('')
    }
  }
}

test('A2 setSameStation subset -> nested cub build+dissolve', () => {
  loadStores(buildGolden())
  const cpu = jobByName('裝 CPU 與 DIMM')   // sub2；子集 G,H
  const g = model().jobs.find(j => j.id === 'sub2')!.steps.slice(2, 4)  // 後兩步
  A.setSameStation(cpu, true, g)
  // G,H 進了一個 parent=sub2 的巢狀 cub
  const st = useLevelStore.getState()
  const gcs = st.levelMap[g[0]].countersignature
  expect(gcs.startsWith('cub')).toBe(true)
  expect(st.groupMeta[gcs].parent).toBe('sub2')
  invariantsHold(); i3Holds()
  // 拆除
  A.setSameStation(jobByName('裝 CPU 與 DIMM'), false, g)
  expect(useLevelStore.getState().levelMap[g[0]].countersignature).toBe('sub2')
  invariantsHold()
})

test('A2 setSamePerson positive on assignable job', () => {
  loadStores(buildGolden())
  const hdd = jobByName('裝 HDD')   // J1,J2,J3 (freq1) + K (torque driver, tool!)
  // K 是工具列 → 整組被擋；改測子集 J1-J3（可指派）
  const sub3 = model().jobs.find(j => j.id === 'sub3')!
  const plain = sub3.steps.slice(0, 3)  // J1,J2,J3
  A.setSamePerson(jobByName('裝 HDD'), true, plain)
  const st = useLevelStore.getState()
  const w = st.levelMap[plain[0]].workerCub
  expect(w).toBeTruthy()
  expect(plain.every(id => st.levelMap[id].workerCub === w)).toBe(true)
  invariantsHold()
})

test('A2 splitSteps', () => {
  loadStores(buildGolden())
  const hdd = model().jobs.find(j => j.id === 'sub3')!
  const split = hdd.steps.slice(0, 2)
  A.splitSteps(jobByName('裝 HDD'), split, '前置')
  expect(jobByName('前置')).toBeTruthy()
  invariantsHold(); i3Holds()
})

test('A2 moveStepsTo single-target-becomes-sub', () => {
  loadStores(buildGolden())
  const src = model().jobs.find(j => j.id === 'sub3')!
  const move = src.steps.slice(0, 1)
  const target = jobByName('放主板進機箱')   // 單列未分組
  A.moveStepsTo(jobByName('裝 HDD'), target, move)
  // target 現含移入的步驟
  invariantsHold(); i3Holds()
})

test('A2 reorderStep changes order and level restamped', () => {
  loadStores(buildGolden())
  const before = useWiStore.getState().rows.map(r => r.id)
  const sub3 = model().jobs.find(j => j.id === 'sub3')!
  A.reorderStep(jobByName('裝 HDD'), sub3.steps[1], -1)  // 上移第二步
  const after = useWiStore.getState().rows.map(r => r.id)
  expect(after).not.toEqual(before)  // 列序改變
  invariantsHold()
})

test('A2 setGeneral detaches group and clears wcub', () => {
  loadStores(buildGolden())
  const sub3 = model().jobs.find(j => j.id === 'sub3')!
  const id = sub3.steps[0]
  A.setGeneral(id, 'scanner')
  const c = useLevelStore.getState().levelMap[id]
  expect(c.isGeneral).toBe(true)
  expect((c.countersignature || '').trim()).toBe('')
  expect((c.workerCub || '').trim()).toBe('')
  expect(c.generalRole).toBe('scanner')
  invariantsHold(); i3Holds()
})

test('A2 setSegment', () => {
  loadStores(buildGolden())
  const sub3 = model().jobs.find(j => j.id === 'sub3')!
  A.setSegment(sub3.steps.slice(0, 2), 'batchX')
  const st = useLevelStore.getState()
  expect(sub3.steps.slice(0, 2).every(id => st.levelMap[id].segment === 'batchX')).toBe(true)
  invariantsHold()
})

test('A2 setLate / joinLayerOf / placeBetween', () => {
  loadStores(buildGolden())
  const d = jobByName('掃主板序號')
  A.setLate(d, d.row + 1)
  expect(jobByName('掃主板序號').rowHi).not.toBeNull()
  invariantsHold()
  // joinLayerOf：把 D 併到 O 的排
  loadStores(buildGolden())
  const o = jobByName('外觀目檢')
  A.joinLayerOf(jobByName('掃主板序號'), o)
  invariantsHold()
  // placeBetween
  loadStores(buildGolden())
  A.placeBetween(jobByName('外觀目檢'), 1)
  invariantsHold()
})
