/**
 * UX Compliance Tests — Type A (Mocked-API)
 *
 * 對應驗收清單：docs/v3/migration-delivery-checklist.md 各節
 * 對應 UX 規格：docs/v3/analysis/UX-design-spec.md
 *
 * 不依賴 preview_server。全部 /api/** 請求由 page.route 攔截。
 * 需要 Vite dev server 在 5173（或 E2E_BASE_URL 指定的 port）。
 *
 * 執行方式：
 *   cd src/frontend
 *   E2E_BASE_URL=http://localhost:5173 npx playwright test ux-compliance.spec.ts --reporter=list
 *
 * DOM 穩定性說明：
 *   React 18 StrictMode 在 dev build 中對每個組件執行 mount→unmount→remount 循環。
 *   在 goto() 後必須等待 waitForLoadState('networkidle')，確保 StrictMode 循環完成後
 *   再執行互動操作；否則 Playwright 的 click/toBeVisible 可能在 unmount phase 執行。
 */
import { test, expect, type Page } from '@playwright/test'

// ─── Mock identity payloads ───────────────────────────────────────────────────

/** admin 身分 (level=3, isAdmin=true, canEdit=true, canPublish=true) */
const ADMIN_ME = { employee_no: 'IEC141289', roles: ['admin'], level: 3 }

/** viewer 身分 (level=0, 無任何 gating 權限) */
const VIEWER_ME = { employee_no: 'TEST_VIEWER', roles: [], level: 0 }

/** approver 身分 (level=2, canPublish=true) */
const APPROVER_ME = { employee_no: 'TEST_APPROVER', roles: ['approver'], level: 2 }

// ─── Minimal valid RuleSetOptions (prevents ActionModuleWorkspace spinner) ────

const MOCK_OPTS = {
  code: 'MINIMOST_FACTORY_V1',
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
}

// ─── Mock case data (G-01) ────────────────────────────────────────────────────

const MOCK_CASES_DRAFT = {
  total: 1,
  items: [{
    process_version_id: 'pv-001',
    worksheet_id:       'ws-001',
    version_no:         '1',
    status:             'draft',
    site_name:          'Site A',
    product_name:       'Product X',
    sku_name:           'SKU 001',
    process_name:       '組裝站作業',
    total_tmu:          28,
    created_at:         '2026-01-01T00:00:00Z',
    approved_at:        null,
  }],
}

const MOCK_CASES_2 = {
  total: 2,
  items: [
    ...MOCK_CASES_DRAFT.items,
    {
      process_version_id: 'pv-002',
      worksheet_id:       'ws-002',
      version_no:         '1',
      status:             'approved',
      site_name:          'Site A',
      product_name:       'Product X',
      sku_name:           'SKU 001',
      process_name:       '壓合站作業',
      total_tmu:          57,
      created_at:         '2026-01-01T00:00:00Z',
      approved_at:        '2026-02-01T00:00:00Z',
    },
  ],
}

const MOCK_AUDIT_LOG = { total: 0, items: [] }

// ─── Vocab items (DictionariesPage) ──────────────────────────────────────────

const MOCK_VOCAB = [
  { id: 'v1', kind: 'object', name_zh: '主板', source_system: 'manual', is_active: true },
  { id: 'v2', kind: 'component', name_zh: 'M4 螺絲', source_system: 'manual', is_active: true },
]

const MOCK_TEMPLATES: unknown[] = []

// ─── Route setup helper ───────────────────────────────────────────────────────
// 所有 /api/** 請求均由此攔截；順序：精確路由優先，最後 catch-all 回傳 []

// 最小有效 Worksheet 物件（WiWorkbench useWorksheet hook 需要 rows 為陣列）
// 注意：useWorksheet(wsId) 無 enabled guard，即使 wsId='' 也會發出請求
// 回傳 [] 會讓 wsData.rows.map() 崩潰，必須回傳帶 rows 欄位的物件
const MOCK_EMPTY_WORKSHEET = {
  worksheet_id: '',
  status: 'active',
  total_tmu: 0,
  rows: [],
}

