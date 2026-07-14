import { test, expect } from '@playwright/test'

// 對單一伺服器預覽（preview_server :8099，含真實 DB）跑端對端冒煙。
test('app loads, identity + dashboard cards (ADR-021 default tab)', async ({ page }) => {
  await page.goto('/')
  // App title rendered as <h1> inside the AppLayout header
  await expect(page.getByRole('heading', { name: 'MOST Workbench' })).toBeVisible()
  await expect(page.getByText(/IEC141289/)).toBeVisible()               // 身分（/api/v2/me）
  // Sidebar nav button for MOST 工作台 (workbench-v3, ADR-021)
  await expect(page.getByRole('button', { name: /MOST 工作台/ })).toBeVisible()
  // 預設 tab = 儀表板：三張卡（資料來自真實 DB 種子）
  await expect(page.getByText('Rule-set 總覽')).toBeVisible()
  await expect(page.getByText('案件狀態統計')).toBeVisible()
  await expect(page.getByText('近期案件')).toBeVisible()
})

test('sidebar navigation renders each migrated feature', async ({ page }) => {
  await page.goto('/')

  // Rule-set tab (admin-gated; seed user IEC141289 is admin)
  await page.getByRole('button', { name: /Rule-set/ }).click()
  await expect(page.getByText(/A — 移動距離/)).toBeVisible()

  // NOTE: SOP 版本 tab has been retired (L-04). Removed from test.
  // NOTE: 主數據 tab has been retired (L-03). Not present in sidebar.

  // 使用者管理 tab
  await page.getByRole('button', { name: /使用者/ }).click()
  await expect(page.getByText(/使用者與角色/)).toBeVisible()
  await expect(page.getByText('IEC141289', { exact: false }).first()).toBeVisible()

  // NOTE: 匯出 tab 已收進分析案件詳情（ADR-021）；目錄 tab 已退場。

  // 字典管理 tab (admin-gated; seed user IEC141289 is admin) — smoke check (H-01)
  await page.getByRole('button', { name: /字典管理/ }).click()
  await expect(page.getByRole('heading', { name: '字典管理' })).toBeVisible()

  // 分析案件 tab — smoke check (G-01)
  await page.getByRole('button', { name: /分析案件/ }).click()
  // Case list renders filter tabs（exact:true 避免匹配到案件列 button 內含「草稿」badge）
  await expect(page.getByRole('button', { name: '全部', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '草稿', exact: true })).toBeVisible()
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
  // ACTIVE_WS 初始為空字串（6452dd6）→ 需經「分析案件 → 編輯工時表」設定 activeWs，
  // 這也是 ADR-021 後的真實使用者動線。
  const WS_ID = '55555555-5555-5555-5555-555555555555'
  const MODULE_ID = 'aaaabbbb-cccc-dddd-eeee-ffffgggghhhh'

  // 單一 catch-all 攔截所有 /api/** 請求
  await page.route('/api/**', route => {
    const url = route.request().url()

    // /api/v2/rule-sets/*/options — ActionModuleWorkspace 需要有效 options
    //（回 [] 會使 opts.a_bands.reach 崩潰 → ErrorBoundary 吃掉整頁，tabs 不會渲染）
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 'MINIMOST_FACTORY_V2',
          multiplier: 1,
          a_bands: {
            reach: [{ max_value: 5, index: 2 }],
            twist: [{ max_value: null, index: 0 }],
            foot:  [{ max_value: null, index: 0 }],
          },
          b: [],
          g: [{ code: 'g_simple', label: '簡單抓握', modifier_key: null, requires_modifier: false }],
          p_bases:  [{ code: 'p_put', label: '放置', label_en: 'Put' }],
          p_addons: [],
          m_verbs:  [{ code: 'm_push', label: '推', pricing_kind: 'distance_ladder' }],
          x: [{ code: 'x_none', label: '無機器時間', mode: 'none' }],
          i: [{ code: 'i_none', label: '無', label_en: 'None' }],
        }),
      })
    }

    // /api/v2/me — 身分（AppLayout + RBAC gating）
    if (url.includes('/api/v2/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ employee_no: 'IEC141289', roles: ['analyst'], level: 1 }),
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

    // /api/v2/cases — 分析案件清單（提供「編輯工時表」入口以設定 activeWs = WS_ID）
    if (/\/api\/v2\/cases(\?|$)/.test(url)) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total: 1,
          items: [{
            process_version_id: 'pv-mock-1',
            worksheet_id: WS_ID,
            version_no: '1',
            status: 'draft',
            site_name: 'Site A',
            product_name: 'Product X',
            sku_name: 'SKU 001',
            process_name: '搬取零件站',
            total_tmu: 28,
            created_at: '2026-01-01T00:00:00Z',
            approved_at: null,
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

  // 先經分析案件設定 activeWs（編輯工時表 → setActiveWs(WS_ID) + 切到 wi tab）
  await page.getByRole('button', { name: /分析案件/ }).first().click()
  await page.getByText('搬取零件站').first().click()
  await page.getByRole('button', { name: '編輯工時表' }).click()

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
  // Dialog 顯示 mocked 模組名稱（.first()：WI 選取器清單也含同名項目）
  await expect(page.getByText('搬取零件 WI').first()).toBeVisible()

  // 點擊「取消」→ dialog 關閉
  await page.getByRole('button', { name: '取消' }).click()
  await expect(page.getByRole('heading', { name: '確認發布新版本' })).not.toBeVisible()
})
