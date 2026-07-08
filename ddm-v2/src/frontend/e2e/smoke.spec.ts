import { test, expect } from '@playwright/test'

// 對單一伺服器預覽（preview_server :8099，含真實 DB）跑端對端冒煙。
test('workbench loads, identity + WI rows from worksheet', async ({ page }) => {
  await page.goto('/')
  // App title rendered as <h1> inside the AppLayout header
  await expect(page.getByRole('heading', { name: 'MOST Workbench' })).toBeVisible()
  await expect(page.getByText(/IEC141289/)).toBeVisible()               // 身分（/api/v2/me）
  // Sidebar nav button for the default MOST 工作台 tab (UX spec §1.2)
  await expect(page.getByRole('button', { name: /MOST 工作台/ })).toBeVisible()
  // WI 由作用中 worksheet 載入（種子 30 列）
  await expect(page.getByText(/合計/)).toBeVisible()
})

test('sidebar navigation renders each migrated feature', async ({ page }) => {
  await page.goto('/')

  // Rule-set tab (admin-gated; seed user IEC141289 is admin)
  await page.getByRole('button', { name: /Rule-set/ }).click()
  await expect(page.getByText(/A — 移動距離/)).toBeVisible()

  // SOP 版本 tab (secondary / legacy item in sidebar)
  await page.getByRole('button', { name: /SOP/ }).click()
  await expect(page.getByText(/作用中/).first()).toBeVisible()
  await expect(page.getByText(/同 SKU 全部版本/)).toBeVisible()

  // 使用者管理 tab
  await page.getByRole('button', { name: /使用者/ }).click()
  await expect(page.getByText(/使用者與角色/)).toBeVisible()
  await expect(page.getByText('IEC141289', { exact: false }).first()).toBeVisible()

  // 匯出 tab
  await page.getByRole('button', { name: /匯出/ }).click()
  await expect(page.getByRole('heading', { name: '匯出' })).toBeVisible()
})

test('import wizard opens from header button', async ({ page }) => {
  await page.goto('/')
  // Import button is now in the header (no emoji, plain text)
  await page.getByRole('button', { name: /匯入 Excel/ }).click()
  await expect(page.getByRole('heading', { name: /匯入 Excel/ })).toBeVisible()
  await expect(page.getByText(/選擇 .xlsx 檔/)).toBeVisible()
})
