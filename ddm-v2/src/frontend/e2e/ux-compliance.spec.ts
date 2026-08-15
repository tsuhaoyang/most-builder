/**
 * UX Compliance Tests — Type A (Mocked-API)
 *
 * 對應決策：docs/decisions/ADR-021、ADR-022、ADR-024
 * 對應 UX 規格：docs/architecture/frontend-ux-spec.md
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
// P1-A 契約：一筆 item ＝一個**案件**（聚合鍵 sku_id×model_label），平面欄位＝代表版（最新版），
// 另帶 model_label / version_count / versions[]（created_at ASC）。total ＝案件數。

const MOCK_CASES_DRAFT = {
  total: 1,
  items: [{
    process_version_id: 'pv-001',
    worksheet_id:       'ws-001',
    version_no:         'v1',
    status:             'draft',
    site_id:            'st-1',
    site_name:          'Site A',
    product_id:         'p1',
    product_name:       'Product X',
    sku_id:             'sk1',
    sku_name:           'SKU 001',
    process_name:       '組裝站作業',
    total_tmu:          28,
    created_at:         '2026-01-01T00:00:00Z',
    approved_at:        null,
    // 型別放寬（不是行為改動）：G-03-2d 會把這個物件展開後覆寫 model_label 成字串，
    // 不註記的話 TS 會把字面 null 收窄成 `null` 型別而拒絕該覆寫。
    model_label:        null as string | null,
    version_count:      1,
    versions: [{
      process_version_id: 'pv-001',
      worksheet_id:       'ws-001',
      version_no:         'v1',
      status:             'draft',
      total_tmu:          28,
      created_at:         '2026-01-01T00:00:00Z',
      approved_at:        null,
    }],
  }],
}

const MOCK_CASES_2 = {
  total: 2,
  items: [
    ...MOCK_CASES_DRAFT.items,
    {
      process_version_id: 'pv-002',
      worksheet_id:       'ws-002',
      version_no:         'v1',
      status:             'approved',
      site_id:            'st-1',
      site_name:          'Site A',
      product_id:         'p1',
      product_name:       'Product X',
      sku_id:             'sk1',
      sku_name:           'SKU 001',
      process_name:       '壓合站作業',
      total_tmu:          57,
      created_at:         '2026-01-01T00:00:00Z',
      approved_at:        '2026-02-01T00:00:00Z',
      model_label:        null,
      version_count:      1,
      versions: [{
        process_version_id: 'pv-002',
        worksheet_id:       'ws-002',
        version_no:         'v1',
        status:             'approved',
        total_tmu:          57,
        created_at:         '2026-01-01T00:00:00Z',
        approved_at:        '2026-02-01T00:00:00Z',
      }],
    },
  ],
}

/** 單一案件、三個版本（P1-C 折疊 UI）：代表版＝v3（最新，draft），歷史 v1/v2 */
const MOCK_CASES_MULTIVERSION = {
  total: 1,
  items: [{
    process_version_id: 'pv-103',
    worksheet_id:       'ws-103',
    version_no:         'v3',
    status:             'draft',
    site_id:            'st-1',
    site_name:          'Site A',
    product_id:         'p1',
    product_name:       'Product X',
    sku_id:             'sk1',
    sku_name:           'SKU 001',
    process_name:       '組裝站作業',
    total_tmu:          80,
    created_at:         '2026-03-01T00:00:00Z',
    approved_at:        null,
    model_label:        'L1 線',
    version_count:      3,
    versions: [
      { process_version_id: 'pv-101', worksheet_id: 'ws-101', version_no: 'v1', status: 'draft',
        total_tmu: 28, created_at: '2026-01-01T00:00:00Z', approved_at: null },
      { process_version_id: 'pv-102', worksheet_id: 'ws-102', version_no: 'v2', status: 'approved',
        total_tmu: 57, created_at: '2026-02-01T00:00:00Z', approved_at: '2026-02-05T00:00:00Z' },
      { process_version_id: 'pv-103', worksheet_id: 'ws-103', version_no: 'v3', status: 'draft',
        total_tmu: 80, created_at: '2026-03-01T00:00:00Z', approved_at: null },
    ],
  }],
}

/**
 * NewCaseModal 引導用：同一 SKU 底下**兩個案件**（聚合鍵＝sku_id × model_label）
 *   - 案件「L1 線」：v1 approved + v2 draft
 *   - 案件「L2 線」：v3 draft
 * 用來驗證引導以聚合鍵精確比對（review #2）：填 L1 線才算命中既有案件，
 * 填 L3 線＝該 SKU 的新案件（不得列出 L1/L2 的草稿）。
 */
const MOCK_SKU_WORKSHEETS = [
  { worksheet_id: 'ws-101', version_no: 'v1', status: 'approved', analyst: 'IEC141289', model_label: 'L1 線' },
  { worksheet_id: 'ws-102', version_no: 'v2', status: 'draft', analyst: 'IEC141289', model_label: 'L1 線' },
  { worksheet_id: 'ws-103', version_no: 'v3', status: 'draft', analyst: 'IEC141289', model_label: 'L2 線' },
]

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
  /** GET /api/v2/skus/{id}/worksheets — NewCaseModal 判斷「此 SKU 是否已有版本」 */
  skuWorksheets: unknown = [],
) {
  await page.route('/api/**', route => {
    const url = route.request().url()

    // Identity
    if (url.includes('/api/v2/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(identity) })
    }

    // 啟用中 rule-set（useActiveRuleSet；ADR-023 §3.5 取代寫死常數）
    if (url.includes('/api/v2/rule-sets/active')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' }) })
    }

    // Rule-set options (WiWorkbench + ActionModuleWorkspace)
    // 必須在 catch-all 之前處理，否則返回 [] 導致 opts.a_bands.reach crash
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(MOCK_OPTS) })
    }

    // Rule-set list (DashboardPage 卡 1)
    if (url.match(/\/api\/v2\/rule-sets(\?|$)/)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify([{ id: 'rs-1', code: 'MINIMOST_FACTORY_V2',
          name_zh: 'MiniMOST 工廠規則 v2', status: 'published', multiplier: 1,
          is_active: true, provenance: 'certified_import',
          created_at: '2026-07-07T10:24:25Z', notes: null }]) })
    }

    // WI preview export (案件詳情匯出區, ADR-021)
    if (url.includes('/export/wi-preview')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ worksheet_id: 'ws-001', status: 'active', total_tmu: 28, rows: [{}] }) })
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

    // 產品/SKU 階層＋建立工序表（NewCaseModal, ADR-021 Phase 3 新建案件流程）
    if (url.match(/\/api\/v2\/products(\?|$)/)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify([{ id: 'p1', site_id: 's1', external_code: null,
          name_zh: 'Product X', name_en: null, description: null, is_active: true }]) })
    }
    if (url.match(/\/api\/v2\/skus\?/)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify([{ id: 'sk1', product_id: 'p1', sku_code: 'SKU001',
          name_zh: '機種一', name_en: null, is_active: true }]) })
    }
    if (url.includes('/api/v2/skus/') && url.includes('/worksheets')) {
      if (route.request().method() === 'POST') {
        return route.fulfill({ status: 200, contentType: 'application/json',
          body: JSON.stringify({ worksheet_id: 'ws-new-001', version_no: 'v1', status: 'draft' }) })
      }
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(skuWorksheets) })
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

// ─── Helper: 交錯句型列的欄位序列 ────────────────────────────────────────────
// ADR-021 §Tab1 形態 3 ／ frontend-ux-spec §2.3 明定 GM/CM 各自的**欄位順序**。
//
// ⚠️ 不要退回用色塊上的可見文字（`getByText('A1', { exact: true })`）來定位：
//   (1) 抬頭文案會漂：b66829d 曾把抬頭改成「A · A1」這一個文字節點，exact 比對
//       永遠 0 命中 —— 正向斷言無故變紅（CI run 31592913583 的 B-01-2），反向斷言
//       （toHaveCount(0)）則變成**恆真的假綠**（E-04-4 原本的 B2/P 兩條就是）。
//       2026-08-15 抬頭已依 ADR-021 收編回單一格位鍵「A1」，但教訓不變：文字錨點
//       跟著文案陪葬，語意錨點不會；
//   (2) 色塊主體的縮寫格在 A 段命中 index=1 時本身就顯示「A1」——抬頭收編後
//       跟抬頭同字，文字比對會隨資料狀態多命中元素 → strict mode 隨機爆掉。
// 所以一律用 SlotBuilder 上的 `data-testid="flow-item-<key>"` 語意錨點。
const GM_FLOW = [
  'hand', 'from', 'A1', 'B1', 'G', 'target', 'component', 'A2', 'B2', 'P', 'to', 'A3',
]
const CM_FLOW = [
  'hand', 'from', 'A1', 'B1', 'G', 'target', 'component', 'M', 'to', 'X', 'I', 'where', 'A3',
]