async function setupRoutes(
  page: Page,
  identity = ADMIN_ME,
  cases: unknown = { total: 0, items: [] },
) {
  await page.route('/api/**', route => {
    const url = route.request().url()

    // Identity
    if (url.includes('/api/v2/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(identity) })
    }

    // Rule-set options (WiWorkbench + ActionModuleWorkspace)
    // 必須在 catch-all 之前處理，否則返回 [] 導致 opts.a_bands.reach crash
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(MOCK_OPTS) })
    }

    // Worksheet by ID — useWorksheet(wsId) 無 enabled guard，wsId='' 也會發請求
    // 必須回傳帶 rows[] 的物件，否則 wsData.rows.map() 崩潰
    // 匹配 /api/v2/worksheets/<id> 但不匹配 /export /rows /publish /retire /versions /clone
    if (url.includes('/api/v2/worksheets/') &&
        !url.includes('/export') && !url.includes('/rows') &&
        !url.includes('/publish') && !url.includes('/retire') &&
        !url.includes('/versions') && !url.includes('/clone')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(MOCK_EMPTY_WORKSHEET) })
    }

    // Cases list
    if (url.match(/\/api\/v2\/cases(\?|$)/)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(cases) })
    }

    // Audit log
    if (url.includes('/api/v2/audit-log')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(MOCK_AUDIT_LOG) })
    }

    // Vocab
    if (url.match(/\/api\/v2\/vocab(\?|$)/)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(MOCK_VOCAB) })
    }

    // Motion modules / motion templates
    if (url.includes('/api/v2/motion-modules') || url.includes('/api/v2/motion-templates')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(MOCK_TEMPLATES) })
    }

    // Everything else (products, skus, skus/<id>/worksheets, etc.) — empty list
    return route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify([]) })
  })
}

// ─── Helper: goto + wait for page to fully settle ────────────────────────────
// React 18 StrictMode 在 dev build 中的 mount-unmount-remount 循環，以及
// React Query 的初始 fetch，都在 networkidle 前完成。
async function gotoAndWait(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
}

// ─── Helper: click a nav button and wait for new content ─────────────────────
async function clickNavAndWait(page: Page, name: RegExp | string) {
  await page.getByRole('button', { name }).first().click()
  // 等待 StrictMode remount 完成，以及新 tab 組件的初始 API 呼叫
  await page.waitForLoadState('networkidle')
}

// ─── § A-01: Sidebar 結構 ─────────────────────────────────────────────────────

test.describe('§A-01 Sidebar 結構 (UX spec §1.1–1.2)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
  })

  test('A-01-1: header 顯示 MOST Workbench 標題 (checklist A-03)', async ({ page }) => {
    await gotoAndWait(page)
    // AppLayout renders <h1 className="...">MOST Workbench</h1>
    await expect(page.getByRole('heading', { name: 'MOST Workbench' })).toBeVisible()
  })

  test('A-01-2: sidebar 背景色為 #304156 (token sidebar-bg, checklist A-03)', async ({ page }) => {
    await gotoAndWait(page)
    // Desktop sidebar has inline style background-color:#304156 (rgb 48,65,86)
    const sidebar = page.locator('.hidden.md\\:flex').first()
    await expect(sidebar).toHaveCSS('background-color', 'rgb(48, 65, 86)')
  })

  test('A-01-3: admin 展開時看到所有導覽項目 (checklist A-01)', async ({ page }) => {
    await gotoAndWait(page)
    // spec §1.2: 儀表板 / MOST 工作台 / WI 專案建立 / Level System / 分析案件 / 字典管理 / 使用者管理
    await expect(page.getByRole('button', { name: /儀表板/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /MOST 工作台/ }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /WI 專案建立/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /Level System/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /分析案件/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /字典管理/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /使用者管理/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /匯出/ })).toBeVisible()
  })

  test('A-01-4: SOP 版本已退役，sidebar 不含「SOP」(checklist L-04)', async ({ page }) => {
    await gotoAndWait(page)
    // SOP was removed from PRIMARY_NAV (SECONDARY_NAV is empty)
    await expect(page.getByRole('button', { name: /SOP/ })).not.toBeVisible()
  })

  test('A-01-5: 主數據已退役，sidebar 不含「主數據」(checklist L-03)', async ({ page }) => {
    await gotoAndWait(page)
    // MasterData.tsx deleted; no '主數據' nav entry
    await expect(page.getByRole('button', { name: /主數據/ })).not.toBeVisible()
  })
})

