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
  // from/to（H-DSX：DSX 建議距離查詢需要 WiWorkbench 建立器面板的「從哪裡」／「到哪裡」有值）
  { id: 'v3', kind: 'from', name_zh: '料架', source_system: 'manual', is_active: true },
  { id: 'v4', kind: 'to', name_zh: '流水線', source_system: 'manual', is_active: true },
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

  test('A-01-3: admin 展開時看到 6 個導覽項目（ADR-021，ADR-038 W6 移除兩項；順序固定）', async ({ page }) => {
    await gotoAndWait(page)
    // ADR-021 目標 IA：儀表板 / Level System / 分析案件 / 主數據管理(analyst+) / 使用者管理(admin) / MOST 字典(admin)
    // ADR-024：「字典管理」更名為「主數據管理」（「字典」在 v2 只指 MOST 規則值）
    // ADR-038 D4（W6）：MOST 工作台與 WI 專案建立移除
    const nav = page.locator('nav').first()
    const labels = ['儀表板', 'Level System', '分析案件', '主數據管理', '使用者管理', 'MOST 字典']
    for (const label of labels) {
      await expect(nav.getByRole('button', { name: new RegExp(label) })).toBeVisible()
    }
    // 側欄剛好 6 項（admin 看得到全部）
    await expect(nav.getByRole('button')).toHaveCount(labels.length)
    // 順序固定（ADR-021）
    const texts = await nav.getByRole('button').allInnerTexts()
    expect(texts.map(t => t.replace(/\s+/g, ' ').trim())).toEqual([
      '表 儀表板', 'L Level System', '案 分析案件', '主 主數據管理', '人 使用者管理', '字 MOST 字典',
    ])
  })

  test('A-01-6: 頂層不含「目錄」「匯出」「WI 組裝」(ADR-021 收斂)', async ({ page }) => {
    await gotoAndWait(page)
    const nav = page.locator('nav').first()
    // 目錄 → 收進分析案件新建流程（Phase 3）；匯出 → 併入案件詳情；WI 組裝 → 改名 MOST 工作台
    await expect(nav.getByRole('button', { name: /目錄/ })).not.toBeVisible()
    await expect(nav.getByRole('button', { name: /匯出/ })).not.toBeVisible()
    await expect(nav.getByRole('button', { name: /WI 組裝/ })).not.toBeVisible()
    // ADR-038 D4（W6）：MOST 工作台與 WI 專案建立已移除
    await expect(nav.getByRole('button', { name: /MOST 工作台/ })).toHaveCount(0)
    await expect(nav.getByRole('button', { name: /WI 專案建立/ })).toHaveCount(0)
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

// ─── § C-01: 動作清單 12 欄 (UX spec §2.4) ───────────────────────────────────

test.describe('§C-01 動作清單 12 欄表格結構 (checklist C-01)', () => {
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

// ─── § H-DSX: DSX 建議距離（契約草案 §1.1／§3.1；掛載點 WiWorkbench.tsx 建立器面板）──
// 掛載點 2026-08-24 更正：原掛 workbench-v3/WiItemInspector 的模組模板列永遠沒有真實
// wi_row_id（ModuleRowIn 沒有穩定 id），改掛這裡（WiWorkbench.tsx 的 a3/from/to 建立器
// 面板）——這裡組的是尚未存檔的新列，`wi_row_id` 選填不帶。只驗 `integration_disabled`
// 路徑（預設 DDM_DSX_INTEGRATION_ENABLED=false，不需要真的連 DSX 或種子資料，最好測）。

test.describe('§H-DSX DSX 建議距離 (契約草案 §3.1)', () => {
  test('H-DSX-1: a3 modal 查詢建議距離 → integration_disabled 顯示對應訊息，且 request 不帶 wi_row_id', async ({ page }) => {
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    await page.getByText('組裝站作業').click()
    await page.getByRole('button', { name: '編輯工時表' }).click()
    await page.waitForLoadState('networkidle')

    // 建立器面板組一筆尚未存檔的新列：填 from/to（a3 DSX 查詢的前提）
    await page.getByPlaceholder('—來源—').click()
    await page.getByText('料架').click()
    await page.getByPlaceholder('—目的地—').click()
    await page.getByText('流水線').click()

    // mock DSX 端點（優先於 setupRoutes 的 catch-all：Playwright 後註冊的路由先比對）
    let capturedBody: Record<string, unknown> | null = null
    await page.route('**/api/v2/dsx/a3-distance', route => {
      capturedBody = route.request().postDataJSON() as Record<string, unknown>
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ available: false, reason: 'integration_disabled' }),
      })
    })

    // 開 a3（放置段）modal → 觸發查詢
    await page.getByTitle('A 移動 — 放置段').click()
    await expect(page.getByTestId('dsx-a3-suggestion')).toBeVisible()
    await page.getByTestId('dsx-a3-query-btn').click()

    await expect(page.getByTestId('dsx-a3-unavailable')).toHaveText('DSX 距離查詢功能目前未啟用。')
    // 不得出現 available=true 的建議卡（integration_disabled 不是「查到結果」）
    await expect(page.getByTestId('dsx-a3-result')).toHaveCount(0)

    expect(capturedBody).not.toBeNull()
    expect(capturedBody!.from_vocab_id).toBe('v3')
    expect(capturedBody!.to_vocab_id).toBe('v4')
    // 建立器面板組的是尚未存檔的新列：不帶 wi_row_id（掛載點更正的核心斷言）
    expect(capturedBody).not.toHaveProperty('wi_row_id')
  })

  test('H-DSX-2: 查到建議距離 → 填入伸手與填入腳步各自獨立落 cmToBandValue 換算後的 band 值，互不清空，並顯示水平/垂直分量', async ({ page }) => {
    // cmToBandValue 是純函式，前端沒有 vitest/jest，只有這裡的 e2e 路徑會真的跑到它
    // （MOCK_OPTS.a_bands：reach=[{max_value:5,index:2}]、foot=[{max_value:null,index:0}]，
    // 所以 distance_cm=3 時 reach 落檔應為 5、foot 落檔應為 999——見 cycle.ts 的規則）。
    // 2026-08-24：互斥拿掉（ASlot 架構上 reach_cm／foot_cm 本來就允許同時有值，MOST
    // 引擎算 TMU 取 max(reach_index, foot_index, twist_index)，不是相加），改驗兩格
    // 可以同時帶著 DSX 建議值；同時驗新增的 horizontal_cm／vertical_cm 分量有顯示。
    await setupRoutes(page, ADMIN_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    await page.getByText('組裝站作業').click()
    await page.getByRole('button', { name: '編輯工時表' }).click()
    await page.waitForLoadState('networkidle')

    await page.getByPlaceholder('—來源—').click()
    await page.getByText('料架').click()
    await page.getByPlaceholder('—目的地—').click()
    await page.getByText('流水線').click()

    await page.route('**/api/v2/dsx/a3-distance', route => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        available: true, distance_cm: 3, horizontal_cm: 2.5, vertical_cm: 1.2, provisional: true,
      }),
    }))

    await page.getByTitle('A 移動 — 放置段').click()
    const modal = page.getByTestId('dsx-a3-suggestion').locator('xpath=ancestor::div[contains(@class,"rounded-xl")][1]')
    // aBlock(cur.a3) 依序渲染 reach/twist/foot 三個 <select>，activeSlot==='a3' 時 modal
    // 內沒有其他 select（bBlock/gBlock/pBlock 等都是別的 slot 才會渲染）
    const reachSelect = modal.locator('select').nth(0)
    const footSelect = modal.locator('select').nth(2)

    await page.getByTestId('dsx-a3-query-btn').click()
    await expect(page.getByTestId('dsx-a3-result')).toBeVisible()

    // 水平/垂直分量顯示為參考數值，不是一一對應的填入建議。用各自獨立的
    // testid + toHaveText 精確比對（而非對整段文字 toContainText 兩個數字）：
    // 後者測不出水平/垂直被對調的 mutation（'2.5cm' 和 '1.2cm' 都還在文字裡，
    // 只是換了位置，弱比對照樣通過）。
    await expect(page.getByTestId('dsx-a3-component-horizontal')).toHaveText('水平分量 2.5cm')
    await expect(page.getByTestId('dsx-a3-component-vertical')).toHaveText('垂直分量 1.2cm')

    // ── 填入伸手：reach 落 band 值 5（3cm → cmToBandValue 找第一個 max_value>=3 的 band）
    await page.getByTestId('dsx-a3-fill-reach').click()
    await expect(reachSelect).toHaveValue('5')
    await expect(footSelect).toHaveValue('0')
    await expect(page.getByTestId('dsx-a3-filled-reach'))
      .toHaveText('已填入 A2 伸手：DSX 建議 3cm → 落檔 5cm')

    // ── 再填入腳步：foot 落 band 值 999（唯一 band 是開放檔 max_value=null），
    //    reach 維持剛才填入的值不變（沒有互斥）
    await page.getByTestId('dsx-a3-fill-foot').click()
    await expect(footSelect).toHaveValue('999')
    await expect(reachSelect).toHaveValue('5')
    await expect(page.getByTestId('dsx-a3-filled-reach'))
      .toHaveText('已填入 A2 伸手：DSX 建議 3cm → 落檔 5cm')
    await expect(page.getByTestId('dsx-a3-filled-foot'))
      .toHaveText('已填入 A2 腳步：DSX 建議 3cm → 落檔 999cm')
  })
})

