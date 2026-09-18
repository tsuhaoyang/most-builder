/**
 * 黃金複本（ADR-035 D10 §8.3）：以真實 CycleIn 建 24 列，對應 server_node_worksheet.json 結構
 * （同 seq_kind／tool／frequency／repeat 格位／x_seconds／level／lb_tags）。複本 TMU 與黃金不同
 * （DoD-1 排除 duration 欄），但 22 欄語意逐欄相等。
 * 需先以 API 建 vocab（tool 帶 name_en：scanner／electric driver／torque driver；object/component 若干）。
 * 列 id 一律隨機（wi_rows.id 是全域主鍵）；要和 fixture 對照時，由呼叫端依 seq_no 改寫 fixture 那一側。
 */
import type { APIRequestContext } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import type { components } from '../../src/shared/types/api'
import path from 'node:path'

const AUTH = { 'X-Username': 'IEC141289' }
const HERE = path.dirname(fileURLToPath(import.meta.url))
export const FIXTURES_DIR = path.resolve(HERE, '..', '..', '..', '..', 'docs', 'lb-integration', 'fixtures')

const TOOLS = [
  { key: 'scanner', name_en: 'scanner' },
  { key: 'electric_driver', name_en: 'electric driver' },
  { key: 'torque_driver', name_en: 'torque driver' },
]
const OBJECTS = ['motherboard', 'chassis', 'board']
const COMPONENTS = ['screw', 'cpu', 'dimm', 'hdd', 'io_shield', 'backplane']

export interface ReplicaVocab { tools: Record<string, string>; objects: Record<string, string>; components: Record<string, string> }

export async function ensureReplicaVocab(request: APIRequestContext): Promise<ReplicaVocab> {
  const existing = (await (await request.get('/api/v2/vocab', { headers: AUTH })).json()) as Array<{ id: string; kind: string; name_en: string | null }>
  const byNameEn = new Map(existing.filter(v => v.name_en).map(v => [v.name_en!.toLowerCase(), v.id]))

  async function ensure(kind: string, name_en: string, name_zh: string): Promise<string> {
    const hit = byNameEn.get(name_en.toLowerCase())
    if (hit) return hit
    const r = await request.post('/api/v2/vocab', { headers: AUTH, data: { kind, name_zh, name_en } })
    const id = ((await r.json()) as { id: string }).id
    byNameEn.set(name_en.toLowerCase(), id)
    return id
  }
  const tools: Record<string, string> = {}
  for (const t of TOOLS) tools[t.key] = await ensure('tool', t.name_en, t.key)
  const objects: Record<string, string> = {}
  for (const o of OBJECTS) objects[o] = await ensure('object', o, o)
  const components: Record<string, string> = {}
  for (const c of COMPONENTS) components[c] = await ensure('component', c, c)
  return { tools, objects, components }
}

const RS = 'MINIMOST_FACTORY_V2'
const gm = () => ({
  seq: 'GM', rule_set_code: RS,
  a0: { reach_cm: 20 }, g2: { g_code: 'g_tap' }, a3: { reach_cm: 20 }, p5: { p_base_code: 'p_place_none' }, a6: { reach_cm: 20 },
})
const cm = (opts: { xSeconds?: number; useRepeat?: number; iRepeatOnly?: number }) => {
  const hasMachine = (opts.xSeconds ?? 0) > 0
  // x_press 需正秒數；無機台秒數的 CM（掃描/檢查）用 x_none（零工時 X option）。
  const x4: Record<string, unknown> = hasMachine
    ? { x_code: 'x_press', x_seconds: opts.xSeconds, ...(opts.useRepeat ? { repeat_count: opts.useRepeat } : {}) }
    : { x_code: 'x_none', ...(opts.useRepeat ? { repeat_count: opts.useRepeat } : {}) }
  return {
    seq: 'CM', rule_set_code: RS,
    a0: { reach_cm: 16 }, g2: { g_code: 'g_tap' },
    m3: { m_components: [{ verb_code: 'm_screw' }], ...(opts.useRepeat ? { repeat_count: opts.useRepeat } : {}) },
    x4,
    i5: { i_code: 'i_check', ...(opts.useRepeat ? { repeat_count: opts.useRepeat } : (opts.iRepeatOnly ? { repeat_count: opts.iRepeatOnly } : {})) },
    a6: { reach_cm: 16 },
  }
}