// ─── § A-02: Sidebar 折疊/展開 ───────────────────────────────────────────────

test.describe('§A-02 Sidebar 折疊/展開 (UX spec §1.1)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
  })

  test('A-02-1: 折疊按鈕存在，點後 aria-label 切換 (checklist A-01)', async ({ page }) => {
    await gotoAndWait(page)
    // Sidebar starts expanded; toggle button shows '«' with aria-label="折疊側欄"
    const collapseBtn = page.getByRole('button', { name: '折疊側欄' })
    await expect(collapseBtn).toBeVisible()
    await collapseBtn.click()
    // After collapse, aria-label becomes "展開側欄"
    await expect(page.getByRole('button', { name: '展開側欄' })).toBeVisible()
  })

  test('A-02-2: 折疊後側欄寬度縮至 56px (checklist A-01)', async ({ page }) => {
    await gotoAndWait(page)
    const desktopSidebar = page.locator('.hidden.md\\:flex').first()
    const expandedWidth = await desktopSidebar.evaluate(
      (el) => (el as HTMLElement).style.width
    )
    expect(expandedWidth).toBe('200px')

    await page.getByRole('button', { name: '折疊側欄' }).click()
    // Wait for CSS transition (0.2s) to complete
    await page.waitForTimeout(300)
    const collapsedWidth = await desktopSidebar.evaluate(
      (el) => (el as HTMLElement).style.width
    )
    expect(collapsedWidth).toBe('56px')
  })
})

// ─── § A-02: 角色可見性 ───────────────────────────────────────────────────────

test.describe('§A-02 角色可見性 (checklist A-02)', () => {
  test('A-02-3: viewer 身分不顯示字典管理/使用者管理', async ({ page }) => {
    await setupRoutes(page, VIEWER_ME)
    await gotoAndWait(page)
    // level=0 → canEdit=false → '字典管理' (minRole:'analyst') hidden
    // level=0 → isAdmin=false → '使用者管理' (minRole:'admin') hidden
    await expect(page.getByRole('button', { name: /字典管理/ })).not.toBeVisible()
    await expect(page.getByRole('button', { name: /使用者管理/ })).not.toBeVisible()
  })

  test('A-02-4: admin 身分顯示字典管理/使用者管理', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    // level=3 → isAdmin=true → both visible
    await expect(page.getByRole('button', { name: /字典管理/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /使用者管理/ })).toBeVisible()
  })
})

// ─── § A-03 視覺 Token 主內容區 ──────────────────────────────────────────────

test.describe('§A-03 視覺 Token 主內容區 (checklist A-03)', () => {
  test('A-03-1: main 內容區底色為 page-bg (#f5f7fa)', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    // AppLayout sets backgroundColor: '#f5f7fa' on <main>
    const main = page.locator('main')
    await expect(main).toHaveCSS('background-color', 'rgb(245, 247, 250)')
  })
})

// ─── § B-01: workbench-v3 佈局 (UX spec §2.1) ────────────────────────────────

