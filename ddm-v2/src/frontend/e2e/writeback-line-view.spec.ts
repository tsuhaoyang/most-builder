/**
 * F（ADR-036）：作業版產線視角「實際結果」區塊 ＋ 離線差異套用。
 * goldenReplica 建 worksheet → 用 fixture 重映 source_wi_row_id → import 回寫 → 開作業版 line 視角 →
 * WritebackPanel 顯示站別／人／差異 → 勾選 offline 差異套用 → 讀回 offline 生效。
 * 需 dev server（__ddmTest, import.meta.env.DEV）。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { ensureReplicaVocab, buildGoldenRows } from './support/goldenReplica'

const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'
const HERE = path.dirname(fileURLToPath(import.meta.url))
const FIXTURE = path.resolve(HERE, '..', '..', '..', 'docs', 'lb-integration', 'fixtures', 'writeback_sample.json')

async function seeded(request: APIRequestContext): Promise<boolean> {
  return (await request.get(`/api/v2/worksheets/${WS}`, { headers: AUTH })).status() === 200
}

test('line view shows LB actual result + apply offline', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  const vocab = await ensureReplicaVocab(request)
  const rows = buildGoldenRows(vocab)
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  const saved = await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })
  expect(saved.status(), await saved.text()).toBe(200)

  // 重映 fixture 的 source_wi_row_id：挑一個 offline 列給 replica 某列（造 offline_diff），
  // 其餘映到 replica 前幾列（matched）。
  const fx = JSON.parse(readFileSync(FIXTURE, 'utf-8'))
  const replicaIds = rows.map(r => (r as { id: string }).id)
  const offRow = fx.rows.find((x: { offline_flag: boolean }) => x.offline_flag)
  offRow.source_wi_row_id = replicaIds[2]  // replica 第 3 列（MOST offline=False）→ 與 LB offline=True 成 diff
  const nonOff = fx.rows.filter((x: { offline_flag: boolean }) => !x.offline_flag).slice(0, 3)
  nonOff.forEach((x: { source_wi_row_id: string }, i: number) => { x.source_wi_row_id = replicaIds[i] })

  const imp = await request.post(`/api/v2/worksheets/${wsId}/lb-writeback/import`, { headers: AUTH, data: fx })
  expect(imp.status(), await imp.text()).toBe(200)
  const impBody = await imp.json() as { diff: { offline_diffs: Array<{ wi_row_id: string }> } }
  const offDiffId = impBody.diff.offline_diffs.find(od => od.wi_row_id === replicaIds[2])?.wi_row_id
  expect(offDiffId, 'replica 第3列應在 offline_diffs').toBe(replicaIds[2])

  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')
  await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
    t.workspace.getState().setActiveWs(id)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' }))
  }, wsId)
  await page.locator('[data-testid^="job-card-"]').first().waitFor({ timeout: 10000 })

  // 切 line 視角 → WritebackPanel 出現
  await page.getByTestId('subview-line').click()
  await expect(page.getByTestId('writeback-panel')).toBeVisible({ timeout: 10000 })
  await expect(page.getByTestId('writeback-placements')).toBeVisible()
  // 實際站別文案（使用者語言，不是 station_index=）
  await expect(page.getByTestId('writeback-placements')).toContainText(/第 \d+ 站|station \d+/i)

  // 離線差異：勾選 replica 第3列 → 套用 → 成功訊息
  const off = page.getByTestId('writeback-offline-diffs')
  await expect(off).toBeVisible()
  await page.getByTestId(`writeback-offline-${replicaIds[2]}`).check()
  await page.getByTestId('writeback-apply-offline').click()
  await expect(page.getByTestId('writeback-apply-msg')).toBeVisible({ timeout: 10000 })

  // 讀回：該列 offline 已生效
  const read = await (await request.get(`/api/v2/worksheets/${wsId}`, { headers: AUTH })).json() as { rows: Array<{ wi_row_id: string; lb_tags: { offline: boolean } }> }
  const row3 = read.rows.find(r => r.wi_row_id === replicaIds[2])
  expect(row3?.lb_tags.offline).toBe(true)
})