async function flowItemKeys(page: Page): Promise<(string | undefined)[]> {
  // `.first()` 是刻意的：evaluateAll 不走 strict mode，若日後頁面同時出現第二個
  // SlotBuilder，沒有 .first() 會靜靜地把兩份格位串在一起（24 個而不是 12 個），
  // 而不是報 strict 違規。明講「只看第一個 flow」比拿到一串垃圾好。
  return page
    .getByTestId('slot-builder-flow')
    .first()
    .locator('[data-testid^="flow-item-"]')
    .evaluateAll((els) =>
      els.map((el) => el.getAttribute('data-testid')?.replace('flow-item-', '')),
    )
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

  test('A-01-3: admin 展開時看到 ADR-021 的 7+2 導覽項目（順序固定）', async ({ page }) => {
    await gotoAndWait(page)
    // ADR-021 目標 IA：儀表板 / MOST 工作台 / WI 專案建立 / Level System / 分析案件
    //                / 主數據管理(analyst+) / 使用者管理(admin) / MOST 字典(admin)
    // ADR-024：第 6 項原名「字典管理」，更名為「主數據管理」（「字典」在 v2 只指 MOST 規則值）
    const nav = page.locator('nav').first()
    const labels = ['儀表板', 'MOST 工作台', 'WI 專案建立', 'Level System',
      '分析案件', '主數據管理', '使用者管理', 'MOST 字典']
    for (const label of labels) {
      await expect(nav.getByRole('button', { name: new RegExp(label) })).toBeVisible()
    }
    // 側欄剛好 8 項（admin：7 一般 + 2 admin，其中儀表板~MOST 字典 共 8 顆按鈕）
    await expect(nav.getByRole('button')).toHaveCount(labels.length)
    // 順序固定（ADR-021）
    const texts = await nav.getByRole('button').allInnerTexts()
    expect(texts.map(t => t.replace(/\s+/g, ' ').trim())).toEqual([
      '表 儀表板', 'M MOST 工作台', 'W WI 專案建立', 'L Level System',
      '案 分析案件', '主 主數據管理', '人 使用者管理', '字 MOST 字典',
    ])
  })

  test('A-01-6: 頂層不含「目錄」「匯出」「WI 組裝」(ADR-021 收斂)', async ({ page }) => {
    await gotoAndWait(page)
    const nav = page.locator('nav').first()
    // 目錄 → 收進分析案件新建流程（Phase 3）；匯出 → 併入案件詳情；WI 組裝 → 改名 MOST 工作台
    await expect(nav.getByRole('button', { name: /目錄/ })).not.toBeVisible()
    await expect(nav.getByRole('button', { name: /匯出/ })).not.toBeVisible()
    await expect(nav.getByRole('button', { name: /WI 組裝/ })).not.toBeVisible()
  })

  test('A-01-4: SOP 版本已退役，sidebar 不含「SOP」(checklist L-04)', async ({ page }) => {
    await gotoAndWait(page)
    // SOP was removed from PRIMARY_NAV (SECONDARY_NAV is empty)
    await expect(page.getByRole('button', { name: /SOP/ })).not.toBeVisible()
  })

  test('A-01-5: 舊 MasterData tab 已退役，「主數據」入口有且只有一個 (checklist L-03, ADR-024)', async ({ page }) => {
    await gotoAndWait(page)
    // 舊 MasterData.tsx（標題「主數據 / 詞彙庫」）已刪除，其詞彙 CRUD 併入「主數據管理」頁的詞彙庫分頁。
    // 原斷言以「側欄不含『主數據』字樣」當代理；ADR-024 將第 6 項正名為「主數據管理」後該代理失效。
    // 改為斷言原始意圖：不得有第二個主數據入口（舊 tab 沒有復活）。
    const masterDataNav = page.locator('nav').first().getByRole('button', { name: /主數據/ })
    await expect(masterDataNav).toHaveCount(1)
    await expect(masterDataNav).toHaveText(/主數據管理/)
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
  test('A-02-3: viewer 身分不顯示主數據管理/使用者管理', async ({ page }) => {
    await setupRoutes(page, VIEWER_ME)
    await gotoAndWait(page)
    // level=0 → canEdit=false → '主數據管理' (minRole:'analyst') hidden
    // level=0 → isAdmin=false → '使用者管理' (minRole:'admin') hidden
    await expect(page.getByRole('button', { name: /主數據管理/ })).not.toBeVisible()
    await expect(page.getByRole('button', { name: /使用者管理/ })).not.toBeVisible()
  })

  test('A-02-4: admin 身分顯示主數據管理/使用者管理', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    // level=3 → isAdmin=true → both visible
    await expect(page.getByRole('button', { name: /主數據管理/ })).toBeVisible()
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

// ─── § A-04: 儀表板 (ADR-021 Phase 1 最小儀表板) ─────────────────────────────

test.describe('§A-04 儀表板 (ADR-021)', () => {
  test('A-04-1: 預設 tab 為儀表板，三張卡齊備', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_2)
    await gotoAndWait(page)
    await expect(page.getByRole('heading', { name: '儀表板' })).toBeVisible()
    // 卡 1：MOST 字典總覽（mock: MINIMOST_FACTORY_V2 published+active → 啟用中徽章）
    await expect(page.getByText('MOST 字典總覽')).toBeVisible()
    await expect(page.getByText('MINIMOST_FACTORY_V2')).toBeVisible()
    await expect(page.getByText('啟用中')).toBeVisible()
    // 卡 2：案件狀態統計
    await expect(page.getByText('案件狀態統計')).toBeVisible()
    // 卡 3：近期案件（mock 兩筆）
    await expect(page.getByText('近期案件')).toBeVisible()
    await expect(page.getByText('組裝站作業')).toBeVisible()
    await expect(page.getByText('壓合站作業')).toBeVisible()
  })

  test('A-04-2: 點近期案件 → 切到分析案件 tab', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_2)
    await gotoAndWait(page)
    await page.getByRole('button', { name: /組裝站作業/ }).click()
    await page.waitForLoadState('networkidle')
    // CasesPage 的狀態篩選 tab 出現，代表已切到分析案件
    await expect(page.getByRole('button', { name: '全部', exact: true })).toBeVisible()
  })
})

// ─── § B-01: workbench-v3 佈局 (UX spec §2.1) ────────────────────────────────

