/**
 * 英文覆核頁（ADR-032 D6，Phase B 前端半部）—— Type A（Mocked-API）。
 *
 * 覆蓋：analyst+ 入口可見／viewer 看不到入口、摘要數字（整體＋依 entity_type）、
 * 待審清單、entity_type／status 篩選（含請求 query 契約）、`source_changed` 的
 * 視覺標示、以及「本輪唯讀」的消極斷言（沒有標記已覆核的按鈕／文案）。
 *
 * 執行：E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test i18n-review.spec.ts
 */
import { test, expect, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ANALYST_ME = { employee_no: 'TEST_ANALYST', roles: ['analyst'], level: 1, locale: 'zh-TW' }
const VIEWER_ME = { employee_no: 'TEST_VIEWER', roles: [], level: 0, locale: 'zh-TW' }

/**
 * 待審清單 fixture：涵蓋三種 entity_type、三種 status，以及
 * `source_changed` 為 true／false 的組合（含「unreviewed 但 source_changed」——
 * 比單純 unreviewed 更急的那一種，見 ADR-032 D6 補記）。
 */
const ALL_ITEMS = [
  {
    entity_type: 'rule_option', scope_key: 'b:b_bend', field: 'label',
    status: 'never_translated', rule_set_code: 'MINIMOST_FACTORY_V2',
    source_zh: '起身或彎腰/坐', target_en: null, source_changed: false,
    review_source: null, translated_by: null, translated_at: null,
    reviewed_by: null, reviewed_at: null,
  },
  {
    entity_type: 'rule_option', scope_key: 'g:g_grasp', field: 'label',
    status: 'unreviewed', rule_set_code: 'MINIMOST_FACTORY_V2',
    source_zh: '抓握', target_en: 'grasp', source_changed: false,
    review_source: 'machine', translated_by: 'machine:mock-mt-v1', translated_at: '2026-08-18T12:00:00Z',
    reviewed_by: null, reviewed_at: null,
  },
  {
    entity_type: 'rule_option', scope_key: 'x:x_dispense', field: 'label',
    status: 'stale', rule_set_code: 'MINIMOST_FACTORY_V2',
    source_zh: '並點膠', target_en: 'dispense glue', source_changed: true,
    review_source: 'human', translated_by: 'IEC141289', translated_at: '2026-07-01T00:00:00Z',
    reviewed_by: 'IEC141289', reviewed_at: '2026-07-01T00:00:00Z',
  },
  {
    entity_type: 'vocab_item', scope_key: 'vocab-uuid-1', field: 'name',
    status: 'unreviewed', rule_set_code: null,
    source_zh: '假DIMM', target_en: 'dummy DIMM', source_changed: true,
    review_source: 'machine', translated_by: 'machine:mock-mt-v1', translated_at: '2026-08-10T00:00:00Z',
    reviewed_by: null, reviewed_at: null,
  },
  {
    entity_type: 'motion_template', scope_key: 'tmpl-uuid-1', field: 'name',
    status: 'unreviewed', rule_set_code: null,
    source_zh: '貼標籤', target_en: 'stick label', source_changed: false,
    review_source: 'legacy_seed', translated_by: 'legacy:dev_seed_templates.py', translated_at: '2026-06-01T00:00:00Z',
    reviewed_by: null, reviewed_at: null,
  },
] as const

function summaryFor(entityType?: string) {
  const rows = entityType ? ALL_ITEMS.filter(i => i.entity_type === entityType) : ALL_ITEMS
  const pending = rows.length // fixture 全部都是待審（沒有已覆核列，貼近本輪機翻先全灌未覆核的現況）
  return { total: rows.length, reviewed: rows.length - pending, pending }
}

interface Captured { method: string; url: string }

async function setup(page: Page, me: Record<string, unknown> = ANALYST_ME) {
  const seen: Captured[] = []
  // S10：`**/api/**` 在 dev 模式會誤中自己的原始碼路徑（如 `/src/shared/api/client.ts`）；
  // 與多數既有 spec（smoke／d10-import-match／d11-retired-badge／ux-compliance）對齊，
  // 只攔真正的 API 路徑。
  await page.route('/api/**', route => {
    const req = route.request()
    const url = req.url()
    const method = req.method()
    seen.push({ method, url })
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (url.includes('/api/v2/me')) return json(me)

    if (url.includes('/api/v2/i18n/review/summary')) {
      const u = new URL(url)
      return json(summaryFor(u.searchParams.get('entity_type') ?? undefined))
    }

    if (url.includes('/api/v2/i18n/review/pending')) {
      const u = new URL(url)
      const et = u.searchParams.get('entity_type')
      const st = u.searchParams.get('status')
      let rows: unknown[] = [...ALL_ITEMS]
      if (et) rows = rows.filter((r: any) => r.entity_type === et)
      if (st) rows = rows.filter((r: any) => r.status === st)
      return json(rows)
    }

    // 其他 tab 的資料源（詞彙庫／範本庫）——不是本輪重點，回空清單即可
    if (url.match(/\/api\/v2\/vocab(\?|$)/)) return json([])
    if (url.includes('/api/v2/motion-templates')) return json([])

    if (method !== 'GET') return json({ detail: `未預期的寫入：${method} ${url}` }, 500)
    return json([])
  })
  return seen
}

async function openI18nReviewTab(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: /主數據管理/ }).first().click()
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: '英文覆核' }).click()
  await page.waitForLoadState('networkidle')
}