// ─── § H-DSX3D: DSX 3D 擺放介面入口（內部／工程用，GET /api/v2/dsx/ui-url）────
// 掛載點：WiWorkbench.tsx「Table section」標頭。
// 單一觀看者限制（NVIDIA Kit 架構限制）必須反映在開啟前的確認對話框文案裡。

const DSX_UI_URL = 'http://172.32.3.60:8081/most.html'
// 這個位址是真實廠內 DSX/Nucleus 主機（零認證、單一 WebRTC 觀看者，且不在
// RFC1918 私網段內），H-DSX3D-1 開 iframe modal 會讓瀏覽器真的對它發連線——
// 誤連可能把正在使用 3D 介面的人踢下線。這裡回一段有明確標記的假 HTML，
// 讓 iframe 拿到內容但**不放行任何真實網路連線**（Playwright route.fulfill
// 在請求離開瀏覽器前攔截，見下方 H-DSX3D-1 對 iframe 內容的斷言：只要那裡
// 讀到的是這個標記字串，就證明走的是這條 mock 而不是真的連上 172.32.3.60）。
const DSX_HOST_STUB_MARKER = 'MOCK-DSX-HOST-STUB'

// DsxUiEntry 掛載時就會查詢 GET /api/v2/dsx/ui-url（見 dsxUiUrl.ts 檔頭註：要在使用者
// 點擊前就決定入口是否可用），所以 mock 必須在 setupRoutes 的 catch-all 之後、
// gotoAndWait 觸發掛載之前註冊——Playwright 後註冊的路由先比對。
async function gotoWorksheet(page: Page, dsxUiUrl: string | null, identity = ADMIN_ME) {
  await setupRoutes(page, identity, MOCK_CASES_DRAFT)
  // page.route 對整個 page（含其內所有 iframe）生效，攔在請求出瀏覽器之前，
  // 所以下面這行必須在 gotoAndWait 之前註冊——絕對不能讓這條 pattern 漏接。
  await page.route('http://172.32.3.60:8081/**', route => route.fulfill({
    status: 200, contentType: 'text/html',
    body: `<html><body>${DSX_HOST_STUB_MARKER}</body></html>`,
  }))
  await page.route('**/api/v2/dsx/ui-url', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ url: dsxUiUrl }),
  }))
  await gotoAndWait(page)
  await clickNavAndWait(page, /分析案件/)
  await page.getByText('組裝站作業').click()
  // 「編輯工時表」只依 isLatest 停用，不看 canEdit（見 CasesPage.tsx 的
  // 「歷史版唯讀」註解）——viewer 也能點進來，只是進去後是唯讀模式。
  await page.getByRole('button', { name: '編輯工時表' }).click()
  await page.waitForLoadState('networkidle')
}

