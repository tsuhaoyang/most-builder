/**
 * ADR-036 回寫驗證（黃金複本）。兩條路徑跑同一組斷言（expectGoldenWriteback）：
 *
 * 1. 離線（import）：複本照常用隨機 id；餵入前把 writeback_sample.json 的 source_wi_row_id 依 seq_no
 *    （fixture wi_row_id → seq_no → 複本 id）改寫成複本的實際 id。
 *    為什麼改寫 payload、而不是讓複本沿用 fixture 的 id：wi_rows.id 是全域主鍵，沿用固定 id 等於測試霸佔
 *    那幾個 id，dev DB 只要已有任何列用到它們就會撞主鍵（2026-09-18 實際發生）。改寫只是測試側的資料轉換，
 *    LB 產出的站別／人／件數／offline 一概不動。
 *
 * 2. 真機（端到端，@slow）：MOST 建複本（隨機 id）→ 匯出 lb-csv → 上傳 LB 建專案 → 求解（約 1 分鐘，
 *    max_time_seconds 60）→ MOST fetch。source_wi_row_id 由 MOST 自己的匯出帶過去，自然對得上；這也是唯一能
 *    驗證「MOST 的匯出真的能被 LB 吃下並還原」的測試。結束時刪掉本測試建的 LB 專案（自建自清；清理失敗
 *    會讓測試失敗。萬一漏刪，專案的 product_name 固定為 e2e-most-writeback，可用 LB 列表篩出來清）。
 *    開關：E2E_LB_BASE_URL 沒設 → skip；設了卻缺 E2E_LB_AUTH_HEADERS 的三個 header、或只設了
 *    E2E_LB_AUTH_HEADERS → 直接失敗（不靜默略過）。E2E_LB_AUTH_HEADERS 語法同 DDM_LB_AUTH_HEADERS
 *    （`k=v,…` 或 JSON，值可為 @me），只轉送 X-User-Id／X-Plant-Code／X-Username 三個；不要放任何憑證，
 *    帶真值執行時不要開 --trace 或 html 報告（Playwright 的 call log 會記下 header）。
 *    LB 專案依 plant_code＋username 分範圍，這組 header 必須與 MOST 伺服器的 DDM_LB_AUTH_HEADERS 一致，
 *    MOST fetch 才看得到該專案；MOST 的 DDM_LB_API_BASE_URL 也必須指向同一台 LB。只指向本機或專用的 LB、
 *    用專用的測試身分——MOST↔LB 直連（無認證）只可本機／內網（ADR-036 §4）。
 *
 * 每條路徑都用 fetch/import 的回應與 GET latest 讀回的結果各驗一次。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import type { WbLatest } from '../src/features/level-system/api'
import { ensureReplicaVocab, saveWritebackReplica, FIXTURES_DIR, GOLDEN_LETTERS, type GoldenRow } from './support/goldenReplica'

const AUTH = { 'X-Username': 'IEC141289' }
const DEMO_WS = '55555555-5555-5555-5555-555555555555'

// 兩個 test 重存同一份複本 worksheet，不可平行。
test.describe.configure({ mode: 'default' })

type WritebackOut = Pick<WbLatest, 'snapshot_id' | 'summary' | 'diff'>
interface WritebackPayload { result_id: string; rows: Array<{ source_wi_row_id: string } & Record<string, unknown>> }

/** 黃金 CSV 的 task 數（general 為 take_unit、只插首站一份，回寫列數＝task 數）。 */
function expectedTaskCount(): number {
  const csv = readFileSync(path.join(FIXTURES_DIR, 'server_node_tasks.expected.csv'), 'utf-8')
  return csv.split('\n').filter(Boolean).length - 1
}

async function seeded(request: APIRequestContext): Promise<boolean> {
  return (await request.get(`/api/v2/worksheets/${DEMO_WS}`, { headers: AUTH })).status() === 200
}