test.describe('§I18N-01 入口角色 gating', () => {
  test('I18N-01-1: analyst 看得到「主數據管理」入口與「英文覆核」分頁', async ({ page }) => {
    await setup(page, ANALYST_ME)
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('button', { name: /主數據管理/ })).toBeVisible()
    await page.getByRole('button', { name: /主數據管理/ }).first().click()
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('button', { name: '英文覆核' })).toBeVisible()
  })

  test('I18N-01-2: viewer 看不到「主數據管理」入口（因此也到不了英文覆核分頁）', async ({ page }) => {
    await setup(page, VIEWER_ME)
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // 正向錨點：先確認側欄真的渲染完成（viewer 看得到不需要 minRole 的「MOST 工作台」，
    // 見 Sidebar.tsx PRIMARY_NAV），下面的消極斷言才不會對著還沒渲染出來的畫面恆真通過。
    await expect(page.getByRole('button', { name: /MOST 工作台/ })).toBeVisible()

    await expect(page.getByRole('button', { name: /主數據管理/ })).not.toBeVisible()
  })
})

test.describe('§I18N-02 摘要與清單', () => {
  test('I18N-02-1: 摘要區顯示整體與依 entity_type 的覆核進度數字', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    // 整體：5 筆全部待審 → 0/5
    await expect(page.getByTestId('i18n-summary-overall')).toContainText('0/5')
    // 依類型：rule_option 3 筆、vocab_item 1 筆、motion_template 1 筆
    await expect(page.getByTestId('i18n-summary-rule_option')).toContainText('0/3')
    await expect(page.getByTestId('i18n-summary-vocab_item')).toContainText('0/1')
    await expect(page.getByTestId('i18n-summary-motion_template')).toContainText('0/1')
  })

  test('I18N-02-2: 清單顯示中文來源、英文譯文與狀態徽章', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    const row = page.getByTestId('i18n-row-rule_option:g:g_grasp:label')
    await expect(row).toBeVisible()
    await expect(row.getByText('抓握')).toBeVisible()
    await expect(row.getByText('grasp')).toBeVisible()
    await expect(row.getByText('未覆核')).toBeVisible()

    // 尚未翻譯的列：英文欄顯示「（尚未翻譯）」，不是空白或 null 字樣
    const untranslated = page.getByTestId('i18n-row-rule_option:b:b_bend:label')
    await expect(untranslated.getByText('（尚未翻譯）')).toBeVisible()
    await expect(untranslated.getByText('尚未翻譯').first()).toBeVisible() // 狀態徽章
  })
})