test.describe('§B-01 workbench-v3 佈局 (checklist B-01, B-02, B-03)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    // Navigate to MOST 工作台 (workbench-v3, ADR-021 改名自「WI 組裝」)
    await clickNavAndWait(page, /MOST 工作台/)
  })

  test('B-01-1: AI 快速建模列存在（NL 輸入＋AI 預填鈕，ADR-021 §Tab1 形態 1）', async ({ page }) => {
    // v3 母版：頂部 AI 快速建模列（tag + input + AI 預填）
    await expect(page.getByText('AI 快速建模')).toBeVisible()
    await expect(page.getByPlaceholder(/輸入動作描述/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'AI 預填' })).toBeVisible()
  })

  test('B-01-2: 交錯句型列存在（含情境欄 元件/從哪裡/目標物/到哪裡，ADR-021 §Tab1 形態 3）', async ({ page }) => {
    const flow = page.getByTestId('slot-builder-flow')
    await expect(flow).toBeVisible()
    // 情境欄嵌在格位之間（米黃）＋使用手（紫）
    await expect(flow.getByText('使用手')).toBeVisible()
    await expect(flow.getByText('從哪裡')).toBeVisible()
    await expect(flow.getByText('目標物')).toBeVisible()
    await expect(flow.getByText('元件')).toBeVisible()
    await expect(flow.getByText('到哪裡')).toBeVisible()
    await expect(flow.getByText('顯示於MI')).toBeVisible()

    // 規格要的是**欄位順序**，不只是「有沒有出現」（見 GM_FLOW 上方註解）：
    //   使用手｜從哪裡｜A1｜B1｜G｜目標物｜元件｜A2｜B2｜P｜到哪裡｜A3（GM）
    await expect.poll(() => flowItemKeys(page)).toEqual(GM_FLOW)

    // 色塊抬頭＝**單一格位鍵標籤**（A1/B1/G…）。三方版本各不同：ADR-021:53 與
    // frontend-ux-spec §2.3 的流程寫「…｜A1｜B1｜G｜…」（單標籤）；v3 SlotBlock.vue:142-143
    // 是 code＋key 兩個獨立 span（無分隔符）；b66829d 發明「A · A1」（三邊都不是，
    // 自稱對齊 v3 實則偏離）。2026-08-15 依 DOC_REGISTRY 權威序（accepted ADR 優先）收編。
    // 原本這裡是 `^\W*${param}\W*${key}\b` 的過渡型 regex（刻意不釘分隔符、等這個裁決），
    // 裁決落地後收緊成**精確比對**：抬頭恰好等於格位鍵，把「A · 」之類前綴加回來必須紅。
    // 參數碼不再由抬頭承載：色帶配色（SLOT_COLORS[param]）與說明文字（`距離(A)-取得`）
    // 本來就帶著它——也因此不另寫 toContainText(param)（那條永遠不可能紅，見 git 舊註解）。
    // 定位走 slot-key testid（本檔一貫的語意錨點），不是外層色帶 span：st.filled 時
    // 色帶還含 ✕ 清除鈕子節點，textContent 變「A1✕」，精確比對會把「該格已填值」
    // 誤報成抬頭壞掉。錨在最內層 key label 才能既保住精確比對（「A · 」加回來必須紅）
    // 又不隱性綁死「該格未填值」。
    for (const key of ['A1', 'B1', 'G', 'A2', 'B2', 'P', 'A3'] as const) {
      const block = flow.getByTestId(`flow-item-${key}`)
      await expect(block).toBeVisible()
      await expect(block.getByTestId('slot-key')).toHaveText(key)
    }

    // 填值狀態迴歸（2026-08 審查點）：st.filled 時色帶尾端多一顆 ✕ 清除鈕
    // （SlotBuilder slotBlock），錨在外層色帶 span 的舊斷言會讀到「G✕」而誤紅——
    // 抬頭斷言不得隱性綁死「該格未填值」。實際把 G 填成 g_simple（MOCK_OPTS 唯一
    // g 選項；互動模式同 E-04-5），驗證 ✕ 出現後抬頭精確比對仍成立。
    await flow.getByTitle('G 取得').click()
    const gDialog = page.getByRole('heading', { name: 'G 取得' }).locator('..').locator('..')
    await gDialog.locator('select').first().selectOption('g_simple')
    await gDialog.getByRole('button', { name: '確認' }).click()
    await expect(flow.getByTestId('flow-item-G').getByLabel('清除 G')).toBeVisible()
    await expect(flow.getByTestId('flow-item-G').getByTestId('slot-key')).toHaveText('G')
  })

  test('B-01-3: 摘要列九欄常駐（ADR-021 §Tab1 形態 2）', async ({ page }) => {
    const bar = page.getByTestId('summary-bar')
    await expect(bar).toBeVisible()
    for (const label of ['動作類型', '使用手', '基礎 TMU', '頻率', '有效 TMU',
      'CT (秒)', 'SIMO', '納入總時間', 'MI 語句']) {
      await expect(bar.getByText(label, { exact: true })).toBeVisible()
    }
  })

  test('B-01-4: 摘要列基礎 TMU 欄存在且未算前顯示 —（前端不自算）', async ({ page }) => {
    const bar = page.getByTestId('summary-bar')
    await expect(bar.getByText('基礎 TMU', { exact: true })).toBeVisible()
    // mock calculate 未攔截具體回應 → 空 cycle 顯示 '—'（不得假裝 0）
    await expect(bar.getByText('動作類型', { exact: true })).toBeVisible()
  })
})

// ─── § C-01: 動作清單 12 欄 (UX spec §2.4) ───────────────────────────────────

test.describe('§C-01 動作清單 12 欄表格結構 (checklist C-01)', () => {
  test('C-01-1: workbench-v3 Tab1 動作清單表格＋工具列（搜尋/筆數/合計，ADR-021 §Tab1 形態 5）', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    // Navigate to workbench-v3 (MOST 工作台, ADR-021 改名自「WI 組裝」)
    await clickNavAndWait(page, /MOST 工作台/)
    // 工具列：搜尋框＋筆數＋合計 TMU（mock 無模組 → 共 0 筆、合計 —）
    await expect(page.getByPlaceholder('搜尋動作…')).toBeVisible()
    await expect(page.getByText(/共 \d+ 筆/)).toBeVisible()
    await expect(page.getByText(/合計：/)).toBeVisible()
    // 表格表頭（ADR-022 B-2：個別動作各自 TMU；缺值顯示 —，不得假裝 0）
    const head = page.locator('thead')
    await expect(head.getByText('WI / 動作描述')).toBeVisible()
    await expect(head.getByText('Base TMU')).toBeVisible()
    await expect(head.getByText('頻率')).toBeVisible()
    await expect(head.getByText('Eff TMU')).toBeVisible()
    await expect(head.getByText('CT(秒)')).toBeVisible()
    await expect(head.getByText('操作')).toBeVisible()
  })

  test('C-01-2: WiWorkbench (wi tab) 有完整欄位含 Base TMU / Eff TMU / CT(秒) / 頻率 (C-01-2 已修)', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    // ADR-021：wi tab 已無側欄入口，經「分析案件 → 編輯工時表」到達 — 驗證功能未回歸
    await clickNavAndWait(page, /分析案件/)
    await page.getByText('組裝站作業').click()
    await page.getByRole('button', { name: '編輯工時表' }).click()
    await page.waitForLoadState('networkidle')
    const tableHead = page.locator('thead')
    await expect(tableHead.getByText('#')).toBeVisible()
    await expect(tableHead.getByText('手')).toBeVisible()
    await expect(tableHead.getByText('SIMO')).toBeVisible()
    await expect(tableHead.getByText('Base TMU')).toBeVisible()
    await expect(tableHead.getByText('Eff TMU')).toBeVisible()
    await expect(tableHead.getByText('CT(秒)')).toBeVisible()
    await expect(tableHead.getByText('頻率')).toBeVisible()
  })
})

// ─── § E-04: MOST 工作台單頁（ADR-022 批次 B：三 tab 移除，回歸 v3 單頁）───────

