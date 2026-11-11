/**
 * ADR-023 §3.4-4 / D11-FE：工序表「使用已下架規則版本」警示徽章。
 *
 * 契約：GET /worksheets/{id} 回應帶 `default_rule_set: {code, status, is_active} | null`。
 * - status === 'retired' → 徽章可見且含 code
 * - published / draft / null → 徽章**不可見**（前端只讀 status，不自行判斷版本新舊）
 *
 * 三情境互為對照：只測 retired 顯示無法證明 published/null 不會誤顯示。
 *
 * 執行：E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test d11-retired-badge.spec.ts
 */
import { test, expect, type Page } from '@playwright/test'

const ADMIN_ME = { employee_no: 'IEC141289', roles: ['admin'], level: 3 }

const MOCK_CASES = {
  total: 1,
  items: [{
    process_version_id: 'pv-001', worksheet_id: 'ws-001', version_no: 'v1', status: 'draft',
    site_id: 'st-1', site_name: 'Site A', product_id: 'p1', product_name: 'Product X',
    sku_id: 'sk1', sku_name: 'SKU 001', process_name: '組裝站作業', total_tmu: 0,
    created_at: '2026-01-01T00:00:00Z', approved_at: null, model_label: null, version_count: 1,
    versions: [{ process_version_id: 'pv-001', worksheet_id: 'ws-001', version_no: 'v1',
      status: 'draft', total_tmu: 0, created_at: '2026-01-01T00:00:00Z', approved_at: null }],
  }],
}

const MOCK_OPTS = {
  code: 'MINIMOST_FACTORY_V2', multiplier: 1,
  a_bands: { reach: [{ max_value: 5, index: 2 }], twist: [{ max_value: null, index: 0 }], foot: [{ max_value: null, index: 0 }] },
  b: [], g: [{ code: 'g_simple', label: '簡單抓握', modifier_key: null, requires_modifier: false }],
  p_bases: [{ code: 'p_put', label: '放置', label_en: 'Put' }], p_addons: [],
  m_verbs: [{ code: 'm_push', label: '推', pricing_kind: 'distance_ladder' }],
  x: [{ code: 'x_none', label: '無機器時間', mode: 'none' }],
  i: [{ code: 'i_none', label: '無', label_en: 'None' }],
}

type Drs = { code: string; status: string; is_active: boolean } | null

function installRoutes(page: Page, defaultRuleSet: Drs) {
  page.route('/api/**', route => {
    const url = route.request().url()
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (url.includes('/api/v2/me')) return json(ADMIN_ME)
    if (url.includes('/api/v2/rule-sets/active'))
      return json({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' })
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) return json(MOCK_OPTS)
    if (url.match(/\/api\/v2\/rule-sets(\?|$)/))
      return json([{ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2',
        status: 'published', multiplier: 1, is_active: true, provenance: 'certified_import',
        created_at: '2026-07-07T10:24:25Z', notes: null }])
    if (url.match(/\/api\/v2\/cases(\?|$)/)) return json(MOCK_CASES)
    if (url.includes('/api/v2/audit-log')) return json({ total: 0, items: [] })
    if (url.includes('/api/v2/worksheets/'))
      return json({ worksheet_id: 'ws-001', status: 'draft', total_tmu: 0, rows: [], default_rule_set: defaultRuleSet })

    if (route.request().method() === 'GET') return json([])
    return json({ detail: `unexpected ${route.request().method()} ${url}` }, 500)
  })
}

async function enterWorksheetContext(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: /分析案件/ }).click()
  await page.waitForLoadState('networkidle')
  await page.getByText('組裝站作業').click()
  await page.getByRole('button', { name: '編輯工時表' }).click()
  await page.waitForLoadState('networkidle')
}

test('D11-d1: default_rule_set.status===retired → 徽章可見且含 code', async ({ page }) => {
  installRoutes(page, { code: 'MINIMOST_FACTORY_V0', status: 'retired', is_active: false })
  await enterWorksheetContext(page)

  const badge = page.getByTestId('worksheet-retired-ruleset-badge')
  await expect(badge).toBeVisible()
  await expect(badge).toContainText('已下架')
  await expect(badge).toContainText('MINIMOST_FACTORY_V0')      // 必須帶 code
  // 語意：提示升級，不得用「錯誤/失效」字眼
  await expect(badge).not.toContainText('錯誤')
  await expect(badge).not.toContainText('失效')
  await page.screenshot({ path: 'd11-retired-badge.png', fullPage: true })
})

test('D11-d2: default_rule_set.status===published → 徽章不可見（與 retired 互為對照）', async ({ page }) => {
  installRoutes(page, { code: 'MINIMOST_FACTORY_V2', status: 'published', is_active: true })
  await enterWorksheetContext(page)

  // 編輯器已載入（確認頁面真的進到工序表情境，不是因為沒渲染而看不到徽章）
  await expect(page.getByRole('heading', { name: '編輯一條工序' })).toBeVisible()
  await expect(page.getByTestId('worksheet-retired-ruleset-badge')).toHaveCount(0)
})

test('D11-d3: default_rule_set===null → 徽章不可見、不報錯', async ({ page }) => {
  installRoutes(page, null)
  await enterWorksheetContext(page)

  await expect(page.getByRole('heading', { name: '編輯一條工序' })).toBeVisible()
  await expect(page.getByTestId('worksheet-retired-ruleset-badge')).toHaveCount(0)
})