test.describe('§I18N-03 篩選', () => {
  test('I18N-03-1: 依 entity_type 篩選送出正確 query，清單只剩該類型', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    await page.getByLabel('物件類型').selectOption('vocab_item')
    await page.waitForLoadState('networkidle')

    await expect(page.getByTestId('i18n-row-vocab_item:vocab-uuid-1:name')).toBeVisible()
    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label')).toHaveCount(0)

    const pendingReqs = seen.filter(w => w.url.includes('/i18n/review/pending') && w.url.includes('entity_type=vocab_item'))
    expect(pendingReqs.length).toBeGreaterThan(0)
  })

  test('I18N-03-2: 依 status=stale 篩選送出正確 query，清單只剩過期項目', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    await page.getByLabel('狀態').selectOption('stale')
    await page.waitForLoadState('networkidle')

    await expect(page.getByTestId('i18n-row-rule_option:x:x_dispense:label')).toBeVisible()
    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label')).toHaveCount(0)

    const pendingReqs = seen.filter(w => w.url.includes('/i18n/review/pending') && w.url.includes('status=stale'))
    expect(pendingReqs.length).toBeGreaterThan(0)
  })

  test('I18N-03-3: 搜尋框可用（前端子字串篩選中文來源／英文譯文）', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    await page.getByPlaceholder('搜尋中文來源／英文譯文…').fill('DIMM')
    await expect(page.getByTestId('i18n-row-vocab_item:vocab-uuid-1:name')).toBeVisible()
    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label')).toHaveCount(0)
  })
})

test.describe('§I18N-04 source_changed 視覺標示', () => {
  test('I18N-04-1: source_changed=true 的列有醒目徽章；false 的列沒有', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    // fixture 中 source_changed=true 的兩列：x:x_dispense（stale）與 vocab-uuid-1（unreviewed 但來源已變）
    await expect(page.getByTestId('i18n-row-rule_option:x:x_dispense:label').getByTestId('i18n-source-changed-badge')).toBeVisible()
    await expect(page.getByTestId('i18n-row-vocab_item:vocab-uuid-1:name').getByTestId('i18n-source-changed-badge')).toBeVisible()

    // source_changed=false 的列（剛翻好、來源沒變過）不該出現這個徽章
    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label').getByTestId('i18n-source-changed-badge')).toHaveCount(0)
    await expect(page.getByTestId('i18n-row-motion_template:tmpl-uuid-1:name').getByTestId('i18n-source-changed-badge')).toHaveCount(0)

    // 全頁徽章總數＝2（不多不少，避免「隨便都顯示」空洞通過）
    await expect(page.getByTestId('i18n-source-changed-badge')).toHaveCount(2)
  })

  test('I18N-04-2: unreviewed 且 source_changed=true 時，狀態文字仍是「未覆核」（不是第四個 status 值）', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    const row = page.getByTestId('i18n-row-vocab_item:vocab-uuid-1:name')
    await expect(row.getByText('未覆核')).toBeVisible()
    await expect(row.getByTestId('i18n-source-changed-badge')).toBeVisible()
  })
})

