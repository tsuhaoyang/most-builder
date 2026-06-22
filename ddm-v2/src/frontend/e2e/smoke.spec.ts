import { test, expect } from '@playwright/test'

// 對單一伺服器預覽（preview_server :8099，含真實 DB）跑端對端冒煙。
test('workbench loads, identity + WI rows from worksheet', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'MOST Workbench' })).toBeVisible()
  await expect(page.getByText(/IEC141289/)).toBeVisible()               // 身分（/api/v2/me）
  await expect(page.getByRole('button', { name: /WI 工時表/ })).toBeVisible()
  // WI 由作用中 worksheet 載入（種子 30 列）
  await expect(page.getByText(/合計/)).toBeVisible()
})

test('tab navigation renders each migrated feature', async ({ page }) => {
  await page.goto('/')

  await page.getByRole('button', { name: /④ Rule-set/ }).click()
  await expect(page.getByText(/A — 移動距離/)).toBeVisible()

  await page.getByRole('button', { name: /⑤ SOP/ }).click()
  await expect(page.getByText(/作用中/).first()).toBeVisible()
  await expect(page.getByText(/同 SKU 全部版本/)).toBeVisible()

  await page.getByRole('button', { name: /⑦ 使用者/ }).click()
  await expect(page.getByText(/使用者與角色/)).toBeVisible()
  await expect(page.getByText('IEC141289', { exact: false }).first()).toBeVisible()

  await page.getByRole('button', { name: /⑥ 匯出/ }).click()
  await expect(page.getByRole('heading', { name: '匯出' })).toBeVisible()
})

test('import wizard opens', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /📥 匯入 Excel/ }).click()
  await expect(page.getByRole('heading', { name: /匯入 Excel/ })).toBeVisible()
  await expect(page.getByText(/選擇 .xlsx 檔/)).toBeVisible()
})
