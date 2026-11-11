/**
 * F7（ADR-035 D10）：工時表「作業」欄（wi_group）UI 全鏈。以 DEV wiStore hook 注入一列 → 切工作台分頁 →
 * 在表格作業欄輸入 → 讀回 wiStore 確認該列 wiGroup 已更新（欄位↔store 綁定正確）；
 * 並確認 datalist 存在（既有作業名重用）。save→DB roundtrip 另由 B1 單元 + hydrate spec 覆蓋。
 * 需 dev server（__ddmTest, import.meta.env.DEV）。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'

const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'

async function seeded(request: APIRequestContext): Promise<boolean> {
  return (await request.get(`/api/v2/worksheets/${WS}`, { headers: AUTH })).status() === 200
}

test('作業 column binds to row.wiGroup + datalist for reuse', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')

  // 設 activeWs（'wi' 分頁需要）+ 切工作台分頁
  await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
    t.workspace.getState().setActiveWs(id)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'wi' }))
  }, wsId)
  // 等工序表渲染（工作台標題）後再注入，避開 useWorksheetWorkspace 首次 hydrate 覆寫
  await page.getByText('工序', { exact: false }).first().waitFor({ timeout: 10000 }).catch(() => {})
  await page.waitForTimeout(800)
  const ids = await page.evaluate(() => {
    const t = (window as unknown as { __ddmTest: { wiStore: { getState: () => { setRows: (r: unknown[]) => void } } } }).__ddmTest
    const mk = (wiGroup: string | null) => ({
      id: crypto.randomUUID(), seq: 'GM', handCode: 'RH', freq: 1, simoGroup: '',
      nv: {}, narr: '動作', narrEn: null, wiGroup, tmu: 10, seconds: 0.36, payload: null,
    })
    const a = mk('鎖螺絲'); const b = mk(null)
    t.wiStore.getState().setRows([a, b])
    return { a: (a as { id: string }).id, b: (b as { id: string }).id }
  })

  // 待輸入列的作業欄
  const cell = page.getByTestId(`row-wi-group-${ids.b}`)
  await cell.waitFor({ timeout: 10000 })
  await cell.fill('裝機箱')
  await cell.blur()

  // 讀回 store 確認 b 列 wiGroup 已更新
  const bGroup = await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { wiStore: { getState: () => { rows: Array<{ id: string; wiGroup: string | null }> } } } }).__ddmTest
    return t.wiStore.getState().rows.find(r => r.id === id)?.wiGroup ?? null
  }, ids.b)
  expect(bGroup).toBe('裝機箱')

  // datalist 存在且含既有作業名「鎖螺絲」
  const hasOption = await page.locator('#wi-group-options option[value="鎖螺絲"]').count()
  expect(hasOption).toBeGreaterThan(0)

  // 作業大綱（由 rows.wiGroup 推導）：現在應有兩個作業
  await expect(page.getByTestId('job-outline')).toBeVisible()
  await expect(page.locator('[data-testid="job-outline-row"]')).toHaveCount(2)
})
