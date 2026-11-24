import { test, expect } from '@playwright/test'

// 對單一伺服器預覽（preview_server :8099，含真實 DB）跑端對端冒煙。
test('app loads, identity + dashboard cards (ADR-021 default tab)', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('script[src*="cdn.tailwindcss.com"]')).toHaveCount(0)
  await expect(page.locator('link[rel="stylesheet"][href*="/assets/"]')).toHaveCount(1)
  // App title rendered as <h1> inside the AppLayout header
  await expect(page.getByRole('heading', { name: 'MOST Workbench' })).toBeVisible()
  await expect(page.getByText(/IEC141289/)).toBeVisible()               // 身分（/api/v2/me）
  // ADR-038 D4（W6）：側欄不再有 MOST 工作台
  await expect(page.getByRole('button', { name: /MOST 工作台/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /分析案件/ })).toBeVisible()
  // 預設 tab = 儀表板：三張卡（資料來自真實 DB 種子）
  await expect(page.getByText('MOST 字典總覽')).toBeVisible()
  await expect(page.getByText('案件狀態統計')).toBeVisible()
  await expect(page.getByText('近期案件')).toBeVisible()
})

test('sidebar navigation renders each migrated feature', async ({ page }) => {
  await page.goto('/')

  // MOST 字典 tab（admin-gated；seed user IEC141289 是 admin）
  // ADR-023 D4：兩層結構，先落在 L1 版本清單
  await page.getByRole('button', { name: /MOST 字典/ }).click()
  await expect(page.getByRole('heading', { name: '字典版本管理' })).toBeVisible()
  await expect(page.getByTestId('dict-version-list')).toBeVisible()
  // 真後端種子：V2 為啟用中版本
  await expect(page.getByTestId('dict-active-card')).toBeVisible()
  // L2：唯一以真 API 進到內容層的路徑 —— 進版本 → 切 G 分頁 → 斷言有選項列
  await page.getByTestId('dict-version-MINIMOST_FACTORY_V2').getByRole('button', { name: '編輯' }).click()
  await expect(page.getByTestId('dict-option-editor')).toBeVisible()
  await page.getByRole('tab', { name: 'G 取得控制' }).click()
  await expect(page.getByTestId('dict-option-g_tap')).toBeVisible()
  await expect(page.locator('[data-testid^="dict-option-g_"]').first()).toBeVisible()
  // A 分頁（帶型）也以真 API 驗一次
  await page.getByRole('tab', { name: 'A 距離' }).click()
  await expect(page.getByTestId('dict-band-editor')).toBeVisible()
  await page.getByRole('button', { name: '← 返回版本列表' }).click()

  // NOTE: SOP 版本 tab has been retired (L-04). Removed from test.
  // NOTE: 主數據 tab has been retired (L-03). Not present in sidebar.

  // 使用者管理 tab
  await page.getByRole('button', { name: /使用者/ }).click()
  await expect(page.getByText(/使用者與角色/)).toBeVisible()
  await expect(page.getByText('IEC141289', { exact: false }).first()).toBeVisible()

  // NOTE: 匯出 tab 已收進分析案件詳情（ADR-021）；目錄 tab 已退場。

  // 主數據管理 tab (admin-gated; seed user IEC141289 is admin) — smoke check (H-01)
  await page.getByRole('button', { name: /主數據管理/ }).click()
  await expect(page.getByRole('heading', { name: '主數據管理' })).toBeVisible()

  // 分析案件 tab — smoke check (G-01)
  await page.getByRole('button', { name: /分析案件/ }).click()
  // Case list renders filter tabs（exact:true 避免匹配到案件列 button 內含「草稿」badge）
  await expect(page.getByRole('button', { name: '全部', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '草稿', exact: true })).toBeVisible()
})

test('header import button leads to the workspace upload (needs an open worksheet)', async ({ page }) => {
  // ADR-038 W5 後（Howard 2026-11-24 選 A）：匯入一律在工作區進編輯區；沒有開啟中的工時表時先提示
  await page.goto('/')
  await page.getByRole('button', { name: /匯入 Excel/ }).click()
  await expect(page.getByText('請先從分析案件開啟工時表')).toBeVisible()
  await expect(page.getByRole('heading', { name: /匯入 Excel/ })).toHaveCount(0)
})

// MOST 工作台（workbench-v3）的冒煙測試隨畫面移除（ADR-038 D4，W6）。
