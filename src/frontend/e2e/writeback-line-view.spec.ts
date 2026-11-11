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
import { ensureReplicaVocab, saveWritebackReplica } from './support/goldenReplica'

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
  // 依 model_label 重用同一份工序表（每次重存列、列 id 隨機），不再每跑一次 clone 一份——worksheet 沒有 DELETE
  // 端點，clone 出來的會永久留在共用 dev DB（2026-09-22 一天就累積十幾份）。快照受保留策略上限 10 筆。
  const { worksheetId: wsId, rows } = await saveWritebackReplica(
    request, WS, await ensureReplicaVocab(request), 'e2e: LB writeback line view')

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
  // 這份 payload 沒有 export_warnings（舊 LB）：不得出現任何 LB 自述警告
  await expect(page.getByTestId('writeback-lb-dropped')).toHaveCount(0)
  await expect(page.getByTestId('writeback-lb-warnings-truncated')).toHaveCount(0)

  // 路徑三（LB §8 export_warnings）：刻意製造降級與丟列，確認 **UI** 真的講出來（不是只有 API 有）。
  // units_degraded 的 source_wi_row_id 用**非正規拼法**（無連字號、大寫）——MOST 沒正規化就會靜默對不上。
  const fxWarn = JSON.parse(readFileSync(FIXTURE, 'utf-8'))
  remap(fxWarn)
  type WRow = { task_id: number; source_wi_row_id: string; units: unknown }
  const wrows = fxWarn.rows as WRow[]
  // 黃金三列（動作 I，electric_driver repeat 8：task 13 setup／14 cyclic／15 setup）映到複本的動作 I
  const goldI = wrows.find(r => r.task_id === 14)!.source_wi_row_id
  for (const r of wrows) if (r.source_wi_row_id === goldI) r.source_wi_row_id = replicaIds[8]
  wrows.find(r => r.task_id === 13)!.units = null           // setup_not_one 的真實情境：降級的是 setup 列
  wrows.find(r => r.source_wi_row_id === replicaIds[6])!.units = null  // conservation：降級的是件數列
  const odd = (id: string) => id.replace(/-/g, '').toUpperCase()
  fxWarn.export_warnings = {
    units_degraded: [
      { task_id: 13, source_wi_row_id: odd(replicaIds[8]), units_sum: 2, quantity: 8, reason: 'setup_not_one' },
      { task_id: 901, source_wi_row_id: odd(replicaIds[6]), units_sum: 7, quantity: 8, reason: 'conservation' },
      { task_id: 903, source_wi_row_id: odd(replicaIds[1]), reason: 'lb_future_reason' },  // 未知 reason 可不帶數字
      { task_id: 904, source_wi_row_id: 'b0000000-0000-4000-8000-000000000099', units_sum: 3, quantity: 8,
        reason: 'conservation' },  // 對不上這份工序表的任何步驟
    ],
    dropped_rows: [
      { task_id: 77, reason: 'source_wi_row_id_not_uuid' },
      { task_id: 78, reason: 'lb_future_reason' },  // 未知 reason：照常存、照常顯示，不 422，也不替它編原因
    ],
    truncated: true,
  }
  const imp3 = await request.post(`/api/v2/worksheets/${wsId}/lb-writeback/import`, { headers: AUTH, data: fxWarn })
  expect(imp3.status(), await imp3.text()).toBe(200)
  await openLineView()
  // conservation：件數格消失，換成「沒把握」標記；兩數可比，可以並排
  await expect(units).toHaveCount(0)
  await expect(page.getByTestId(`writeback-units-degraded-${replicaIds[6]}`)).toContainText('算出 7 件、數量是 8')
  // setup_not_one：件數仍確定——「共 8 件」照常顯示，標記講「件數不受影響」，且不並排那兩個數字
  await expect(page.getByTestId(`writeback-units-${replicaIds[8]}`)).toHaveText('共 8 件')
  const setupMark = page.getByTestId(`writeback-units-degraded-${replicaIds[8]}`)
  await expect(setupMark).toContainText('件數不受影響')
  await expect(setupMark).toContainText('產線平衡工作項 13')  // 作業者要能回產線平衡找到那一列
  await expect(setupMark).not.toContainText('2')              // Σused 與數量本來就不該相等，不得並排

  await expect(page.getByTestId(`writeback-units-degraded-${replicaIds[1]}`)).toContainText('原因無法辨識')
  // 丟列：筆數用全部丟列（2）；丟列清單本身沒滿到上限，所以仍給「至多 2 步」（truncated 是另一張清單滿了也會亮）。
  // 原因分開講：已知的講對應資料損壞並給下一步，未知的講「原因無法辨識」，不替它編原因
  await expect(page.getByTestId('writeback-lb-dropped')).toContainText('2 列沒送回來')
  await expect(page.getByTestId('writeback-lb-dropped')).toContainText('至多 2 步')
  await expect(page.getByTestId('writeback-lb-dropped-key-damaged')).toContainText('其中 1 列是對應資料損壞')
  await expect(page.getByTestId('writeback-lb-dropped-unknown')).toContainText('其中 1 列的原因無法辨識')
  await expect(page.getByTestId('writeback-lb-degraded-unattached')).toContainText('1 筆')
  await expect(page.getByTestId('writeback-lb-warnings-truncated')).toContainText('前 50 筆')
  // 沒有結果的步驟：原本的說明保留，只補一句「也可能是沒送回來的那幾列之一」
  const firstMissing = page.getByTestId('writeback-missing').first()
  await expect(firstMissing).toContainText('產線平衡沒有這一步的結果')
  await expect(firstMissing.getByTestId('writeback-missing-dropped-tag')).toBeVisible()
  // 驗收證據：放大視窗再拍，避免被外層捲動框裁掉（上一版只拍到上半段）
  await page.setViewportSize({ width: 1400, height: 3200 })
  // 標記再長也不能把步驟名稱擠掉（上一版在這個寬度下，動作 I 那列只剩「第」一個字；較窄時標記會自己換行、
  // 反而看不出來）。CSS 截斷不會把文字從 DOM 拿掉，所以量實際渲染寬度，而不是比對文字
  const labelWidth = await page.getByTestId(`writeback-motion-${replicaIds[8]}`).locator('span').first()
    .evaluate(el => (el as HTMLElement).clientWidth)
  expect(labelWidth, '步驟名稱被擠掉了').toBeGreaterThan(120)
  await page.getByTestId('writeback-panel').screenshot({ path: test.info().outputPath('writeback-export-warnings.png') })

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
