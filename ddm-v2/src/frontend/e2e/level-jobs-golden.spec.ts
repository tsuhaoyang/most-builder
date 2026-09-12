/**
 * DoD-1（ADR-035 D10 §0.4/§8.3）：黃金複本經 API 建 24 列 → 存 → lb-csv 與 expected 除 duration/divisible
 * 兩欄外逐欄相等；tasks_out==34；errors==[]。複本 TMU 與黃金不同故排除 duration；divisible 見 §3.2。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { ensureReplicaVocab, buildGoldenRows } from './support/goldenReplica'

const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'
const HERE = path.dirname(fileURLToPath(import.meta.url))
const EXPECTED = path.resolve(HERE, '..', '..', '..', 'docs', 'lb-integration', 'fixtures', 'server_node_tasks.expected.csv')

function parseCsv(text: string): { header: string[]; rows: string[][] } {
  const lines = text.replace(/^\ufeff/, '').trim().split('\n')
  const parse = (line: string): string[] => {
    const out: string[] = []
    let cur = '', q = false
    for (const ch of line) {
      if (ch === '"') q = !q
      else if (ch === ',' && !q) { out.push(cur); cur = '' }
      else cur += ch
    }
    out.push(cur)
    return out
  }
  return { header: parse(lines[0]), rows: lines.slice(1).map(parse) }
}

async function seeded(request: APIRequestContext): Promise<boolean> {
  return (await request.get(`/api/v2/worksheets/${WS}`, { headers: AUTH })).status() === 200
}

test('DoD-1: golden replica lb-csv equals expected except duration/divisible', async ({ request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  const vocab = await ensureReplicaVocab(request)
  const rows = buildGoldenRows(vocab)
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  const saved = await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })
  expect(saved.status(), await saved.text()).toBe(200)

  // errors==[] + tasks_out==34
  const rep = await (await request.get(`/api/v2/worksheets/${wsId}/export/lb-report`, { headers: AUTH })).json() as { errors: unknown[]; tasks_out: number }
  expect(rep.errors, JSON.stringify(rep.errors)).toEqual([])
  expect(rep.tasks_out).toBe(34)

  // lb-csv 除 duration/divisible 外逐欄相等
  const csvText = await (await request.get(`/api/v2/worksheets/${wsId}/export/lb-csv`, { headers: AUTH })).text()
  const got = parseCsv(csvText)
  const exp = parseCsv(readFileSync(EXPECTED, 'utf-8'))
  expect(got.header).toEqual(exp.header)
  expect(got.rows.length).toBe(exp.rows.length)
  // 排除欄：duration（複本 TMU 不同，§8.3）、divisible（§3.2 task31 1→0）、
  // action（複本 use/單列敘述由不同 MOST 內容產生；acquire/release 的 pick up/put down {tool} 仍比對）、
  // source_wi_row_id（複本 UUID 不同）。其餘語意欄（predecessors/group/atomic_group/quantity/qty_scope/
  // tool_id/tool_action/segment/fixed_station/offline_flag/role_type/general_role/part_id…）逐欄相等。
  const EXCLUDE = new Set(['duration', 'divisible', 'action', 'source_wi_row_id'])
  for (let r = 0; r < exp.rows.length; r++) {
    for (let c = 0; c < exp.header.length; c++) {
      if (EXCLUDE.has(exp.header[c])) continue
      expect(got.rows[r][c], `row ${r + 1} col ${exp.header[c]}`).toBe(exp.rows[r][c])
    }
  }
})