interface Spec {
  letter: string; seq: 'GM' | 'CM'; obj?: string | null; tool?: string | null; freq?: number
  xs?: number; useRepeat?: number; iRepeatOnly?: number; sub?: string
  level?: string; cs?: string; par?: string; ord?: number
  general?: boolean; role?: string; offline?: boolean; segment?: string; wcub?: string; mu?: boolean | null
  mergeLock?: boolean; pin?: number
}

// action_type（IE 標籤，ruling B）per motion（golden 值；A=general 由 general_role 推 take）
const ACTION: Record<string, string> = {
  B: 'collect', C: 'place', D: 'scan', E: 'insert', F: 'scan', G: 'insert', H: 'latch', I: 'fasten',
  J1: 'pick', J2: 'insert', J3: 'press', K: 'fasten', L1: 'place', L2: 'press', L3: 'remove', M: 'fasten',
  N1: 'place', N2: 'press', N3: 'remove', O: 'inspect', P1: 'place', P2: 'test', P3: 'remove',
}

// part_id（key_parts）per motion（golden 值；A=general 由投影填 General）
const PART: Record<string, string> = {
  A: 'General', B: 'SCREW', C: 'MB', D: 'MB', E: 'CPU', F: 'CPU', G: 'DIMM', H: 'DIMM', I: 'SCREW',
  J1: 'HDD', J2: 'HDD', J3: 'HDD', K: 'HDD', L1: 'BACKPLANE', L2: 'BACKPLANE', L3: 'BACKPLANE', M: 'BACKPLANE',
  N1: 'IO_SHIELD', N2: 'IO_SHIELD', N3: 'IO_SHIELD', O: 'MB', P1: 'MB', P2: 'MB', P3: 'MB',
}

// station_name（sub_activity）per motion（golden 值）
const STATION: Record<string, string> = {
  A: 'General', B: 'Pre-kit', C: 'MB sub-assy', D: 'MB sub-assy', E: 'MB sub-assy', F: 'MB sub-assy',
  G: 'MB sub-assy', H: 'MB sub-assy', I: 'MB sub-assy',
  J1: 'HDD sub-assy', J2: 'HDD sub-assy', J3: 'HDD sub-assy', K: 'HDD sub-assy',
  L1: 'Backplane', L2: 'Backplane', L3: 'Backplane', M: 'Backplane',
  N1: 'IO shield', N2: 'IO shield', N3: 'IO shield',
  O: 'Final', P1: 'Final', P2: 'Final', P3: 'Final',
}

