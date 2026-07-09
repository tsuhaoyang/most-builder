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

// ── workbench-v3 Tab 3 apply-back UI (F-03b §3) ─────────────────────────────
// 方案 B：用 page.route 攔截所有 /api/** 呼叫，模擬一個帶 source_module_id 的
// worksheet response，觸發「回」badge → ApplyBackDialog 的顯示流程。
//
// 此測試「不依賴 preview_server」：只需靜態資源伺服器（npm run dev 或
// preview_server 的 dist 托管）可訪問；所有 API 均由 page.route 攔截，
// 不對真實後端發出請求。若靜態資源伺服器也未啟動，goto('/') 會 timeout，
// 與現有 smoke test 行為一致（屬預期失敗）。
test('workbench-v3 tab3: ProcessWorkspace 結構與 apply-back dialog（mocked API）', async ({ page }) => {
  const WS_ID = '55555555-5555-5555-5555-555555555555'   // 與 shared/config.ts ACTIVE_WS 一致
  const MODULE_ID = 'aaaabbbb-cccc-dddd-eeee-ffffgggghhhh'

  // 單一 catch-all 攔截所有 /api/** 請求
  await page.route('/api/**', route => {
    const url = route.request().url()

    // /api/v2/me — 身分（AppLayout + RBAC gating）
    if (url.includes('/api/v2/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ employee_no: 'IEC141289', roles: ['IE'], level: 1 }),
      })
    }

    // /api/v2/worksheets/{WS_ID} — 含 source_module_id 的列，觸發「回」badge
    if (url.includes(`/api/v2/worksheets/${WS_ID}`)) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          worksheet_id: WS_ID,
          status: 'active',
          total_tmu: 28,
          rows: [{
            wi_row_id: 'test-row-001',
            seq_no: 1,
            hand: 'BH',
            sub_activity: null,
            object_vocab_id: null,
            from_vocab_id: null,
            to_vocab_id: null,
            tool_vocab_id: null,
            frequency: 1,
            simo_group_id: null,
            source_module_id: MODULE_ID,
            source_module_version: 1,
            cycle: {
              seq_kind: 'GM',
              total_tmu: 28,
              total_seconds: 1.008,
              narrative: '搬取零件',
              slot_inputs: {},
              rule_set_id: 'ruleset-v2',
            },
            level: null,
          }],
        }),
      })
    }

    // /api/v2/motion-modules?category=wi-template — Panel 1 WI 選取器清單
    if (url.includes('/api/v2/motion-modules') && url.includes('wi-template')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{
          id: MODULE_ID,
          name_zh: '搬取零件 WI',
          keywords: [],
          scope: 'shared',
          status: 'active',
          rows: [],
          total_tmu: 28,
        }]),
      })
    }

    // 其餘（products、skus、motion-modules 無 filter、rule-sets、vocab 等）→ 空陣列
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/')

  // 切換到 MOST 工作台 (v3)
  await page.getByRole('button', { name: /MOST 工作台/ }).click()

  // 切換至 Tab 3：製程途程
  await page.getByRole('button', { name: '製程途程' }).click()

  // Panel 1 「WI 選取器」與 Panel 2 「製程大綱」標題必須存在
  await expect(page.getByText('WI 選取器')).toBeVisible()
  await expect(page.getByText('製程大綱')).toBeVisible()

  // 「回」badge 出現（mocked row 具有 source_module_id + source_module_version）
  const applyBackBtn = page.getByRole('button', { name: '回' })
  await expect(applyBackBtn).toBeVisible()

  // 點擊「回」→ ApplyBackDialog 顯示（F-03b §3.3）
  await applyBackBtn.click()
  await expect(page.getByRole('heading', { name: '確認發布新版本' })).toBeVisible()
  // Dialog 顯示 mocked 模組名稱
  await expect(page.getByText('搬取零件 WI')).toBeVisible()

  // 點擊「取消」→ dialog 關閉
  await page.getByRole('button', { name: '取消' }).click()
  await expect(page.getByRole('heading', { name: '確認發布新版本' })).not.toBeVisible()
})