test.describe('§B-01 workbench-v3 佈局 (checklist B-01, B-02, B-03)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    // Navigate to MOST 工作台 (workbench-v3) and wait for ActionModuleWorkspace
    await clickNavAndWait(page, /MOST 工作台/)
  })

  test('B-01-1: NlDraftInput 文字輸入框存在 (checklist B-02)', async ({ page }) => {
    // ActionModuleWorkspace renders a textarea for NL draft (B-02 §1)
    await expect(page.getByPlaceholder(/口語描述動作/)).toBeVisible()
  })

  test('B-01-2: Slot Strip（句子型格位列）存在 (checklist B-03)', async ({ page }) => {
    // ActionModuleWorkspace renders the slot inputs inline as "sentence-line" elements.
    // Check for the GM/CM model selector (always present when rule-set loads)
    await expect(page.getByText('一般移動 (GM)')).toBeVisible()
    await expect(page.getByText('控制移動 (CM)')).toBeVisible()
  })

  test('B-01-3: [SPEC GAP] MiCompositionTable 12欄動作清單未出現在 workbench-v3 (checklist C-01)', async ({ page }) => {
    // UX spec §2.4 requires Section 2 with 12-column MiCompositionTable.
    // Current workbench-v3 Tab 1 (ActionModuleWorkspace) has a card-based pool instead.
    // This test documents the gap: the table headers should NOT be found.
    await expect(page.getByText('Base TMU')).not.toBeVisible()
    await expect(page.getByText('Eff TMU')).not.toBeVisible()
  })

  test('B-01-4: TMU 標籤存在 (checklist A-03, C-01)', async ({ page }) => {
    // ActionModuleWorkspace shows TMU label with blue color styling
    await expect(page.getByText('TMU')).toBeVisible()
  })
})

// ─── § C-01: 動作清單 12 欄 (UX spec §2.4) ───────────────────────────────────

test.describe('§C-01 動作清單 12 欄表格結構 (checklist C-01)', () => {
  test('C-01-1: [SPEC GAP] workbench-v3 缺少 12 欄 MiCompositionTable 規格表頭', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    // Navigate to workbench-v3
    await clickNavAndWait(page, /MOST 工作台/)
    // Spec C-01 requires: 拖曳把手 | 勾選 | # | 手 | 動作描述 | Base TMU | 頻率 | Eff TMU | CT(秒) | SIMO | 納入 TMU | 操作
    // Current implementation has card pool, not 12-col table. These headers absent.
    await expect(page.getByText('Base TMU')).not.toBeVisible()
    await expect(page.getByText('Eff TMU')).not.toBeVisible()
    await expect(page.getByText('CT(秒)')).not.toBeVisible()
  })

  test('C-01-2: 舊工作台 (wi tab) 有 #/手/SIMO 欄，但缺少 Base TMU/Eff TMU/CT(秒)', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    // Navigate to old workbench ('工作台 (舊)')
    await clickNavAndWait(page, /工作台.*舊/)
    // Old workbench has partial columns: # / 手 / 敘述 / TMU / 次數 / SIMO
    const tableHead = page.locator('thead')
    // Existing headers
    await expect(tableHead.getByText('#')).toBeVisible()
    await expect(tableHead.getByText('手')).toBeVisible()
    await expect(tableHead.getByText('SIMO')).toBeVisible()
    // MISSING from spec: 'Base TMU', 'Eff TMU', 'CT(秒)', '頻率' as separate columns
    await expect(page.locator('thead').getByText('Base TMU')).not.toBeVisible()
    await expect(page.locator('thead').getByText('Eff TMU')).not.toBeVisible()
    await expect(page.locator('thead').getByText('CT(秒)')).not.toBeVisible()
  })
})

// ─── § E-04/05/06: WI Pool 三層組裝 Tab 結構 ─────────────────────────────────