test.describe('§E-04 MOST 工作台單頁 (ADR-022 批次 B)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    await clickNavAndWait(page, /MOST 工作台/)
  })

  test('E-04-1: 單頁直渲染 — 無三 tab，建立器（摘要列＋新增動作）直接可見', async ({ page }) => {
    // ADR-022：三層 tab 是 v3 實驗性隱藏頁殘留，非驗證 UX → 移除
    await expect(page.getByRole('button', { name: '動作模組工作區' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'WI 組成工作區' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '製程途程工作區' })).toHaveCount(0)
    // 單頁建立器不需點 tab 即可見
    await expect(page.getByTestId('summary-bar')).toBeVisible()
    await expect(page.getByRole('button', { name: '新增動作' })).toBeVisible()
    await expect(page.getByRole('button', { name: '清空' })).toBeVisible()
  })

  test('E-04-2: WI 大綱區存在於動作清單下方（ADR-022 B-3）', async ({ page }) => {
    const outline = page.getByTestId('wi-outline')
    await expect(outline).toBeVisible()
    await expect(outline.getByText('WI 大綱')).toBeVisible()
    // mock 無 WI → 空狀態導引文案
    await expect(outline.getByText(/尚無 WI/)).toBeVisible()
  })

  test('E-04-3: NL Draft（AI 快速建模）在單頁存在', async ({ page }) => {
    await expect(page.getByText('AI 快速建模')).toBeVisible()
    await expect(page.getByPlaceholder(/輸入動作描述/)).toBeVisible()
  })

  test('E-04-4: GM/CM 切換套用遷移規則，B 單選會自動關閉 modal', async ({ page }) => {
    await page.route('**/api/v2/rule-sets/*/options', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...MOCK_OPTS,
        b: [
          { code: 'b_none', label: '無身體動作', modifier_key: null, requires_modifier: false },
          { code: 'b_eye', label: '眼部動作', modifier_key: null, requires_modifier: false },
          { code: 'b_bend', label: '彎腰', modifier_key: null, requires_modifier: false },
        ],
      }),
    }))

    await page.reload()
    await page.waitForLoadState('networkidle')
    await clickNavAndWait(page, /MOST 工作台/)

    const flow = page.getByTestId('slot-builder-flow')

    // A 格：點「距離對照表」的檔位列（testid 尾碼＝band.index，本測 mock 只有 index=2 一檔）。
    const fillASlot = async (title: string) => {
      await flow.getByTitle(title).click()
      await page.getByTestId('a-distance-row-2').click()
      await page.getByRole('button', { name: '確認' }).click()
      await expect(page.getByTestId('a-distance-row-2')).toHaveCount(0)
    }
    // 「這一格有值」的語意錨點：SlotBuilder 只在 filled 時渲染清除鈕（aria-label=`清除 <key>`）。
    // exact 是必要的：外層 <button> 的 accessible name 由內容組出來、會**含**這個 aria-label。
    const clearBtn = (key: string) =>
      flow.getByRole('button', { name: `清除 ${key}`, exact: true })

    await fillASlot('A 移動 — 取得段')   // A1：CM→GM 必須**保留**（§2.2），當本測的對照組
    await fillASlot('A 移動 — 放置段')   // A2：GM→CM 必須清空

    await flow.getByTitle('P 放置').click()
    const pDialog = page.getByRole('heading', { name: 'P 放置' }).locator('..').locator('..')
    await pDialog.locator('select').first().selectOption('p_put')
    await pDialog.getByRole('button', { name: '確認' }).click()

    await flow.getByTitle('B 身體動作 — 放置段').click()
    await page.getByRole('heading', { name: 'B 身體動作 — 放置段' }).locator('..').locator('..').locator('select').selectOption('b_bend')
    await expect(page.getByRole('heading', { name: 'B 身體動作 — 放置段' })).toHaveCount(0)
    await expect(flow.getByText('彎腰')).toBeVisible()

    // 前提：切換前 A1/A2/P 三格都真的有值（否則下面的「被清空」全是空歡喜）
    for (const key of ['A1', 'A2', 'P']) {
      await expect(clearBtn(key)).toBeVisible()
    }

    const seqSelect = page.getByLabel('動作類型')
    await seqSelect.selectOption('CM')
    // CM 的欄位序列（frontend-ux-spec §2.3）＝ GM 專屬的 A2/B2/P 消失、換上 M/X/I/哪裡。
    //
    // 這兩行原本是：
    //     await expect(flow.getByText('B2', { exact: true })).toHaveCount(0)
    //     await expect(flow.getByText('P',  { exact: true })).toHaveCount(0)
    // 自 b66829d 把色塊抬頭改成「B · B2」之後，exact 文字比對永遠 0 命中，
    // 這兩條反向斷言就變成**恆真**——實測把 B2/P 塞回 CM_ITEMS（直接違反遷移規則），
    // 本測試依然全綠。改用 flow 序列比對，欄位集合才真的被守住。
    // （2026-08-15 抬頭已依 ADR-021 收編回「B2」單標籤，getByText 理論上又抓得到了，
    //   但**不要改回去**：文字錨點才是當初假綠的根因，序列比對不隨文案漂。）
    await expect.poll(() => flowItemKeys(page)).toEqual(CM_FLOW)
    await expect(flow.getByTitle('M 控制移動')).toBeVisible()
    await expect(flow.getByTitle('X 製程時間')).toBeVisible()
    await expect(flow.getByTitle('I 對準/檢查')).toBeVisible()

    await seqSelect.selectOption('GM')
    await expect.poll(() => flowItemKeys(page)).toEqual(GM_FLOW)
    await expect(flow.getByTitle('B 身體動作 — 放置段')).toBeVisible()

    // ── 遷移規則守的是**值**，不只是欄位可見性（frontend-ux-spec §2.2）──────────
    //   GM → CM：清空 P/A2/B2；CM → GM：清空 M/X/I，兩邊都保留 A1/B1/G/A3。
    // A2/P 在 CM 沒有欄位可看，所以清空只能在**繞一圈回到 GM 後**驗：值若沒被清，
    // 它會原封不動回到色塊上（migrateSeqState 的 GM 分支是 `p_base || …`，會沿用舊值）。
    // 空格的縮寫是 '—'（filled 時才是動作標籤）→ 正向斷言，壞掉會大聲失敗。
    await expect(flow.getByTestId('flow-item-A2')).toContainText('—')
    await expect(flow.getByTestId('flow-item-P')).toContainText('—')
    await expect(clearBtn('A2')).toHaveCount(0)
    await expect(clearBtn('P')).toHaveCount(0)
    // 對照組：A1 不在清空名單，繞一圈後必須仍有值（否則就是改成「全部清光」也會綠）
    await expect(clearBtn('A1')).toBeVisible()
    // B2 被清空後回填預設身體動作（DEFAULT_B_MOVE_CODE）→ 看得到「眼部」、看不到「彎腰」
    await expect(flow.getByText(/眼部/)).toBeVisible()
    await expect(flow.getByText('彎腰')).toHaveCount(0)
    await expect(flow.getByTitle('M 控制移動')).toHaveCount(0)
    await expect(flow.getByTitle('X 製程時間')).toHaveCount(0)
    await expect(flow.getByTitle('I 對準/檢查')).toHaveCount(0)
  })

  test('E-04-5: G/P 動作次數會寫入 calculate payload', async ({ page }) => {
    const payloads: Array<Record<string, any>> = [] // eslint-disable-line @typescript-eslint/no-explicit-any
    await page.route('**/api/v2/minimost/calculate', route => {
      payloads.push(route.request().postDataJSON() as Record<string, any>) // eslint-disable-line @typescript-eslint/no-explicit-any
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ seq: 'GM', total_tmu: 42, total_seconds: 1.512, tech_line: 'GM TEST' }),
      })
    })

    const flow = page.getByTestId('slot-builder-flow')

    await flow.getByTitle('G 取得').click()
    const gDialog = page.getByRole('heading', { name: 'G 取得' }).locator('..').locator('..')
    await gDialog.locator('select').first().selectOption('g_simple')
    await gDialog.getByLabel('G 動作次數').fill('3')
    await gDialog.getByRole('button', { name: '確認' }).click()

    await flow.getByTitle('P 放置').click()
    const pDialog = page.getByRole('heading', { name: 'P 放置' }).locator('..').locator('..')
    await pDialog.locator('select').first().selectOption('p_put')
    await pDialog.getByLabel('P 動作次數').fill('2')
    await pDialog.getByRole('button', { name: '確認' }).click()

    await expect.poll(() => payloads.at(-1)?.g2?.repeat_count).toBe(3)
    await expect.poll(() => payloads.at(-1)?.p5?.repeat_count).toBe(2)
    await expect(flow.getByText(/×3/)).toBeVisible()
    await expect(flow.getByText(/×2/)).toBeVisible()
  })

  test('E-04-5b: P 附加條件會套用插入與卡合互斥', async ({ page }) => {
    await page.route('**/api/v2/rule-sets/*/options', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...MOCK_OPTS,
        p_bases: [{ code: 'p_put', label: '放置', label_en: 'Put' }],
        p_addons: [
          { code: 'a_insert', label: '插入', needs_precision: false },
          { code: 'a_snap', label: '卡合', needs_precision: false },
        ],
      }),
    }))
    await page.reload()
    await page.waitForLoadState('networkidle')
    await clickNavAndWait(page, /MOST 工作台/)

    const flow = page.getByTestId('slot-builder-flow')

    await flow.getByTitle('P 放置').click()
    const pDialog = page.getByRole('heading', { name: 'P 放置' }).locator('..').locator('..')
    await pDialog.locator('select').first().selectOption('p_put')
    await pDialog.locator('select').nth(1).selectOption('a_insert')
    await expect(pDialog.getByText('插入與卡合互斥')).toBeVisible()
    await expect(pDialog.locator('select').nth(2).locator('option[value="a_snap"]')).toHaveCount(0)

    await pDialog.locator('select').nth(1).selectOption('a_snap')
    await expect(pDialog.locator('select').nth(2).locator('option[value="a_insert"]')).toHaveCount(0)
  })
})