const SPECS: Spec[] = [
  { letter: 'A', seq: 'GM', obj: 'chassis', level: '1', general: true, role: 'take_unit' },
  { letter: 'B', seq: 'GM', obj: 'screw', level: '1', offline: true },
  { letter: 'C', seq: 'GM', obj: 'motherboard', level: '1' },
  { letter: 'D', seq: 'CM', obj: 'motherboard', tool: 'scanner', level: '2' },
  { letter: 'E', seq: 'GM', obj: 'cpu', level: '2', cs: 'sub2', ord: 1 },
  { letter: 'F', seq: 'CM', obj: 'cpu', tool: 'scanner', cs: 'sub2', ord: 2 },
  { letter: 'G', seq: 'GM', obj: 'dimm', freq: 8, level: '2', cs: 'cub30', par: 'sub2', ord: 1, segment: 'dimm' },
  { letter: 'H', seq: 'GM', obj: 'dimm', freq: 8, cs: 'cub30', par: 'sub2', ord: 2, segment: 'dimm' },
  { letter: 'I', seq: 'CM', obj: 'screw', tool: 'electric_driver', xs: 0.216, useRepeat: 8, level: '2', cs: 'cub40', ord: 1, segment: 'screw' },
  { letter: 'J1', seq: 'GM', obj: 'hdd', level: '2', cs: 'sub3', ord: 1, wcub: 'wcub20' },
  { letter: 'J2', seq: 'CM', obj: 'hdd', cs: 'sub3', ord: 2, wcub: 'wcub20' },
  { letter: 'J3', seq: 'CM', obj: 'hdd', cs: 'sub3', ord: 3, wcub: 'wcub20' },
  { letter: 'K', seq: 'CM', obj: 'screw', tool: 'torque_driver', xs: 0.216, cs: 'sub3', ord: 4, mergeLock: true },
  { letter: 'L1', seq: 'GM', obj: 'backplane', level: '2', cs: 'cub10', ord: 1 },
  { letter: 'L2', seq: 'CM', obj: 'backplane', xs: 3.0, cs: 'cub10', ord: 2, mu: true },
  { letter: 'L3', seq: 'GM', obj: 'backplane', cs: 'cub10', ord: 3 },
  { letter: 'M', seq: 'CM', obj: 'screw', tool: 'torque_driver', xs: 0.216, cs: 'cub10', ord: 4, mergeLock: true },
  { letter: 'N1', seq: 'GM', obj: 'io_shield', level: '2', cs: 'cub11', ord: 1, wcub: 'wcub21' },
  { letter: 'N2', seq: 'CM', obj: 'io_shield', xs: 2.0, cs: 'cub11', ord: 2, wcub: 'wcub21', mu: false },
  { letter: 'N3', seq: 'GM', obj: 'io_shield', cs: 'cub11', ord: 3, wcub: 'wcub21' },
  { letter: 'O', seq: 'CM', obj: 'board', iRepeatOnly: 12, level: '3' },
  { letter: 'P1', seq: 'GM', obj: 'board', level: '4', cs: 'sub5', ord: 1, pin: 6 },
  { letter: 'P2', seq: 'CM', obj: 'board', xs: 20.0, cs: 'sub5', ord: 2, mu: true, pin: 6 },
  { letter: 'P3', seq: 'GM', obj: 'board', cs: 'sub5', ord: 3, pin: 6 },
]

export const JOB_NAME: Record<string, string> = {
  A: '把機箱放上輸送帶', B: '預備 8 顆螺絲（離線）', C: '放主板進機箱', D: '掃主板序號',
  E: '裝 CPU 與 DIMM', F: '裝 CPU 與 DIMM', G: '裝 CPU 與 DIMM', H: '裝 CPU 與 DIMM',
  I: '鎖主板 8 顆螺絲', J1: '裝 HDD', J2: '裝 HDD', J3: '裝 HDD', K: '裝 HDD',
  L1: '背板壓合', L2: '背板壓合', L3: '背板壓合', M: '背板壓合',
  N1: 'I/O 擋板熱熔', N2: 'I/O 擋板熱熔', N3: 'I/O 擋板熱熔',
  O: '外觀目檢', P1: 'ICT 測試', P2: 'ICT 測試', P3: 'ICT 測試',
}

/** 複本 24 列依 seq_no 的字母代號（與 server_node_worksheet.json 的 `letter` 同序；呼叫端對齊檢查用）。 */
export const GOLDEN_LETTERS: readonly string[] = SPECS.map(s => s.letter)

/** 複本一列（PUT /worksheets/{id} 的 WiRowSaveIn 子集；未用到的選填欄不列）。id 一律隨機。 */
export interface GoldenRow {
  id: string; seq_no: number; hand: string
  sub_activity: string | null; key_parts: string | null
  object_vocab_id: string | null; tool_vocab_id: string | null
  frequency: number; wi_group: string | null
  cycle: Record<string, unknown>
  // 鍵名與型別跟著後端 LevelFieldsIn（api.d.ts 由 OpenAPI 產）走，後端改名時 typecheck:e2e 會紅。
  level: Pick<components['schemas']['LevelFieldsIn'],
    'ascription' | 'level' | 'countersignature' | 'parent_countersignature' | 'order'
    | 'is_general' | 'general_role' | 'offline' | 'segment' | 'worker_cub'
    | 'station_pin' | 'merge_lock' | 'machine_unattended' | 'action_type'>
}