test.describe('§E-04/05/06 WI Pool 三層 Tab (checklist E-04~E-06)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    await clickNavAndWait(page, /MOST 工作台/)
  })

  test('E-04-1: 三個 Tab 按鈕存在 (實際名稱)', async ({ page }) => {
    // MostWorkbenchV3 renders 3 tabs with these actual labels
    await expect(page.getByRole('button', { name: '動作模組' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'WI 組成' })).toBeVisible()
    await expect(page.getByRole('button', { name: '製程途程' })).toBeVisible()
  })

  test('E-04-2: [SPEC GAP] Tab 名稱缺少「工作區」後綴 (spec 要求「動作模組工作區」等)', async ({ page }) => {
    // UX spec checklist E-04/05/06 requires tab labels ending in 工作區:
    //   「動作模組工作區」「WI 組成工作區」「製程途程工作區」
    // Actual implementation uses shorter names without the 工作區 suffix.
    // The following assertions confirm the spec gap (buttons with 工作區 suffix do NOT exist).
    await expect(page.getByRole('button', { name: '動作模組工作區' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: 'WI 組成工作區' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: '製程途程工作區' })).not.toBeVisible()
  })

  test('E-04-3: 點擊 Tab 1 顯示動作模組編輯器', async ({ page }) => {
    await page.getByRole('button', { name: '動作模組' }).click()
    await expect(page.getByText('動作模組編輯器')).toBeVisible()
  })

  test('E-05-1: 點擊 Tab 2 顯示 WI 組成工作區', async ({ page }) => {
    await page.getByRole('button', { name: 'WI 組成' }).click()
    // WIPoolWorkspace renders headings 'WI 組成器' and 'WI Pool'
    // Use heading role to avoid matching the tab button itself (strict mode)
    await expect(page.getByRole('heading', { name: 'WI Pool' })).toBeVisible()
  })

  test('E-06-1: 點擊 Tab 3 顯示製程大綱', async ({ page }) => {
    await page.getByRole('button', { name: '製程途程' }).click()
    // ProcessWorkspace renders 'WI 選取器' and '製程大綱' panels
    await expect(page.getByText('WI 選取器')).toBeVisible()
    await expect(page.getByText('製程大綱')).toBeVisible()
  })

  test('E-04-4: NL Draft 只出現在 Tab 1，Tab 2/3 不應有 NL Draft (spec E-04 拒絕條件)', async ({ page }) => {
    // Tab 1: NL Draft present
    await page.getByRole('button', { name: '動作模組' }).click()
    await expect(page.getByPlaceholder(/口語描述動作/)).toBeVisible()

    // Tab 2: NL Draft absent
    await page.getByRole('button', { name: 'WI 組成' }).click()
    await expect(page.getByPlaceholder(/口語描述動作/)).not.toBeVisible()

    // Tab 3: NL Draft absent
    await page.getByRole('button', { name: '製程途程' }).click()
    await expect(page.getByPlaceholder(/口語描述動作/)).not.toBeVisible()
  })
})

// ─── § G-01: 分析案件清單 ─────────────────────────────────────────────────────