/** fixture payload 的 source_wi_row_id 依 seq_no 改寫成複本 id（對不上的 id 直接拋，不靜默略過）。 */
function remapToReplica(payload: WritebackPayload, rows: GoldenRow[]): WritebackPayload {
  const fx = JSON.parse(readFileSync(path.join(FIXTURES_DIR, 'server_node_worksheet.json'), 'utf-8')) as {
    rows: Array<{ wi_row_id: string; seq_no: number; letter: string }>
  }
  // 先確認複本與 fixture 逐 seq 是同一個動作（SPECS 順序一漂移就報錯，不會把列靜默接錯）
  const letterOfSeq = new Map(fx.rows.map(r => [r.seq_no, r.letter]))
  const drift = GOLDEN_LETTERS.map((l, i) => [i + 1, l, letterOfSeq.get(i + 1)] as const).filter(([, a, b]) => a !== b)
  if (drift.length || fx.rows.length !== GOLDEN_LETTERS.length) {
    throw new Error(`複本 SPECS 與 server_node_worksheet.json 不同序：${JSON.stringify(drift)}`)
  }
  const seqOfFixtureId = new Map(fx.rows.map(r => [r.wi_row_id, r.seq_no]))
  const replicaIdOfSeq = new Map(rows.map(r => [r.seq_no, r.id]))
  return {
    ...payload,
    rows: payload.rows.map(r => {
      const seq = seqOfFixtureId.get(r.source_wi_row_id)
      const id = seq === undefined ? undefined : replicaIdOfSeq.get(seq)
      if (!id) throw new Error(`fixture source_wi_row_id ${r.source_wi_row_id} 對不到複本的 seq_no`)
      return { ...r, source_wi_row_id: id }
    }),
  }
}

/** MOST 自己對複本投影出的 quantity Q：{wi_row_id: Q}（lb-report 的 tasks；同一 motion 各列 Q 相同，取最大）。 */
async function projectedQuantities(request: APIRequestContext, worksheetId: string): Promise<Map<string, number>> {
  const res = await request.get(`/api/v2/worksheets/${worksheetId}/export/lb-report?include_tasks=true`, { headers: AUTH })
  expect(res.status(), await res.text()).toBe(200)
  const tasks = ((await res.json()) as { tasks: Array<{ source_wi_row_id: string; quantity: string | number }> }).tasks
  const out = new Map<string, number>()
  for (const t of tasks) out.set(t.source_wi_row_id, Math.max(out.get(t.source_wi_row_id) ?? 0, Number(t.quantity)))
  return out
}

