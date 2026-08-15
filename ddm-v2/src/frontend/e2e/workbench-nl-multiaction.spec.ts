import { test, expect } from '@playwright/test'
import {
  installMocks, gotoWorkbenchAndParse, draftContentCalculated,
} from './support/workbenchNlMocks'

// ── MOST 工作台（workbench-v3）× NL 多 action 草稿（spec §18.3）────────────────
// 條文：「前端完成多 action UI 前不得自動丟棄額外 action」。
// 後端契約（wi_ai_service）：頂層 slots 是舊前端相容的壓平欄位，ai.drafts 是權威草稿。
// 本檔驗證：
//   1) 多 action → 逐筆呈現、逐筆採用（採用 → 新增動作 → 採用下一筆迴圈）
//   2) 負向：絕不「只採用第一筆、其餘消失」——每筆 draft 都有卡片、無任何自動套用
//   3) 單 action 既有流程不退化（自動覆蓋填入 + 無多 action 警示）
// mock 與 fixtures 共用 ./support/workbenchNlMocks（與 workbench-nl-guards.spec 同源）。

test('§18.3 多 action：逐筆呈現 → 採用 → 新增動作 → 採用下一筆（含 review 事件）', async ({ page }) => {
  const captured = await installMocks(page)
  await gotoWorkbenchAndParse(page, '從料架取得DIMM放至流水線，然後推治具到位')

  // 逐筆呈現：兩筆 draft 各有卡片＋多 action 警示
  await expect(page.getByTestId('nl-multi-warning')).toBeVisible()
  await expect(page.locator('[data-testid^="ai-action-card-"]')).toHaveCount(2)
  await expect(page.getByTestId('ai-action-card-act-2').getByText('推治具到位')).toBeVisible()

  // 未採用前不得自動套用（含 debounce 窗口）：無草稿內容的試算、編輯器仍是空白 GM
  await page.waitForTimeout(700)
  expect(draftContentCalculated(captured.calcBodies)).toBe(false)
  await expect(page.getByLabel('動作類型')).toHaveValue('GM')
  await expect(page.getByText('簡單抓握')).toHaveCount(0)

  // 採用第 1 筆 → 編輯器載入 GM 草稿並經後端試算
  const gmCalc = page.waitForResponse(r =>
    r.url().endsWith('/api/v2/minimost/calculate') && r.request().method() === 'POST'
    && (JSON.parse(r.request().postData() ?? '{}') as { g2?: { g_code?: string } }).g2?.g_code === 'g_simple')
  await page.getByTestId('ai-action-card-act-1').getByRole('button', { name: '採用到編輯器' }).click()
  await gmCalc
  await expect(page.getByTestId('ai-action-card-act-1').getByText('已採用（再載入）')).toBeVisible()
  await expect(page.getByLabel('動作類型')).toHaveValue('GM')
  await expect(page.getByText('簡單抓握').first()).toBeVisible()
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('28')

  // 存為動作（採用迴圈第一步）：存檔後 NL 面板必須留著（否則其餘草稿變相被丟棄）
  await page.getByText('WI 語句', { exact: true }).locator('..').locator('input').fill('E2E多動作-1')
  const created = page.waitForResponse(r =>
    new URL(r.url()).pathname === '/api/v2/motion-modules' && r.request().method() === 'POST' && r.status() === 201)
  const published = page.waitForResponse(r =>
    /\/motion-modules\/[^/]+\/publish$/.test(new URL(r.url()).pathname) && r.status() === 201)
  await page.getByRole('button', { name: '新增動作' }).click()
  await created
  await published
  await expect(page.getByText(/已新增動作：E2E多動作-1/)).toBeVisible()
  await expect(page.getByTestId('nl-multi-warning')).toBeVisible()
  await expect(page.locator('[data-testid^="ai-action-card-"]')).toHaveCount(2)
  await expect(page.getByTestId('ai-action-card-act-1').getByText('已採用（再載入）')).toBeVisible()

  // 採用第 2 筆 → 編輯器切到 CM 草稿
  const cmCalc = page.waitForResponse(r =>
    r.url().endsWith('/api/v2/minimost/calculate') && r.request().method() === 'POST'
    && (JSON.parse(r.request().postData() ?? '{}') as { seq?: string }).seq === 'CM')
  await page.getByTestId('ai-action-card-act-2').getByRole('button', { name: '採用到編輯器' }).click()
  await cmCalc
  await expect(page.getByLabel('動作類型')).toHaveValue('CM')
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('29')

  // 逐筆 review 事件（accept_plan × 2，各自帶 action_id）
  await expect.poll(() => captured.reviewBodies.length).toBe(2)
  const acceptedIds = captured.reviewBodies.flatMap(b =>
    ((b.events ?? []) as Array<{ event_type: string; target?: { action_id?: string } }>)
      .filter(e => e.event_type === 'accept_plan')
      .map(e => e.target?.action_id))
  expect(acceptedIds).toEqual(['act-1', 'act-2'])
})

test('§18.3 負向：絕不「只採用第一筆、其餘消失」', async ({ page }) => {
  const captured = await installMocks(page)
  await gotoWorkbenchAndParse(page, '從料架取得DIMM放至流水線，然後推治具到位')

  // 後端回幾筆 draft，畫面就要有幾張卡——第二筆不得消失
  await expect(page.locator('[data-testid^="ai-action-card-"]')).toHaveCount(2)
  await expect(page.getByTestId('ai-action-card-act-1')).toBeVisible()
  await expect(page.getByTestId('ai-action-card-act-2')).toBeVisible()
  await expect(page.getByTestId('ai-action-card-act-2').getByText('推治具到位')).toBeVisible()

  // 且不得把首 action 靜默套進編輯器（等超過 calculate debounce 400ms 再驗）：
  //   - 沒有任何帶草稿內容（g_simple／CM）的試算請求
  //   - 編輯器仍是空白預設（GM、無 G 值、TMU 尚未有草稿值）
  await page.waitForTimeout(700)
  expect(draftContentCalculated(captured.calcBodies)).toBe(false)
  await expect(page.getByLabel('動作類型')).toHaveValue('GM')
  await expect(page.getByText('簡單抓握')).toHaveCount(0)
  await expect(page.getByTestId('summary-base-tmu')).not.toHaveText('28')

  // 多 action 時不得以首 action 的壓平 slots 冒充解析結果（相容欄位列隱藏）
  await expect(page.getByText('明確')).toHaveCount(0)
})

test('單 action 既有流程不退化：自動覆蓋填入＋無多 action 警示', async ({ page }) => {
  await installMocks(page)
  await gotoWorkbenchAndParse(page, '單動作：取得DIMM放至流水線')

  // 既有行為：編輯器空白＋相容欄位與權威草稿一致 → 直接覆蓋填入（相容 slots 流程）
  await expect(page.getByText('已覆蓋填入 AI 建議')).toBeVisible()
  await expect(page.getByText('簡單抓握').first()).toBeVisible()
  // 單 action：無多 action 警示；權威草稿卡仍逐筆（1 筆）呈現
  await expect(page.getByTestId('nl-multi-warning')).toHaveCount(0)
  await expect(page.locator('[data-testid^="ai-action-card-"]')).toHaveCount(1)
  // 壓平 slots badge 列（明確/推斷）在單 action 一致模式維持可見
  await expect(page.getByText('明確')).toBeVisible()
})