test.describe('§H-DSX3D DSX 3D 擺放介面入口', () => {
  test('H-DSX3D-1: 已設定網址 → 入口可點 → 確認對話框警告單一觀看者斷線 → 確認後 modal 開啟且 iframe src 正確', async ({ page }) => {
    await gotoWorksheet(page, DSX_UI_URL)

    const entry = page.getByTestId('dsx-ui-entry-btn')
    await expect(entry).toBeEnabled()
    await expect(page.getByTestId('dsx-ui-unavailable-reason')).toHaveCount(0)

    await entry.click()
    const confirmDialog = page.getByTestId('dsx-ui-confirm-dialog')
    await expect(confirmDialog).toBeVisible()
    await expect(confirmDialog).toContainText('斷線')
    await expect(page.getByTestId('dsx-ui-modal')).toHaveCount(0)

    await page.getByTestId('dsx-ui-confirm-proceed').click()
    await expect(confirmDialog).toHaveCount(0)
    const modal = page.getByTestId('dsx-ui-modal')
    await expect(modal).toBeVisible()
    await expect(page.getByTestId('dsx-ui-iframe')).toHaveAttribute('src', DSX_UI_URL)
    // iframe 讀到的必須是上面 mock 回的假內容——這是「請求真的沒有離開瀏覽器打到
    // 172.32.3.60」的正面證據，不是只看 src 屬性（那個永遠對，不管有沒有連成）。
    // 若日後不慎移除 gotoWorksheet 裡的 route 攔截，這裡會變紅（真實 DSX 頁面的內容
    // 不會是這個標記字串，或者連線在沙盒環境直接失敗導致 frameLocator 逾時）。
    await expect(page.frameLocator('[data-testid="dsx-ui-iframe"]').locator('body'))
      .toHaveText(DSX_HOST_STUB_MARKER)

    // sandbox 屬性：允許 script/same-origin（WebRTC/signaling 必要），但不給
    // top-navigation/popups/modals/downloads/forms（誤觸不該能把整個分頁導航走）
    await expect(page.getByTestId('dsx-ui-iframe')).toHaveAttribute('sandbox', 'allow-scripts allow-same-origin')

    await page.getByTestId('dsx-ui-modal-close').click()
    await expect(modal).toHaveCount(0)
  })

  test('H-DSX3D-3: modal 開啟時按 Esc 會關閉（釋放唯一 WebRTC 觀看者名額的快速手段）', async ({ page }) => {
    await gotoWorksheet(page, DSX_UI_URL)

    await page.getByTestId('dsx-ui-entry-btn').click()
    await page.getByTestId('dsx-ui-confirm-proceed').click()
    const modal = page.getByTestId('dsx-ui-modal')
    await expect(modal).toBeVisible()

    await page.keyboard.press('Escape')
    await expect(modal).toHaveCount(0)
  })

  test('H-DSX3D-2: 未設定網址（url=null）→ 入口 disabled 並顯示原因', async ({ page }) => {
    await gotoWorksheet(page, null)

    const entry = page.getByTestId('dsx-ui-entry-btn')
    await expect(entry).toBeDisabled()
    await expect(page.getByTestId('dsx-ui-unavailable-reason')).toBeVisible()
  })

  test('H-DSX3D-4: viewer（無編輯權限）進到唯讀工時表 → 看不到 DSX 3D 入口', async ({ page }) => {
    // 「編輯工時表」按鈕只依 isLatest 停用、不看 canEdit，viewer 進得來但是唯讀模式；
    // DsxUiEntry 會搶走唯一 WebRTC 觀看者名額，不該讓最低權限的人有這個能力。
    await gotoWorksheet(page, DSX_UI_URL, VIEWER_ME)
    await expect(page.getByTestId('dsx-ui-entry-btn')).toHaveCount(0)
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

  test('G-03-3: viewer 不顯示「新建案件」按鈕（RBAC gating）', async ({ page }) => {
    await setupRoutes(page, VIEWER_ME, MOCK_CASES_DRAFT)
    await gotoAndWait(page)
    await clickNavAndWait(page, /分析案件/)
    await expect(page.getByRole('button', { name: '＋ 新建案件' })).not.toBeVisible()
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