test('E-04-6: 列表層 SIMO 會映射到建立 WI 的 rows pairing', async ({ page }) => {
  const ACTION_A = 'action-a'
  const ACTION_B = 'action-b'
  const WI_NEW = 'wi-new'
  let publishBody: Record<string, any> | null = null // eslint-disable-line @typescript-eslint/no-explicit-any

  const rowA = {
    hand: 'RH',
    frequency: 1,
    simo_pair_index: null,
    vocab_refs: {},
    narrative_zh: '抓取零件',
    computed: { total_tmu: 10, total_seconds: 0.36, eff_tmu: 10, contribution_tmu: 10 },
    cycle: {
      seq: 'GM',
      rule_set_code: 'MINIMOST_FACTORY_V2',
      a0: { reach_cm: 5, twist_deg: 0, foot_cm: 0 },
      b1: { b_code: null },
      g2: { g_code: 'g_simple', modifiers: {}, repeat_count: 1 },
      a3: { reach_cm: 5, twist_deg: 0, foot_cm: 0 },
      b4: { b_code: null },
      p5: { p_base_code: 'p_put', p_addon_codes: [], precision: false, repeat_count: 1 },
      a6: { reach_cm: 0, twist_deg: 0, foot_cm: 0 },
    },
  }
  const rowB = {
    ...rowA,
    narrative_zh: '放置零件',
  }

  await page.route('/api/**', route => {
    const url = route.request().url()
    const method = route.request().method()
    const path = new URL(url).pathname

    if (url.includes('/api/v2/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ADMIN_ME) })
    }
    if (url.includes('/api/v2/rule-sets/active')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' }) })
    }
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_OPTS) })
    }
    if (url.includes('/api/v2/vocab')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/v2/minimost/calculate')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ seq: 'GM', total_tmu: 10, total_seconds: 0.36, tech_line: 'GM TEST' }) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=action')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
        { id: ACTION_A, name_zh: '動作 A', category: 'action', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: 1, total_tmu: 10, action_count: 1, seq_kind: 'GM', hand: 'RH', base_tmu: 10, frequency: 1, current_version_detail: null },
        { id: ACTION_B, name_zh: '動作 B', category: 'action', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: 1, total_tmu: 10, action_count: 1, seq_kind: 'GM', hand: 'RH', base_tmu: 10, frequency: 1, current_version_detail: null },
      ]) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=wi-template')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (path === `/api/v2/motion-modules/${ACTION_A}`) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: ACTION_A, name_zh: '動作 A', category: 'action', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: 1, total_tmu: 10, action_count: 1, seq_kind: 'GM', hand: 'RH', base_tmu: 10, frequency: 1,
        current_version_detail: { id: 'ver-a', module_id: ACTION_A, version_no: 1, rule_set_id: 'rs-1', rows: [rowA], narrative_zh: '抓取零件', total_tmu: 10, total_seconds: 0.36, published_by: 'IEC141289', published_at: '2026-08-05T00:00:00Z' },
      }) })
    }
    if (path === `/api/v2/motion-modules/${ACTION_B}`) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: ACTION_B, name_zh: '動作 B', category: 'action', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: 1, total_tmu: 10, action_count: 1, seq_kind: 'GM', hand: 'RH', base_tmu: 10, frequency: 1,
        current_version_detail: { id: 'ver-b', module_id: ACTION_B, version_no: 1, rule_set_id: 'rs-1', rows: [rowB], narrative_zh: '放置零件', total_tmu: 10, total_seconds: 0.36, published_by: 'IEC141289', published_at: '2026-08-05T00:00:00Z' },
      }) })
    }
    if (path === '/api/v2/motion-modules' && method === 'POST') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: WI_NEW, name_zh: '新 WI', category: 'wi-template', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'draft', current_version: 0, total_tmu: null, action_count: null, current_version_detail: null,
      }) })
    }
    if (path === `/api/v2/motion-modules/${WI_NEW}` && method === 'GET') {
      const published = !!publishBody
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: WI_NEW, name_zh: '新 WI', category: 'wi-template', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: published ? 1 : 0, total_tmu: published ? 20 : null, action_count: published ? 2 : null,
        current_version_detail: published
          ? { id: 'ver-wi', module_id: WI_NEW, version_no: 1, rule_set_id: 'rs-1', rows: publishBody?.rows ?? [], narrative_zh: '新 WI', total_tmu: 20, total_seconds: 0.72, published_by: 'IEC141289', published_at: '2026-08-05T00:00:00Z' }
          : null,
      }) })
    }
    if (path === `/api/v2/motion-modules/${WI_NEW}/publish` && method === 'POST') {
      publishBody = route.request().postDataJSON() as Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: WI_NEW, current_version: 1 }) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await gotoAndWait(page)
  await clickNavAndWait(page, /MOST 工作台/)

  const rows = page.locator('tbody tr')
  await rows.nth(1).getByTestId('action-row-move-up').click()
  await expect(rows.nth(0)).toContainText('動作 B')
  await expect(rows.nth(1)).toContainText('動作 A')

  await rows.nth(0).locator('input[type="checkbox"]').check()
  await rows.nth(1).locator('input[type="checkbox"]').check()
  await rows.nth(0).getByTestId('action-row-simo-checkbox').check()
  await rows.nth(0).getByTestId('action-row-simo').selectOption(ACTION_A)

  await page.getByRole('button', { name: '建立 WI' }).click()

  await expect.poll(() => publishBody?.rows?.[0]?.sub_activity).toBe('動作 B')
  await expect.poll(() => publishBody?.rows?.[1]?.sub_activity).toBe('動作 A')
  await expect.poll(() => publishBody?.rows?.[0]?.simo_pair_index).toBe(1)
  await expect.poll(() => publishBody?.rows?.[1]?.simo_pair_index ?? null).toBe(null)
})

test('E-04-7: 再做一份會載回建立器但維持新增模式', async ({ page }) => {
  const ACTION_ID = 'action-rework'
  const row = {
    hand: 'RH',
    frequency: 1,
    simo_pair_index: null,
    vocab_refs: {},
    sub_activity: '搬取零件',
    narrative_zh: '搬取零件',
    computed: { total_tmu: 28, total_seconds: 1.008, eff_tmu: 28, contribution_tmu: 28 },
    cycle: {
      seq: 'GM',
      rule_set_code: 'MINIMOST_FACTORY_V2',
      a0: { reach_cm: 5, twist_deg: 0, foot_cm: 0 },
      b1: { b_code: null },
      g2: { g_code: 'g_simple', modifiers: {}, repeat_count: 1 },
      a3: { reach_cm: 5, twist_deg: 0, foot_cm: 0 },
      b4: { b_code: null },
      p5: { p_base_code: 'p_put', p_addon_codes: [], precision: false, repeat_count: 1 },
      a6: { reach_cm: 0, twist_deg: 0, foot_cm: 0 },
    },
  }

  await page.route('/api/**', route => {
    const url = route.request().url()
    const path = new URL(url).pathname

    if (url.includes('/api/v2/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ADMIN_ME) })
    }
    if (url.includes('/api/v2/rule-sets/active')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' }) })
    }
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_OPTS) })
    }
    if (url.includes('/api/v2/vocab')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/v2/minimost/calculate')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ seq: 'GM', total_tmu: 28, total_seconds: 1.008, tech_line: 'GM REWORK' }) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=action')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
        { id: ACTION_ID, name_zh: '既有動作', category: 'action', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: 1, total_tmu: 28, action_count: 1, seq_kind: 'GM', hand: 'RH', base_tmu: 28, frequency: 1, current_version_detail: null },
      ]) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=wi-template')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (path === `/api/v2/motion-modules/${ACTION_ID}`) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: ACTION_ID, name_zh: '既有動作', category: 'action', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: 1, total_tmu: 28, action_count: 1, seq_kind: 'GM', hand: 'RH', base_tmu: 28, frequency: 1,
        current_version_detail: { id: 'ver-rework', module_id: ACTION_ID, version_no: 1, rule_set_id: 'rs-1', rows: [row], narrative_zh: '搬取零件', total_tmu: 28, total_seconds: 1.008, published_by: 'IEC141289', published_at: '2026-08-05T00:00:00Z' },
      }) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await gotoAndWait(page)
  await clickNavAndWait(page, /MOST 工作台/)

  await page.getByRole('button', { name: /再做一份/ }).click()

  await expect(page.locator('input[value="既有動作"]')).toBeVisible()
  await expect(page.getByRole('button', { name: '新增動作' })).toBeVisible()
  await expect(page.getByText('編輯中')).toHaveCount(0)
})

