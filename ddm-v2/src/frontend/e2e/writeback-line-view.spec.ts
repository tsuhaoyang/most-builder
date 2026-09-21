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

// 件數的兩條路徑都要有 UI 覆蓋：LB 自 106bf14 起帶 qty_scope（cyclic＝確定值），但 DB 裡沒有 qty_scope 的
// 舊快照會存在很久——退路不能因為主路徑通了就失去覆蓋（Howard 2026-09-21 F4）。
// 兩條路徑在**同一份 clone** 內先後 import（第二次產生新快照，保留策略上限 10）——拆成兩個 test 會讓
// 每跑一次在共用 dev DB 留下兩份工序表（worksheet 無 DELETE 端點，清不掉）。
test('line view shows LB actual result + apply offline（件數兩條路徑）', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  const vocab = await ensureReplicaVocab(request)
  const rows = buildGoldenRows(vocab)
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  const saved = await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })
  expect(saved.status(), await saved.text()).toBe(200)

  // 重映 fixture 的 source_wi_row_id：挑一個 offline 列給 replica 某列（造 offline_diff），
  // 其餘映到 replica 前幾列（matched）。
  const replicaIds = rows.map(r => (r as { id: string }).id)
  type FxRow = { source_wi_row_id: string; offline_flag: boolean; units: Array<{ units: number }> | null }
  // 重映 source_wi_row_id（兩次 import 都要做同一份映射，否則第二次會全變 unmatched）：
  // 件數（C＋退路）用 fixture 裡單列、units 8 的 lot，映到複本 G（seq 7，frequency 8）。
  const remap = (payload: { rows: FxRow[] }) => {
    const rs = payload.rows
    const offRow = rs.find(x => x.offline_flag)!
    offRow.source_wi_row_id = replicaIds[2]  // replica 第 3 列（MOST offline=False）→ 與 LB offline=True 成 diff
    // 挑列用語意條件（單列 motion）而非檔案順序：vendor 換版會重排 34 列，依順序挑會撈到工具三列裡的
    // setup 列，讓「一個 motion 只剩 setup 列」這種 LB 不會產生的情境悄悄混進來。
    const singles = rs.filter(x => !x.offline_flag
      && rs.filter(y => y.source_wi_row_id === x.source_wi_row_id).length === 1)
    expect(singles.length, 'fixture 應有至少 3 個非 offline 的單列 motion').toBeGreaterThanOrEqual(3)
    // 避開 replicaIds[2]（已給 offline 列）：重複指派會讓該 motion 變成「offline 列＋非 offline 列」
    // 的混合，意外帶上 offline_conflict——不是這支測試要測的東西
    const targets = [0, 1, 3].map(i => replicaIds[i])
    singles.slice(0, 3).forEach((x, i) => { x.source_wi_row_id = targets[i] })
    const lotRow = rs.find(x => x.units?.length === 1 && x.units[0].units === 8
      && rs.filter(y => y.source_wi_row_id === x.source_wi_row_id).length === 1)
    expect(lotRow, 'fixture 應有單列 lot（units 8）').toBeTruthy()
    lotRow!.source_wi_row_id = replicaIds[6]
  }
  const fx = JSON.parse(readFileSync(FIXTURE, 'utf-8'))
  remap(fx)

  const imp = await request.post(`/api/v2/worksheets/${wsId}/lb-writeback/import`, { headers: AUTH, data: fx })
  expect(imp.status(), await imp.text()).toBe(200)
  const impBody = await imp.json() as { diff: { offline_diffs: Array<{ wi_row_id: string }> } }
  const offDiffId = impBody.diff.offline_diffs.find(od => od.wi_row_id === replicaIds[2])?.wi_row_id
  expect(offDiffId, 'replica 第3列應在 offline_diffs').toBe(replicaIds[2])

  // 進該工序表的產線視角。第二次 import 後要重載頁面（react-query 快取），而重載會清掉
  // active worksheet 與分頁狀態——所以整段要能重跑，不能只 reload 了事。
  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')  // 條件在本 test 內不變，只檢一次——放進 openLineView
  // 的話，第二次呼叫觸發 skip 會把「路徑一已驗完、路徑二沒驗」整支標成 skipped，讀起來像沒問題
  const openLineView = async () => {
    await page.goto('/')
    await page.evaluate((id) => {
      const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
      t.workspace.getState().setActiveWs(id)
      window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' }))
    }, wsId)
    await page.locator('[data-testid^="job-card-"]').first().waitFor({ timeout: 10000 })
    await page.getByTestId('subview-line').click()
    await expect(page.getByTestId('writeback-panel')).toBeVisible({ timeout: 10000 })
  }
  await openLineView()
  await expect(page.getByTestId('writeback-placements')).toBeVisible()
  // 實際站別文案（使用者語言，不是 station_index=）
  await expect(page.getByTestId('writeback-placements')).toContainText(/第 \d+ 站|station \d+/i)
  // 路徑一（fixture 現況，帶 qty_scope=cyclic）：確定值，不得出現「推算」，也不掛解釋用的 tooltip
  const units = page.getByTestId(`writeback-units-${replicaIds[6]}`)
  await expect(units).toHaveText('共 8 件')
  await expect(units).not.toHaveAttribute('title', /.+/)

  // 路徑二（剝掉 qty_scope＝舊快照的樣子）：同一份工序表再 import 一次 → 新快照 → 改標「（推算）」並掛 tooltip。
  // 數字同樣是 8：差別只在確不確定，把來源講成確定值或反之，都是把不確定講成確定。
  const fxOld = JSON.parse(readFileSync(FIXTURE, 'utf-8'))
  for (const r of fxOld.rows as Array<Record<string, unknown>>) delete r.qty_scope
  remap(fxOld)
  const imp2 = await request.post(`/api/v2/worksheets/${wsId}/lb-writeback/import`, { headers: AUTH, data: fxOld })
  expect(imp2.status(), await imp2.text()).toBe(200)
  await openLineView()
  await expect(units).toHaveText('共 8 件（推算）')
  await expect(units).toHaveAttribute('title', /.+/)  // 解釋文案存在（刪掉 i18n key 這裡會紅）

  // 離線差異：勾選 replica 第3列 → 套用 → 成功訊息
  const off = page.getByTestId('writeback-offline-diffs')
  await expect(off).toBeVisible()
  await page.getByTestId(`writeback-offline-${replicaIds[2]}`).check()
  await page.getByTestId('writeback-apply-offline').click()
  await expect(page.getByTestId('writeback-apply-msg')).toBeVisible({ timeout: 10000 })
  // 這份工序表投影得出來 → 降級那行不該出現（條件寫錯會讓它永遠亮著，這條反向斷言零成本擋住）
  await expect(page.getByTestId('writeback-apply-report-unavailable')).toHaveCount(0)

  // 讀回：該列 offline 已生效
  const read = await (await request.get(`/api/v2/worksheets/${wsId}`, { headers: AUTH })).json() as { rows: Array<{ wi_row_id: string; lb_tags: { offline: boolean } }> }
  const row3 = read.rows.find(r => r.wi_row_id === replicaIds[2])
  expect(row3?.lb_tags.offline).toBe(true)
})