// unitsSource：離線兩條路徑各自確定（cyclic／inferred_max）；真機那條交給部署中的 LB 版本決定 → null＝兩者皆可。
function expectGoldenWriteback(
  out: WritebackOut, rows: GoldenRow[], projectedQ: Map<string, number>,
  unitsSource: 'cyclic' | 'inferred_max' | null = null,
): void {
  const { summary, diff } = out
  const ids = rows.map(r => r.id)

  // 24 個 motion 全對上：matched=24／missing=0／unmatched=0
  expect(summary.rows_in).toBe(expectedTaskCount())
  expect(summary.motions).toBe(rows.length)
  expect(summary.matched, `missing=${JSON.stringify(diff.missing)} unmatched=${JSON.stringify(diff.unmatched)}`).toBe(rows.length)
  expect(summary.missing).toBe(0)
  expect(summary.unmatched).toBe(0)
  expect([...diff.matched].sort()).toEqual([...ids].sort())
  expect(diff.missing).toEqual([])
  expect(diff.unmatched).toEqual([])
  expect(summary.cross_station).toEqual([])
  expect(summary.offline_conflicts).toEqual([])

  // general 不再 missing：已回寫；take_unit 只插首站一份 → 單列單站（LB §2、§8 (a)）
  const generals = rows.filter(r => r.level.is_general)
  expect(generals).toHaveLength(1)
  for (const g of generals) {
    const m = diff.motions[g.id]
    expect(m, `general ${g.id} 應已回寫`).toBeTruthy()
    expect(m.task_ids, `general ${g.id}`).toHaveLength(1)
    expect(m.stations, `general ${g.id}`).toHaveLength(1)
  }

  // 持工具 motion 的 acquire／use／release 三列聚合為單站。依據：Q=1 的 episode 靠 LB ADR-023 D3（同站同人）；
  // lot 的 episode（I，Q>1，LB §3.1 不在 D3 範圍）靠 group（硬性同站）。
  const tooled = rows.filter(r => r.tool_vocab_id)
  expect(tooled).toHaveLength(5)
  for (const t of tooled) {
    const m = diff.motions[t.id]
    expect(m.task_ids, `tool motion ${t.id}`).toHaveLength(3)
    expect(m.stations, `tool motion ${t.id}`).toHaveLength(1)
    expect(m.cross_station).toBe(false)
  }

  // 件數（Howard 2026-09-18 裁：C＋退路）：LB 的 setup 列帶 used（0／1，Σ＝經手人數）不是件數，不可跨列加總；
  // 有 qty_scope 取 cyclic 那列，沒有就各列取最大值（標為推算）。比對基準是 MOST 自己投影出的 Q，不是 frequency。
  // 每個 motion：Q>1 → units_total == Q；Q=1 → LB 不帶 units（null）。
  expect(summary.units_baseline).toEqual({ status: 'ok', reasons: [] })  // 已用投影 Q 比對（不是沒比）
  expect(diff.units_uncomparable).toEqual([])
  expect([...projectedQ.values()].filter(q => q > 1)).toHaveLength(3)  // G、H（frequency 8）與 I（repeat 8）
  for (const r of rows) {
    const q = projectedQ.get(r.id) ?? 1
    expect(diff.motions[r.id].units_total, `units ${r.id}`).toBe(q > 1 ? q : null)
  }
  // 動作 I（seq 9，electric_driver repeat 8）：LB 回 1/8/1，舊做法加總成 10；現在是 8。
  const actionI = rows[GOLDEN_LETTERS.indexOf('I')]
  expect(diff.motions[actionI.id].units_total).toBe(8)
  if (unitsSource) expect(diff.motions[actionI.id].units_source).toBe(unitsSource)
  else expect(['cyclic', 'inferred_max']).toContain(diff.motions[actionI.id].units_source)
  expect(diff.unit_mismatches).toEqual([])

  // offline：兩邊一致（無差異）；offline 列不排站、無人（LB §8 (b)）
  expect(diff.offline_diffs).toEqual([])
  const offline = rows.filter(r => r.level.offline)
  expect(offline).toHaveLength(1)
  for (const r of offline) {
    expect(diff.motions[r.id].offline).toBe(true)
    expect(diff.motions[r.id].stations).toEqual([])
    expect(diff.motions[r.id].workers).toEqual([])
  }
}

async function expectLatestMatches(
  request: APIRequestContext, worksheetId: string, out: WritebackOut, rows: GoldenRow[], projectedQ: Map<string, number>,
  unitsSource: 'cyclic' | 'inferred_max' | null = null,
) {
  const res = await request.get(`/api/v2/worksheets/${worksheetId}/lb-writeback/latest`, { headers: AUTH })
  expect(res.status(), await res.text()).toBe(200)
  const latest = (await res.json()) as WbLatest
  expect(latest.snapshot_id).toBe(out.snapshot_id)
  expectGoldenWriteback(latest, rows, projectedQ, unitsSource)
}