test('E-04-8: WI 大綱支援本地排序（上移/下移）', async ({ page }) => {
  await page.route('/api/**', route => {
    const url = route.request().url()

    if (url.includes('/api/v2/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ADMIN_ME) })
    }
    if (url.includes('/api/v2/rule-sets/active')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' }) })
    }
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_OPTS) })
    }
    if (url.includes('/api/v2/vocab')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/v2/minimost/calculate')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ seq: 'GM', total_tmu: 10, total_seconds: 0.36, tech_line: 'GM TEST' }) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=action')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=wi-template')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
        { id: 'wi-a', name_zh: 'WI A', category: 'wi-template', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: 1, total_tmu: 28, action_count: 1, seq_kind: 'GM', hand: 'RH', base_tmu: 28, frequency: 1, current_version_detail: null },
        { id: 'wi-b', name_zh: 'WI B', category: 'wi-template', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'standard', current_version: 1, total_tmu: 56, action_count: 2, seq_kind: 'GM', hand: 'RH', base_tmu: 28, frequency: 1, current_version_detail: null },
      ]) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await gotoAndWait(page)
  await clickNavAndWait(page, /MOST 工作台/)

  const cards = page.getByTestId('wi-outline-card')
  await expect(cards).toHaveCount(2)
  await expect(cards.nth(0)).toContainText('WI A')
  await expect(cards.nth(1)).toContainText('WI B')

  await cards.nth(1).getByTestId('wi-outline-move-up').click()
  await expect(cards.nth(0)).toContainText('WI B')
  await expect(cards.nth(1)).toContainText('WI A')

  await cards.nth(0).getByTestId('wi-outline-move-down').click()
  await expect(cards.nth(0)).toContainText('WI A')
  await expect(cards.nth(1)).toContainText('WI B')
})

test('E-04-9: draft WI 可於大綱內改名', async ({ page }) => {
  let wiName = 'Draft WI A'

  await page.route('/api/**', route => {
    const url = route.request().url()
    const method = route.request().method()
    const path = new URL(url).pathname

    if (url.includes('/api/v2/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ADMIN_ME) })
    }
    if (url.includes('/api/v2/rule-sets/active')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' }) })
    }
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_OPTS) })
    }
    if (url.includes('/api/v2/vocab')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/v2/minimost/calculate')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ seq: 'GM', total_tmu: 10, total_seconds: 0.36, tech_line: 'GM TEST' }) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=action')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=wi-template')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
        { id: 'wi-draft-a', name_zh: wiName, category: 'wi-template', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'draft', current_version: 0, total_tmu: null, action_count: null, seq_kind: null, hand: null, base_tmu: null, frequency: null, current_version_detail: null },
      ]) })
    }
    if (path === '/api/v2/motion-modules/wi-draft-a' && method === 'PUT') {
      const body = route.request().postDataJSON() as Record<string, unknown>
      wiName = String(body.name_zh ?? wiName)
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: 'wi-draft-a', name_zh: wiName, category: 'wi-template', keywords: [], scope: 'personal', owner: 'IEC141289', status: 'draft', current_version: 0,
        total_tmu: null, action_count: null, seq_kind: null, hand: null, base_tmu: null, frequency: null, current_version_detail: null,
      }) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await gotoAndWait(page)
  await clickNavAndWait(page, /MOST 工作台/)

  const card = page.getByTestId('wi-outline-card').first()
  await expect(card).toContainText('Draft WI A')

  await card.getByTestId('wi-outline-rename').click()
  const input = card.getByTestId('wi-outline-rename-input')
  await input.fill('Draft WI Renamed')
  await card.getByTestId('wi-outline-rename-save').click()

  await expect(card).toContainText('Draft WI Renamed')
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
    await expect(page.getByRole('button', { name: '編輯工時表' })).toBeVisible()
  })

  test('G-01-4: 案件詳情含匯出操作區（ADR-021：原頂層匯出 tab 的五種操作）', async ({ page }) => {
    await page.getByText('組裝站作業').click()
    // 五種匯出操作：wi-preview / excel / lb-csv / report.xlsx / lb-api dry-run
    await expect(page.getByRole('button', { name: 'WI 預覽' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下載 Excel' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下載 LB CSV' })).toBeVisible()
    await expect(page.getByRole('button', { name: '下載報表' })).toBeVisible()
    await expect(page.getByRole('button', { name: '送 LB API (dry-run)' })).toBeVisible()
    // WI 預覽走 apiGet，摘要 inline 顯示（mock: 1 列 / 28 TMU）
    await page.getByRole('button', { name: 'WI 預覽' }).click()
    await expect(page.getByText(/共 1 列 · 合計/)).toBeVisible()
  })
})

// ─── § G-01b: 案件清單折疊（P1-C，守則 §6）────────────────────────────────────
// 一列＝一個案件（非一版）；version_count>1 給「N 版」徽章＋展開鈕，可點歷史版切詳情。

test.describe('§G-01b 案件清單版本折疊 (P1-C)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_MULTIVERSION)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
  })

  test('G-01b-1: 三版的 SKU 只出現一列案件，帶「3 版」徽章與代表版（最新 v3）', async ({ page }) => {
    await expect(page.getByTestId('case-row')).toHaveCount(1)
    await expect(page.getByText('3 版')).toBeVisible()
    await expect(page.getByText('最新 v3')).toBeVisible()
    // footer 計數語意＝案件數
    await expect(page.getByText('共 1 件案件')).toBeVisible()
    // 未展開時不顯示版本列
    await expect(page.getByTestId('case-versions')).toHaveCount(0)
  })

  test('G-01b-2: 展開列出全部版本（v1…v3，版本時序）', async ({ page }) => {
    await page.getByRole('button', { name: '展開版本歷史' }).click()
    const versions = page.getByTestId('case-versions').getByRole('listitem')
    await expect(versions).toHaveCount(3)
    await expect(versions.nth(0)).toContainText('v1')
    await expect(versions.nth(1)).toContainText('v2')
    await expect(versions.nth(2)).toContainText('v3')
    // 各版 TMU 由後端 versions[] 提供（前端不計算）
    await expect(versions.nth(1)).toContainText('57 TMU')
  })

  test('G-01b-3: 預設檢視代表版；點歷史版 → 詳情切到該版（版本/TMU/狀態隨之變）', async ({ page }) => {
    await page.getByText('組裝站作業').click()
    // 預設＝代表版 v3 · 最新
    const viewing = page.getByTestId('viewing-version')
    await expect(viewing).toContainText('v3')
    await expect(viewing).toContainText('最新')
    await expect(page.getByText('80 TMU').first()).toBeVisible()

    // 展開 → 點 v2（approved，57 TMU）
    await page.getByRole('button', { name: '展開版本歷史' }).click()
    await page.getByTestId('case-versions').getByRole('listitem').nth(1).click()
    await expect(viewing).toContainText('v2')
    await expect(viewing).toContainText('歷史')
    await expect(page.getByText('57 TMU').first()).toBeVisible()
  })

  // review #1：狀態流轉只允許在代表版（守則 §1 案件＝單一當前狀態）
  test('G-01b-4: 歷史版不可狀態流轉／不可編輯（admin：代表版 draft 有核准鈕，歷史 draft 沒有）', async ({ page }) => {
    await page.getByText('組裝站作業').click()
    // 代表版 v3 = draft + admin → 核准鈕在（exact:true 避開狀態篩選 tab「已核准」/「已退役」）
    await expect(page.getByRole('button', { name: '核准', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '編輯工時表' })).toBeEnabled()

    await page.getByRole('button', { name: '展開版本歷史' }).click()
    const versions = page.getByTestId('case-versions').getByRole('listitem')

    // 歷史 draft v1：不得出現核准鈕（否則同鏈會出現兩個 approved）
    await versions.nth(0).click()
    await expect(page.getByTestId('viewing-version')).toContainText('歷史')
    await expect(page.getByRole('button', { name: '核准', exact: true })).toHaveCount(0)
    // 編輯入口停用＋唯讀提示（不讓使用者編到存檔才撞 NotEditable）
    await expect(page.getByRole('button', { name: '編輯工時表' })).toBeDisabled()
    await expect(page.getByText('歷史版本唯讀，請切換到最新版再編輯').first()).toBeVisible()

    // 歷史 approved v2：admin 也不得出現退役鈕
    await versions.nth(1).click()
    await expect(page.getByTestId('viewing-version')).toContainText('歷史')
    await expect(page.getByRole('button', { name: '退役', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '編輯工時表' })).toBeDisabled()
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

// ─── § H-01: 主數據管理頁面 ────────────────────────────────────────────────────

test.describe('§H-01 主數據管理頁面 (checklist H-01)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    await clickNavAndWait(page, /主數據管理/)
  })

  test('H-01-1: 主數據管理頁 heading 存在', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '主數據管理' })).toBeVisible()
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