export function buildGoldenRows(vocab: ReplicaVocab): GoldenRow[] {
  const vidOf = (name?: string | null): string | null => {
    if (!name) return null
    return vocab.objects[name] ?? vocab.components[name] ?? null
  }
  return SPECS.map((s, i) => ({
    id: crypto.randomUUID(), seq_no: i + 1, hand: 'RH',
    sub_activity: STATION[s.letter] ?? null,
    key_parts: PART[s.letter] ?? null,
    object_vocab_id: vidOf(s.obj),
    tool_vocab_id: s.tool ? vocab.tools[s.tool] : null,
    frequency: s.freq ?? 1,
    wi_group: JOB_NAME[s.letter] ?? null,
    cycle: s.seq === 'GM' ? gm() : cm({ xSeconds: s.xs, useRepeat: s.useRepeat, iRepeatOnly: s.iRepeatOnly }),
    level: {
      ascription: s.ord && s.ord !== 1 ? null : 'main',
      level: s.level ?? (s.ord && s.ord !== 1 ? null : String(i + 1)),
      countersignature: s.cs ?? null, parent_countersignature: s.par ?? null, order: s.ord ?? null,
      is_general: !!s.general, general_role: s.role ?? null,
      offline: !!s.offline, segment: s.segment ?? null, worker_cub: s.wcub ?? null,
      station_pin: s.pin ?? null, merge_lock: !!s.mergeLock,
      machine_unattended: s.mu ?? null,
      action_type: ACTION[s.letter] ?? null,
    },
  }))
}

/** 回寫驗證複本所在 worksheet 的標記（model_label）；放在 demo worksheet 同一 SKU 下，一次列表即可找回。 */
export const WRITEBACK_REPLICA_LABEL = 'e2e: LB writeback golden replica'

/**
 * 回寫驗證用的複本：在 demo worksheet 的 SKU 下找標記的 draft 重存，找不到才新建（自建重用——不每跑一次
 * 就多一份 clone；快照受保留策略上限 10 筆）。列 id 每次都是新的隨機值：wi_rows.id 是全域主鍵，
 * 測試不得佔用任何固定 id。同一份 worksheet 會被重存，不可在共用 dev DB 上同時跑兩次。
 */
export async function saveWritebackReplica(
  request: APIRequestContext,
  demoWorksheetId: string,
  vocab: ReplicaVocab,
): Promise<{ worksheetId: string; rows: GoldenRow[] }> {
  const ver = await request.get(`/api/v2/worksheets/${demoWorksheetId}/versions`, { headers: AUTH })
  if (ver.status() !== 200) throw new Error(`讀 demo worksheet 版本失敗：${ver.status()} ${await ver.text()}`)
  const skuId = ((await ver.json()) as { sku_id: string }).sku_id

  const listed = await request.get(`/api/v2/skus/${skuId}/worksheets`, { headers: AUTH })
  if (listed.status() !== 200) throw new Error(`列 SKU worksheet 失敗：${listed.status()} ${await listed.text()}`)
  let worksheetId = ((await listed.json()) as Array<{ worksheet_id: string; status: string; model_label: string | null }>)
    .find(w => w.model_label === WRITEBACK_REPLICA_LABEL && w.status === 'draft')?.worksheet_id
  if (!worksheetId) {
    const created = await request.post(`/api/v2/skus/${skuId}/worksheets`, {
      headers: AUTH, data: { model_label: WRITEBACK_REPLICA_LABEL },
    })
    if (created.status() !== 201) throw new Error(`建複本 worksheet 失敗：${created.status()} ${await created.text()}`)
    worksheetId = ((await created.json()) as { worksheet_id: string }).worksheet_id
  }

  const rows = buildGoldenRows(vocab)
  const saved = await request.put(`/api/v2/worksheets/${worksheetId}`, { headers: AUTH, data: { rows } })
  if (saved.status() !== 200) throw new Error(`存複本失敗：${saved.status()} ${await saved.text()}`)
  return { worksheetId, rows }
}