test('黃金複本：import LB fixture（依 seq_no 改寫 id）→ 24 motion 全對上', async ({ request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  const { worksheetId, rows } = await saveWritebackReplica(request, DEMO_WS, await ensureReplicaVocab(request))
  const projectedQ = await projectedQuantities(request, worksheetId)

  // 件數的兩條路徑都要覆蓋：fixture 自 LB `106bf14` 起帶 qty_scope（件數＝cyclic 列，確定值），但 DB 裡
  // 沒有 qty_scope 的舊快照會存在很久——退路不能因為主路徑通了就失去覆蓋（Howard 2026-09-21 F4）。
  // 兩條在**同一份複本**內先後 import（第二次產生新快照，保留策略上限 10）——拆成兩個 test 會讓每跑一次
  // 在共用 dev DB 留下兩份工序表（worksheet 無 DELETE 端點，清不掉）。
  for (const { name, stripScope, source } of [
    { name: '帶 qty_scope → 件數取 cyclic 列（確定值）', stripScope: false, source: 'cyclic' as const },
    { name: '無 qty_scope（舊快照）→ 各列取最大值（推算）', stripScope: true, source: 'inferred_max' as const },
  ]) {
    // test.step：expectGoldenWriteback 的約 30 條斷言都在同一個呼叫點，不包 step 的話紅了分不出是哪條路徑
    await test.step(name, async () => {
      const fx = JSON.parse(readFileSync(path.join(FIXTURES_DIR, 'writeback_sample.json'), 'utf-8')) as WritebackPayload
      if (stripScope) for (const r of fx.rows as Array<Record<string, unknown>>) delete r.qty_scope

      const res = await request.post(`/api/v2/worksheets/${worksheetId}/lb-writeback/import`, {
        headers: AUTH, data: remapToReplica(fx, rows),
      })
      expect(res.status(), await res.text()).toBe(200)
      const out = (await res.json()) as WritebackOut
      expect(out.summary.result_id).toBe(fx.result_id)
      expectGoldenWriteback(out, rows, projectedQ, source)
      await expectLatestMatches(request, worksheetId, out, rows, projectedQ, source)
    })
  }
})

// ── 真機端到端 ────────────────────────────────────────────────────────────

const LB_IDENTITY_HEADERS = ['X-User-Id', 'X-Plant-Code', 'X-Username'] as const
const LB_ID = /^[A-Za-z0-9_-]{1,64}$/  // LB id 的安全字元集（只含英數、_、-；不含 /、.、空白）
const SOLVE_STATES = new Set(['queued', 'running', 'done', 'failed', 'cancelled'])

/** E2E_LB_AUTH_HEADERS → 只取三個身分 header（語法同 DDM_LB_AUTH_HEADERS；@me → 本測試身分）。錯誤訊息不帶值。 */
function lbHeaders(): Record<string, string> {
  const raw = (process.env.E2E_LB_AUTH_HEADERS ?? '').trim()
  let parsed: Record<string, unknown> = {}
  if (raw.startsWith('{')) {
    try {
      parsed = JSON.parse(raw) as Record<string, unknown>
    } catch {
      throw new Error('E2E_LB_AUTH_HEADERS 不是合法 JSON')
    }
  } else {
    for (const pair of raw.split(',')) {
      const i = pair.indexOf('=')
      if (i > 0) parsed[pair.slice(0, i).trim()] = pair.slice(i + 1).trim()
    }
  }
  const out: Record<string, string> = {}
  for (const h of LB_IDENTITY_HEADERS) {
    const v = parsed[h] == null ? '' : String(parsed[h])  // 同 MOST _parse_lb_headers：JSON 值一律 str()
    if (v) out[h] = v === '@me' ? AUTH['X-Username'] : v
  }
  const missing = LB_IDENTITY_HEADERS.filter(h => !out[h])
  if (missing.length) throw new Error(`E2E_LB_AUTH_HEADERS 缺 ${missing.join('／')}（LB 缺任一回 401）`)
  return out
}

// 與 LB scripts/gen_writeback_sample.py（黃金 server_node 求解）同參數。
const SOLVE_PARAMS = {
  target_takt: 30_000, cycle_time: 30_000,
  max_lines: 1, min_stations_per_line: 6, max_stations_per_line: 6, max_tasks_per_station: 20,
  max_workers: 14, max_workers_per_station: 3, min_workers_per_station: 1,
  merge_multiplier: 1.0, cross_line_movement_budget: 0, cross_line_movement_cost: 0,
  objective_scenario: 'Balanced',
  line_station_config: { line_station_available_actions: {}, line_station_positions: {} },
  max_time_seconds: 60, enable_offline_handling: true,
}
const SOLVE_DEADLINE_MS = 5 * 60_000
const LB_CALL_TIMEOUT_MS = 30_000

test('黃金複本：真機端到端 MOST 匯出 → LB 上傳求解 → MOST fetch → 24 motion 全對上', { tag: '@slow' }, async ({ request }) => {
  const lb = process.env.E2E_LB_BASE_URL?.trim().replace(/\/+$/, '')
  if (!lb && process.env.E2E_LB_AUTH_HEADERS) throw new Error('設了 E2E_LB_AUTH_HEADERS 卻沒設 E2E_LB_BASE_URL')
  test.skip(!lb, '未設 E2E_LB_BASE_URL（真機端到端）')
  const headers = lbHeaders()  // 缺 header → 在任何請求之前失敗
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  // 求解期限＋各步驟與清理的單次請求上限，確保測試逾時前 finally 的清理還跑得到
  test.setTimeout(SOLVE_DEADLINE_MS + 4 * LB_CALL_TIMEOUT_MS + 60_000)

  const { worksheetId, rows } = await saveWritebackReplica(request, DEMO_WS, await ensureReplicaVocab(request))
  const exported = await request.get(`/api/v2/worksheets/${worksheetId}/export/lb-csv`, { headers: AUTH })
  expect(exported.status(), await exported.text()).toBe(200)
  const csv = await exported.text()

  const up = await request.post(`${lb}/api/v3/projects`, {
    headers, timeout: LB_CALL_TIMEOUT_MS,
    multipart: {
      file: { name: 'most-golden-replica.csv', mimeType: 'text/csv', buffer: Buffer.from(csv, 'utf-8') },
      product_name: 'e2e-most-writeback', sku_name: `golden-replica-${Date.now()}`, complexity: '',
    },
  })
  expect(up.status(), await up.text()).toBe(200)
  const projectId = ((await up.json()) as { id?: unknown }).id
  if (typeof projectId !== 'string' || !LB_ID.test(projectId)) throw new Error('LB 建專案回應的 id 格式不合法')
  const projectUrl = `${lb}/api/v3/projects/${encodeURIComponent(projectId)}`

  let bodyError: unknown = null
  try {
    const solve = await request.post(`${projectUrl}/versions/original/results`, {
      headers, timeout: LB_CALL_TIMEOUT_MS, data: { project_id: projectId, version_id: 'original', ...SOLVE_PARAMS },
    })
    expect(solve.status(), await solve.text()).toBe(202)
    const sessionId = ((await solve.json()) as { solve_session_id: string }).solve_session_id

    let job: { state: string; result_id: string | null; message: string | null } = { state: 'queued', result_id: null, message: null }
    const deadline = Date.now() + SOLVE_DEADLINE_MS
    while (job.state === 'queued' || job.state === 'running') {
      if (Date.now() > deadline) throw new Error(`LB 求解逾時（${SOLVE_DEADLINE_MS / 1000}s），最後狀態 ${job.state}`)
      await new Promise(r => setTimeout(r, 3_000))
      const st = await request.get(`${lb}/api/v3/optimize-multi-line/sessions/${encodeURIComponent(sessionId)}`, {
        headers, timeout: LB_CALL_TIMEOUT_MS,
      })
      expect(st.status(), await st.text()).toBe(200)
      job = await st.json()
      if (!SOLVE_STATES.has(job.state)) throw new Error(`LB 求解狀態不在契約內：${String(job.state)}`)
    }
    expect(job.state, job.message ?? '').toBe('done')
    expect(job.result_id).toBeTruthy()

    const res = await request.post(`/api/v2/worksheets/${worksheetId}/lb-writeback/fetch`, {
      headers: AUTH, data: { lb_project_id: projectId, lb_version_id: 'original', lb_result_id: job.result_id },
    })
    expect(res.status(), await res.text()).toBe(200)
    const out = (await res.json()) as WritebackOut
    expect(out.summary).toMatchObject({
      contract_version: 'lb-most-writeback-v1', project_id: projectId, version_id: 'original', result_id: job.result_id,
    })
    const projectedQ = await projectedQuantities(request, worksheetId)
    expectGoldenWriteback(out, rows, projectedQ)
    await expectLatestMatches(request, worksheetId, out, rows, projectedQ)
  } catch (e) {
    bodyError = e
    throw e
  } finally {
    // 自建自清：主體成功而清理失敗 → 測試失敗；主體已失敗 → 只附註清理結果，不蓋掉原因。不印回應 body。
    let cleanupProblem: string | null = null
    try {
      const del = await request.delete(projectUrl, { headers, timeout: LB_CALL_TIMEOUT_MS })
      if (del.status() !== 200) cleanupProblem = `HTTP ${del.status()}`
    } catch (e) {
      // 只取訊息第一行（Playwright 的 call log 在後面，含 header 值）
      cleanupProblem = e instanceof Error ? e.message.split('\n')[0] : 'request error'
    }
    if (cleanupProblem) {
      const msg = `清理 LB 專案 ${projectId} 失敗（${cleanupProblem}）`
      if (bodyError) console.warn(msg)
      else throw new Error(msg)
    }
  }
})