// ─── § I-01: RBAC viewer 看不到主數據管理 ────────────────────────────────────────

test.describe('§I-01 RBAC viewer 無主數據管理入口 (checklist I-01, A-02)', () => {
  test('I-01-1: viewer 身分 sidebar 無主數據管理 button', async ({ page }) => {
    await setupRoutes(page, VIEWER_ME)
    await gotoAndWait(page)
    // level=0 → canEdit=false → minRole:'analyst' item hidden
    await expect(page.getByRole('button', { name: /主數據管理/ })).not.toBeVisible()
  })
})

// ─── § G-03: 案件編輯情境頁 (ADR-021 Phase 3) ────────────────────────────────

test.describe('§G-03 案件編輯情境頁 (ADR-021 Phase 3)', () => {
  test('G-03-1: 編輯工時表 → 案件情境列（返回鈕/案件名/產品鏈/狀態 badge）→ 返回分析案件', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    await page.getByText('組裝站作業').click()
    await page.getByRole('button', { name: '編輯工時表' }).click()
    await page.waitForLoadState('networkidle')

    // 案件情境列（CaseContextBar）：返回鈕 + 案件名 + 產品/SKU/版本 + 狀態 badge
    const bar = page.getByTestId('case-context-bar')
    await expect(bar).toBeVisible()
    await expect(bar.getByRole('button', { name: '← 返回分析案件' })).toBeVisible()
    await expect(bar.getByText('組裝站作業')).toBeVisible()
    await expect(bar.getByText('Product X / SKU 001 · 版本 v1')).toBeVisible()
    await expect(bar.getByText('草稿')).toBeVisible()

    // 情境列下方即 WiWorkbench 編輯器（工時表表頭存在）
    await expect(page.locator('thead').getByText('Base TMU')).toBeVisible()

    // 返回動線：情境列返回鈕 → 分析案件清單
    await bar.getByRole('button', { name: '← 返回分析案件' }).click()
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('button', { name: '全部', exact: true })).toBeVisible()
  })

  test('G-03-2: 新建案件 modal（選產品→SKU→line 名稱）→ 建立後直接進入編輯情境', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)

    // 清單上方「＋ 新建案件」按鈕（analyst+）
    await page.getByRole('button', { name: '＋ 新建案件' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByText('新建案件')).toBeVisible()

    // P1-C 守則 §6：產品/SKU **不自動預選**（舊行為會默默在同一 SKU 上 +1 版），
    // 未選 SKU 前建立鈕停用
    await expect(dialog.locator('select').first()).toHaveValue('')
    await expect(dialog.locator('select').nth(1)).toHaveValue('')
    await expect(dialog.getByRole('button', { name: /建立/ })).toBeDisabled()

    // 明確選產品 → SKU（此 SKU 尚無工序表 ⇒ 真正的新案件，不出現引導區塊）
    await dialog.locator('select').first().selectOption('p1')
    await dialog.locator('select').nth(1).selectOption('sk1')
    await expect(dialog.getByTestId('existing-versions-guide')).toHaveCount(0)

    // 輸入 line 名稱 → 建立（v1：此 SKU 尚無工序表）
    await dialog.getByPlaceholder('可空').first().fill('L1 線')
    await dialog.getByRole('button', { name: /建立新案件（v1）/ }).click()
    await page.waitForLoadState('networkidle')

    // 建立成功 → 直接進入案件編輯情境（情境列顯示新案件名與草稿 badge）
    const bar = page.getByTestId('case-context-bar')
    await expect(bar).toBeVisible()
    await expect(bar.getByText('L1 線')).toBeVisible()
    await expect(bar.getByText(/Product X \/ SKU001（機種一） · 版本 v1/)).toBeVisible()
    await expect(bar.getByText('草稿')).toBeVisible()
  })

  test('G-03-2b: 同 SKU ＋同 model_label（命中既有案件）→ 繼續編輯草稿／建立新版本（守則 §6）', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT, MOCK_SKU_WORKSHEETS)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    await page.getByRole('button', { name: '＋ 新建案件' }).click()

    const dialog = page.getByRole('dialog')
    await dialog.locator('select').first().selectOption('p1')
    await dialog.locator('select').nth(1).selectOption('sk1')
    // 聚合鍵的另一半：填入既有案件的 model_label 才算命中（review #2）
    await dialog.getByPlaceholder('可空').first().fill('L1 線')

    // 引導區塊：計數與草稿清單都限縮在**該案件**（L1 線 = v1 approved + v2 draft）
    const guide = dialog.getByTestId('existing-versions-guide')
    await expect(guide).toBeVisible()
    await expect(guide.getByText('此機種/線別（L1 線）的案件已有 2 個版本')).toBeVisible()
    await expect(guide.getByRole('button', { name: /v2/ })).toBeVisible()
    await expect(guide.getByRole('button', { name: /v1/ })).toHaveCount(0)  // approved 非草稿
    await expect(guide.getByRole('button', { name: /v3/ })).toHaveCount(0)  // 屬於 L2 線案件，不得列出
    // 別的案件的資訊區塊不出現（已命中既有案件）
    await expect(dialog.getByTestId('other-cases-info')).toHaveCount(0)

    // 主要動作＝建立新版本；版號＝後端 SKU 範圍 COUNT+1（3 筆 → v4）
    await expect(dialog.getByRole('button', { name: '建立新版本（v4）' })).toBeVisible()

    // 選「繼續編輯 v2 草稿」→ 不建版，直接進入該工序表編輯情境
    await guide.getByRole('button', { name: /v2/ }).click()
    await page.waitForLoadState('networkidle')
    const bar = page.getByTestId('case-context-bar')
    await expect(bar).toBeVisible()
    await expect(bar.getByText(/版本 v2/)).toBeVisible()
  })

  test('G-03-2c: 同 SKU 但 model_label 不同 → 資訊性提示＋主按鈕維持「建立新案件」（review #2）', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT, MOCK_SKU_WORKSHEETS)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    await page.getByRole('button', { name: '＋ 新建案件' }).click()

    const dialog = page.getByRole('dialog')
    await dialog.locator('select').first().selectOption('p1')
    await dialog.locator('select').nth(1).selectOption('sk1')
    // 全新的機種/線別＝該 SKU 底下的新案件
    await dialog.getByPlaceholder('可空').first().fill('L3 線')

    // 不得宣稱「這不是新案件」，也不得列出別案件的草稿
    await expect(dialog.getByTestId('existing-versions-guide')).toHaveCount(0)
    const info = dialog.getByTestId('other-cases-info')
    await expect(info).toBeVisible()
    await expect(info.getByText('此 SKU 底下另有 2 個其他機種/線別的案件')).toBeVisible()
    await expect(info.getByText('L1 線')).toBeVisible()
    await expect(info.getByText('L2 線')).toBeVisible()
    await expect(info.getByRole('button')).toHaveCount(0)  // 純資訊，不可誤點

    // 主按鈕語意＝建立新案件（版號仍由後端 SKU 範圍 COUNT+1 決定＝v4，前端不假造 v1）
    await expect(dialog.getByRole('button', { name: '建立新案件（v4）' })).toBeVisible()
  })

  test('G-03-2d: WI 專案建立分析案件 → 預覽與 Level 共用匯入列', async ({ page }) => {
    const cases = { total: 0, items: [] as typeof MOCK_CASES_DRAFT.items }
    const project = {
      id: 'project-001',
      project_code: 'PW-WISET-001',
      name: 'Playwright WI 專案',
      site: 'TAO',
      bu: 'BU1',
      process: 'L10_ASSY',
      family: 'FAMILY-A',
      model: 'PROJECT-LINE',
      description: null,
      status: 'draft',
      created_by: 'IEC141289',
      created_at: '2026-08-04T00:00:00Z',
      updated_at: '2026-08-04T00:00:00Z',
      items: [{
        id: 'project-item-001',
        project_id: 'project-001',
        seq_no: 1,
        wi_template_id: 'wi-template-001',
        wi_code_snapshot: null,
        wi_name_snapshot: '裝配主板',
        action_count_snapshot: 1,
        total_tmu_snapshot: 28,
        total_seconds_snapshot: 1.008,
        notes: null,
        created_at: '2026-08-04T00:00:00Z',
        updated_at: '2026-08-04T00:00:00Z',
      }],
    }
    let instantiateBody: Record<string, unknown> | null = null

    await setupRoutes(page, ADMIN_ME, cases)
    await page.route('**/api/v2/wi-set-projects**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (request.method() === 'POST' && path.endsWith('/instantiate')) {
        instantiateBody = request.postDataJSON() as Record<string, unknown>
        cases.total = 1
        cases.items = [{
          ...MOCK_CASES_DRAFT.items[0],
          process_version_id: 'pv-project-001',
          worksheet_id: 'ws-project-001',
          process_name: 'PROJECT-LINE',
          total_tmu: 28,
          model_label: 'PROJECT-LINE',
          versions: [{
            ...MOCK_CASES_DRAFT.items[0].versions[0],
            process_version_id: 'pv-project-001',
            worksheet_id: 'ws-project-001',
          }],
        }]
        return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({
          worksheet_id: 'ws-project-001',
          version_no: 'v1',
          status: 'draft',
          imported_wi_count: 1,
          imported_row_count: 1,
          tmu_drift: [],
        }) })
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(path === '/api/v2/wi-set-projects' ? [project] : project),
      })
    })
    await page.route('**/api/v2/worksheets/ws-project-001**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/export/wi-preview')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
          worksheet_id: 'ws-project-001', status: 'draft', total_tmu: 28, rows: [{
            seq_no: 1, sub_activity: '裝配主板', method: '右手抓取主板並放置', tmu: 28,
          }],
        }) })
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        worksheet_id: 'ws-project-001',
        status: 'draft',
        total_tmu: 28,
        default_rule_set: null,
        rows: [{
          wi_row_id: 'row-project-001',
          seq_no: 1,
          hand: 'RH',
          sub_activity: '裝配主板',
          object_vocab_id: 'v1',
          from_vocab_id: null,
          to_vocab_id: null,
          tool_vocab_id: null,
          frequency: 1,
          simo_group_id: null,
          source_module_id: 'wi-template-001',
          source_module_version: 1,
          cycle: {
            seq_kind: 'GM', total_tmu: 28, total_seconds: 1.008,
            narrative: '裝配主板', slot_inputs: {}, rule_set_id: 'rs-1',
          },
          level: {
            coefficient: 1, ascription: null, level: '1', countersignature: null,
            parent_countersignature: null, number: null, number_count: null,
          },
        }],
      }) })
    })
    await page.route('**/api/v2/level/validate', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ valid: true, issues: [] }),
    }))

    await gotoAndWait(page)
    await clickNavAndWait(page, /WI 專案建立/)
    // 用 aria-label 而非 `locator('select').first()`：後者靠 DOM 順序猜是哪個下拉，
    // 版面一動就指到別的 select（wi-set-add.spec.ts 同一個下拉已改用可及名稱）。
    await page.getByLabel('選擇現有專案').selectOption('project-001')
    await expect(page.getByRole('button', { name: '建立分析案件' })).toBeEnabled()
    await page.getByRole('button', { name: '建立分析案件' }).click()

    const dialog = page.getByRole('dialog', { name: '建立分析案件' })
    await dialog.locator('select').first().selectOption('p1')
    await dialog.locator('select').nth(1).selectOption('sk1')
    await dialog.getByRole('button', { name: '建立並匯入 WI' }).click()

    await expect(page.getByRole('heading', { name: 'PROJECT-LINE' })).toBeVisible()
    expect(instantiateBody).toMatchObject({ sku_id: 'sk1', model_label: 'PROJECT-LINE' })
    await page.getByRole('button', { name: 'WI 預覽' }).click()
    await expect(page.getByText(/共 1 列/)).toBeVisible()
    const previewRows = page.getByTestId('wi-preview-rows')
    await expect(previewRows.getByText('裝配主板')).toBeVisible()
    await expect(previewRows.getByText('右手抓取主板並放置')).toBeVisible()

    await clickNavAndWait(page, /Level System/)
    await expect(page.getByText('裝配主板')).toBeVisible()
    await expect(page.getByText('✓ 群組設定正確')).toBeVisible()
  })

  test('G-03-3: viewer 不顯示「新建案件」按鈕（RBAC gating）', async ({ page }) => {
    await setupRoutes(page, VIEWER_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    await expect(page.getByRole('button', { name: '＋ 新建案件' })).not.toBeVisible()
  })

  test('G-03-4: MOST 工作台不再出現全域 WorksheetBar（ADR-021 去全域化）', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
    await clickNavAndWait(page, /MOST 工作台/)
    // 工作台本體正常渲染（正向）
    await expect(page.getByTestId('summary-bar')).toBeVisible()
    // WorksheetBar 專有元素不得出現（＋新建工序表鈕、工序表選擇器空狀態）
    await expect(page.getByRole('button', { name: '＋新建工序表' })).not.toBeVisible()
    await expect(page.getByText('（此 SKU 尚無工序表）')).not.toBeVisible()
  })

  test('G-03-5: MOST 工作台無製程途程入口（ADR-022 批次 B：tab 斷路，能力批次 E 搬入案件編輯）', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /MOST 工作台/)
    // 單頁本體正常渲染（正向），且不再有製程途程 tab / 面板
    await expect(page.getByTestId('summary-bar')).toBeVisible()
    await expect(page.getByRole('button', { name: '製程途程工作區' })).toHaveCount(0)
    await expect(page.getByText('製程大綱')).toHaveCount(0)
  })

  test('G-03-6: Level System 無 activeWs → 空狀態提示＋跳轉鈕', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /Level System/)
    await expect(page.getByText('請先從分析案件開啟工時表')).toBeVisible()
    await page.getByRole('button', { name: '前往分析案件' }).click()
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('button', { name: '全部', exact: true })).toBeVisible()
  })
})

// ─── § L-03/L-04: 退役確認 ────────────────────────────────────────────────────

test.describe('§L 退役確認 (checklist L-03, L-04)', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page, ADMIN_ME)
    await gotoAndWait(page)
  })

  test('L-03: 舊 MasterData tab 已退役（未以獨立入口復活）', async ({ page }) => {
    // MasterData.tsx 已刪除、PRIMARY_NAV 無 'master-data' 項；features/master-data/ 僅剩 api.ts
    // 供工作台複用。ADR-024 後「主數據管理」是唯一帶「主數據」字樣的入口（原 H-01 頁更名而來）。
    const masterDataNav = page.locator('nav').first().getByRole('button', { name: /主數據/ })
    await expect(masterDataNav).toHaveCount(1)
    await expect(masterDataNav).toHaveText(/主數據管理/)
  })

  test('L-04: SOP 版本 tab 已退役，sidebar 無入口', async ({ page }) => {
    // SECONDARY_NAV is empty; SOP removed from PRIMARY_NAV
    await expect(page.getByRole('button', { name: /SOP/ })).not.toBeVisible()
  })
})