test.describe('§G-01 分析案件清單 (checklist G-01)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_2)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
  })

  test('G-01-1: 狀態篩選 Tab 存在（全部/草稿/已核准/已退役）', async ({ page }) => {
    // Use exact:true to avoid partial matches: '草稿' ≠ '組裝站作業 草稿 …', '已核准' ≠ '核准'
    await expect(page.getByRole('button', { name: '全部', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '草稿', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '已核准', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '已退役', exact: true })).toBeVisible()
  })

  test('G-01-2: 案件清單顯示 process_name + status badge', async ({ page }) => {
    // MOCK_CASES_2 has '組裝站作業' (draft) and '壓合站作業' (approved)
    await expect(page.getByText('組裝站作業')).toBeVisible()
    await expect(page.getByText('壓合站作業')).toBeVisible()
    // Status badges
    await expect(page.getByText('草稿').first()).toBeVisible()
    await expect(page.getByText('已核准').first()).toBeVisible()
  })

  test('G-01-3: 點選案件後出現右側詳情面板', async ({ page }) => {
    // Click on the first case item
    await page.getByText('組裝站作業').click()
    // Detail panel shows case name as heading and action buttons
    await expect(page.getByRole('heading', { name: '組裝站作業' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下載報表' })).toBeVisible()
    await expect(page.getByRole('button', { name: '開啟工作台' })).toBeVisible()
  })
})

// ─── § G-02: 動作按鈕角色 gating ─────────────────────────────────────────────

test.describe('§G-02 動作按鈕角色 gating (checklist G-01)', () => {
  test('G-02-1: approver + draft → 顯示「核准」按鈕', async ({ page }) => {
    await setupRoutes(page, APPROVER_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    // Click the draft case
    await page.getByText('組裝站作業').click()
    // canApprove = (status==='draft') && canPublish (level>=2) → true
    // exact:true avoids matching '已核准' status-filter tab which contains '核准'
    await expect(page.getByRole('button', { name: '核准', exact: true })).toBeVisible()
  })

  test('G-02-2: viewer + approved → 不顯示「退役」按鈕', async ({ page }) => {
    const approvedCases = {
      total: 1,
      items: [{
        process_version_id: 'pv-002',
        worksheet_id:       'ws-002',
        version_no:         '1',
        status:             'approved',
        site_name:          'Site A',
        product_name:       'Product X',
        sku_name:           'SKU 001',
        process_name:       '壓合站作業',
        total_tmu:          57,
        created_at:         '2026-01-01T00:00:00Z',
        approved_at:        '2026-02-01T00:00:00Z',
      }],
    }
    await setupRoutes(page, VIEWER_ME, approvedCases)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    await page.getByText('壓合站作業').click()
    // canRetire = (status==='approved') && isAdmin (level>=3) → false for viewer
    // exact:true avoids matching '已退役' status-filter tab (which IS visible and contains '退役')
    await expect(page.getByRole('button', { name: '退役', exact: true })).not.toBeVisible()
  })
})

// ─── § H-01: 字典管理頁面 ────────────────────────────────────────────────────

test.describe('§H-01 字典管理頁面 (checklist H-01)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    await clickNavAndWait(page, /字典管理/)
  })

  test('H-01-1: 字典管理頁 heading 存在', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '字典管理' })).toBeVisible()
  })

  test('H-01-2: Tab「詞彙庫」存在並顯示詞彙列表', async ({ page }) => {
    // DictionariesPage renders '詞彙庫' as the first tab (default active)
    const vocabTab = page.getByRole('button', { name: '詞彙庫' })
    await expect(vocabTab).toBeVisible()
    // VocabTab renders when active; mock has 2 items
    await expect(page.getByText('主板')).toBeVisible()
    await expect(page.getByText('M4 螺絲')).toBeVisible()
  })

  test('H-01-3: Tab「動作模組範本」存在且可切換', async ({ page }) => {
    const templatesTab = page.getByRole('button', { name: '動作模組範本' })
    await expect(templatesTab).toBeVisible()
    await templatesTab.click()
    // TemplatesTab renders with empty list message
    await expect(page.getByText(/無符合條件的範本/)).toBeVisible()
  })
})

// ─── § I-01: RBAC viewer 看不到字典管理 ────────────────────────────────────────

test.describe('§I-01 RBAC viewer 無字典管理入口 (checklist I-01, A-02)', () => {
  test('I-01-1: viewer 身分 sidebar 無字典管理 button', async ({ page }) => {
    await setupRoutes(page, VIEWER_ME)
    await gotoAndWait(page)
    // level=0 → canEdit=false → minRole:'analyst' item hidden
    await expect(page.getByRole('button', { name: /字典管理/ })).not.toBeVisible()
  })
})

// ─── § L-03/L-04: 退役確認 ────────────────────────────────────────────────────

test.describe('§L 退役確認 (checklist L-03, L-04)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
  })

  test('L-03: 主數據（MasterData）tab 已退役，sidebar 無入口', async ({ page }) => {
    // MasterData.tsx deleted; no nav item '主數據' in PRIMARY_NAV
    await expect(page.getByRole('button', { name: /主數據/ })).not.toBeVisible()
  })

  test('L-04: SOP 版本 tab 已退役，sidebar 無入口', async ({ page }) => {
    // SECONDARY_NAV is empty; SOP removed from PRIMARY_NAV
    await expect(page.getByRole('button', { name: /SOP/ })).not.toBeVisible()
  })
})