test.describe('§I18N-05 唯讀（本輪無寫入端點）', () => {
  test('I18N-05-1: 頁面不出現「標記已覆核」或任何寫入按鈕/文案', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    // 正向錨點（複審發現的恆真斷言修復）：先確認清單真的渲染完成，才做下面的消極斷言。
    // 沒有這一步，`toHaveCount(0)` 在畫面（甚至整個分頁）都還沒渲染出來時也會通過，
    // 塞一個真的寫入按鈕進頁面也抓不到——複審已用這個手法連續 4 次證明恆真。
    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label')).toBeVisible()

    await expect(page.getByRole('button', { name: /標記.*已覆核/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /覆核完成/ })).toHaveCount(0)
    await expect(page.getByText(/已覆核完成/)).toHaveCount(0)

    // 沒有任何非 GET 打去 i18n 端點
    const writes = seen.filter(w => w.url.includes('/i18n/') && w.method !== 'GET')
    expect(writes).toHaveLength(0)
  })

  test('I18N-05-2: 頁面明白標示唯讀（尚無標記完成功能）', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)
    await expect(page.getByText(/尚未開放/)).toBeVisible()
  })
})

// ══════════════════════════════════════════════════════════════════════════
// §I18N-06 唯讀 source-level 守衛（S1 複審建議：比 e2e 消極斷言更根本的機制）
//
// I18N-05-1／I18N-05-2 只斷言「畫面上看不到寫入 UI」，會被文案措辭或渲染時機
// 影響（複審已證實 I18N-05-1 曾經恆真）。這裡改成掃原始碼字面：唯讀頁只該
// import GET 用的 `apiGet`，一旦有人 import 了 `apiPost`/`apiPut`/`apiPatch`/
// `apiDelete`，不管有沒有接上 UI、不管畫面斷言測不測得到，都算違反「本輪唯讀」
// 這個承諾。同一套 grep 型守衛慣例見後端 `tests/unit/test_i18n_en_field_isolation.py`
// （I3：`_en` 欄位不得進入決定 TMU 的路徑）。
//
// 這些是純 Node 測試，不用 `page` fixture，不需要瀏覽器／伺服器即可跑。
// ══════════════════════════════════════════════════════════════════════════
test.describe('§I18N-06 唯讀 source-level 守衛', () => {
  const HERE = path.dirname(fileURLToPath(import.meta.url))
  const GUARDED_FILES = [
    path.resolve(HERE, '../src/features/dictionaries/I18nReviewTab.tsx'),
    path.resolve(HERE, '../src/features/dictionaries/i18nReviewApi.ts'),
  ]
  const FORBIDDEN_IMPORTS = ['apiPost', 'apiPut', 'apiPatch', 'apiDelete']

  function scan(files: string[]): Array<{ file: string; hit: string }> {
    const hits: Array<{ file: string; hit: string }> = []
    for (const file of files) {
      const text = fs.readFileSync(file, 'utf-8')
      for (const forbidden of FORBIDDEN_IMPORTS) {
        if (text.includes(forbidden)) hits.push({ file, hit: forbidden })
      }
    }
    return hits
  }

  test('I18N-06-1: 守衛對象檔案確實存在（後設守衛，避免路徑漂移後測試形同虛設）', () => {
    for (const file of GUARDED_FILES) {
      expect(fs.existsSync(file), `${file} 不存在，守衛對象的路徑可能已經漂移`).toBe(true)
    }
  })

  test('I18N-06-2: I18nReviewTab.tsx／i18nReviewApi.ts 不 import 任何寫入 API helper', () => {
    const hits = scan(GUARDED_FILES)
    expect(
      hits,
      `違反「本輪唯讀」——以下檔案出現了寫入 API helper：${JSON.stringify(hits)}`,
    ).toEqual([])
  })

  test('I18N-06-3: 掃描器本身會抓到合成違規（非恆真的空清單斷言）', () => {
    const tmpFile = path.join(HERE, `.i18n-guard-mutation-${process.pid}.tmp.ts`)
    fs.writeFileSync(
      tmpFile,
      "import { apiPost } from '../../shared/api/client'\n// 合成違規，僅用於證明 scan() 真的會命中，測完即刪\n",
    )
    try {
      const hits = scan([tmpFile])
      expect(hits).toEqual([{ file: tmpFile, hit: 'apiPost' }])
    } finally {
      fs.unlinkSync(tmpFile)
    }
  })
})
