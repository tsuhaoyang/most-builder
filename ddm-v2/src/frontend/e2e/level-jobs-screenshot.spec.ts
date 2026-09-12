/**
 * F3/F4 截圖：作業順序（flow）+ 作業內容抽屜（drawer），黃金 11 作業載入狀態。
 * 存 docs/lb-integration/screenshots/level-jobs-flow.png / level-jobs-drawer.png。
 * 需 dev server（__ddmTest, import.meta.env.DEV）。以 API 存一份含 wcub/cub/general/machine 的 worksheet →
 * 設 activeWs → 切 level tab（作業版為預設）→ 截圖。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'

const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'
const OBJ = '66666666-6666-6666-6666-666666666666'
const GM = { seq: 'GM', rule_set_code: 'MINIMOST_FACTORY_V1', a0: { reach_cm: 20 }, g2: { g_code: 'g_grasp' }, a3: { reach_cm: 25 }, p5: { p_base_code: 'p_place_none' } }

async function seeded(request: APIRequestContext): Promise<boolean> {
  return (await request.get(`/api/v2/worksheets/${WS}`, { headers: AUTH })).status() === 200
}

function row(seq: number, wiGroup: string, level: Record<string, unknown>) {
  return { id: crypto.randomUUID(), seq_no: seq, hand: 'RH', object_vocab_id: OBJ, frequency: 1,
           narrative: wiGroup, wi_group: wiGroup, cycle: GM,
           level: { ascription: 'main', level: '1', ...level } }
}

test('capture Level System jobs flow + drawer', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  // 6 列：兩個作業（裝 HDD ×3 sub、鎖背板 ×3 cub 同站）+ 一列離線 + 一列 general
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  const rows = [
    row(1, '把機箱上線', { is_general: true, general_role: 'take_unit' }),
    row(2, '預備螺絲', { offline: true }),
    row(3, '裝 HDD', { level: '2' }),
    row(4, '裝 HDD', { level: '2' }),
    row(5, '裝 HDD', { level: '2' }),
    row(6, '背板壓合', { level: '2', countersignature: 'cub10', order: 1 }),
  ]
  await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })

  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')
  await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
    t.workspace.getState().setActiveWs(id)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' }))
  }, wsId)

  // 等作業版渲染（標題「工序整理」）
  await page.getByText('工序整理').first().waitFor({ timeout: 8000 }).catch(() => {})
  await page.waitForTimeout(800)
  await page.screenshot({ path: '../../docs/lb-integration/screenshots/level-jobs-flow.png', fullPage: true })

  // 點一張作業卡開抽屜
  const card = page.locator('[data-testid^="job-card-"]').first()
  if (await card.count()) {
    await card.click()
    await page.waitForTimeout(500)
  }
  await page.screenshot({ path: '../../docs/lb-integration/screenshots/level-jobs-drawer.png', fullPage: true })
  expect(true).toBe(true)  // 截圖為設計產物，不硬斷言
})
