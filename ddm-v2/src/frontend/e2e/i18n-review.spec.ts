/**
 * 英文覆核頁（ADR-032 D6）—— Type A（Mocked-API）。
 *
 * 覆蓋：analyst+ 入口可見／viewer 看不到入口、摘要數字（整體＋依 entity_type）、
 * 待審清單、entity_type／status 篩選（含請求 query 契約）、`source_changed`／
 * `target_changed` 的視覺標示、逐條覆核（含修正譯文）、指派／取消指派，
 * 以及**寫入面守衛**（§I18N-05 網路層／§I18N-07 原始碼層，見那兩段的大段註解——
 * 它們取代了 Phase B「本輪唯讀」的兩組守衛）。
 *
 * 執行：E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test i18n-review.spec.ts
 */
import { test, expect, type Page } from '@playwright/test'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ANALYST_ME = { employee_no: 'TEST_ANALYST', roles: ['analyst'], level: 1, locale: 'zh-TW' }
const VIEWER_ME = { employee_no: 'TEST_VIEWER', roles: [], level: 0, locale: 'zh-TW' }

/**
 * 待審清單 fixture：涵蓋三種 entity_type、三種 status、兩種 field（label／sentence），
 * 以及 `source_changed`／`target_changed`／`assigned_to` 的各種組合
 * （含「unreviewed 但 source_changed」——比單純 unreviewed 更急的那一種，見 D6 補記）。
 */
const ALL_ITEMS = [
  {
    entity_type: 'rule_option', scope_key: 'b:b_bend', field: 'label',
    status: 'never_translated', rule_set_code: 'MINIMOST_FACTORY_V2',
    source_zh: '起身或彎腰/坐', target_en: null, source_is_fallback: false,
    source_changed: false, target_changed: false,
    review_source: null, translated_by: null, translated_at: null,
    reviewed_by: null, reviewed_at: null, assigned_to: null, assigned_at: null,
  },
  {
    entity_type: 'rule_option', scope_key: 'g:g_grasp', field: 'label',
    status: 'unreviewed', rule_set_code: 'MINIMOST_FACTORY_V2',
    source_zh: '抓握', target_en: 'grasp', source_is_fallback: false,
    source_changed: false, target_changed: false,
    review_source: 'machine', translated_by: 'machine:mock-mt-v1', translated_at: '2026-08-18T12:00:00Z',
    reviewed_by: null, reviewed_at: null, assigned_to: null, assigned_at: null,
  },
  {
    entity_type: 'rule_option', scope_key: 'x:x_dispense', field: 'label',
    status: 'stale', rule_set_code: 'MINIMOST_FACTORY_V2',
    source_zh: '並點膠', target_en: 'dispense glue', source_is_fallback: false,
    source_changed: true, target_changed: false,
    review_source: 'human', translated_by: 'IEC141289', translated_at: '2026-07-01T00:00:00Z',
    reviewed_by: 'IEC141289', reviewed_at: '2026-07-01T00:00:00Z', assigned_to: null, assigned_at: null,
  },
  {
    // target_changed（v2_0043）：上次覆核後有人動過英文——與 source_changed 正交。
    // 同時是「已指派給我」的那一列（給「只看指派給我」篩選用）。
    entity_type: 'rule_option', scope_key: 'g:g_touch', field: 'label',
    status: 'stale', rule_set_code: 'MINIMOST_FACTORY_V2',
    source_zh: '接觸', target_en: 'touch', source_is_fallback: false,
    source_changed: false, target_changed: true,
    review_source: 'human', translated_by: 'IEC141289', translated_at: '2026-07-01T00:00:00Z',
    reviewed_by: 'IEC141289', reviewed_at: '2026-07-01T00:00:00Z',
    assigned_to: 'TEST_ANALYST', assigned_at: '2026-08-19T00:00:00Z',
  },
  {
    // field='sentence'：D6 分母修正（63→126）之後才進得了清單的那一半。
    // `m_hand` 是 D7.6「刻意不入句」的 7 條之一——中文句面本身為空（`source_zh` 顯示的是
    // 標籤，`source_is_fallback: true`），所以英文句面空字串是合法值。
    entity_type: 'rule_option', scope_key: 'm:m_hand', field: 'sentence',
    status: 'never_translated', rule_set_code: 'MINIMOST_FACTORY_V2',
    source_zh: '手度', target_en: null, source_is_fallback: true,
    source_changed: false, target_changed: false,
    review_source: null, translated_by: null, translated_at: null,
    reviewed_by: null, reviewed_at: null, assigned_to: null, assigned_at: null,
  },
  {
    entity_type: 'vocab_item', scope_key: 'vocab-uuid-1', field: 'name',
    status: 'unreviewed', rule_set_code: null,
    source_zh: '假DIMM', target_en: 'dummy DIMM', source_is_fallback: false,
    source_changed: true, target_changed: false,
    review_source: 'machine', translated_by: 'machine:mock-mt-v1', translated_at: '2026-08-10T00:00:00Z',
    reviewed_by: null, reviewed_at: null, assigned_to: null, assigned_at: null,
  },
  {
    entity_type: 'motion_template', scope_key: 'tmpl-uuid-1', field: 'name',
    status: 'unreviewed', rule_set_code: null,
    source_zh: '貼標籤', target_en: 'stick label', source_is_fallback: false,
    source_changed: false, target_changed: false,
    review_source: 'legacy_seed', translated_by: 'legacy:dev_seed_templates.py', translated_at: '2026-06-01T00:00:00Z',
    reviewed_by: null, reviewed_at: null, assigned_to: null, assigned_at: null,
  },
] as const

/**
 * 有狀態的 mock 後端（2026-08-20 覆核修正）。
 *
 * **為什麼非有狀態不可**：先前 `summaryFor()` 恆回 `{total:n, reviewed:0, pending:n}`、
 * `/pending` 恆回全量，所以覆核前後畫面數字與列數都一樣——把 `i18nReviewApi.ts` 兩個
 * mutation 的 `onSuccess: invalidate` 整段刪掉，全部測試依然綠。D6 的完成判準原文是
 * 「覆核進度是**可見且可下降**的數字」，而那個「可下降」當時沒有任何一條測試看守，
 * 正好就是這一輪要修的症狀（使用者按了「標記已覆核」畫面數字不動）。
 *
 * 現在：`mark-reviewed` 把該列移出 `rows`（＝離開待審清單），`/pending` 回 `rows`，
 * 摘要的**分母固定為 fixture 全量、分子＝已離開清單的列數**——覆核一條就是
 * 0/7 → 1/7；快取沒失效的話畫面會停在 0/7 且該列還在（見 I18N-06-9）。
 * `assign` 同樣就地改寫該列，讓「指派後畫面顯示的人」也是真的重抓來的。
 */
function makeMockBackend(base: readonly any[]) {
  const rows: any[] = base.map(r => ({ ...r }))
  const scoped = (arr: readonly any[], entityType?: string) =>
    entityType ? arr.filter((i: any) => i.entity_type === entityType) : arr
  const indexOf = (ref: any) =>
    rows.findIndex(
      r => r.entity_type === ref?.entity_type && r.scope_key === ref?.scope_key && r.field === ref?.field,
    )
  return {
    /** 目前仍待審的列（`/pending` 的資料源）。 */
    pending(entityType?: string | null, status?: string | null): any[] {
      let out = [...rows]
      if (entityType) out = out.filter(r => r.entity_type === entityType)
      if (status) out = out.filter(r => r.status === status)
      return out
    },
    summaryFor(entityType?: string) {
      const total = scoped(base, entityType).length
      const pending = scoped(rows, entityType).length
      return { total, reviewed: total - pending, pending }
    },
    find(ref: any): any | undefined {
      const i = indexOf(ref)
      return i >= 0 ? rows[i] : undefined
    },
    /** 覆核成功 ＝ 這一列離開待審清單（摘要分子 +1）。 */
    markReviewed(ref: any): void {
      const i = indexOf(ref)
      if (i >= 0) rows.splice(i, 1)
    },
    /** 指派不改變 status，只改這一列的 assigned_to（ADR-032 D6）。 */
    assign(ref: any, to: string | null): void {
      const row = this.find(ref)
      if (row) {
        row.assigned_to = to
        row.assigned_at = to ? '2026-08-20T00:00:00Z' : null
      }
    },
  }
}

interface Captured { method: string; url: string; body: any }

/** 讓單一測試改寫某支寫入端點的回應（模擬後端 409／422）。 */
interface SetupOpts {
  me?: Record<string, unknown>
  /** 覆寫待審清單 fixture（預設 `ALL_ITEMS`）——給需要不同 `source_is_fallback` 等欄位組合的單一測試用。 */
  items?: readonly any[]
  /** 回 null ＝走預設成功回應。 */
  onWrite?: (url: string, body: any) => { status: number; body: unknown } | null
}

async function setup(page: Page, opts: SetupOpts = {}) {
  const me = opts.me ?? ANALYST_ME
  const backend = makeMockBackend(opts.items ?? ALL_ITEMS)
  const seen: Captured[] = []
  // S10：`**/api/**` 在 dev 模式會誤中自己的原始碼路徑（如 `/src/shared/api/client.ts`）；
  // 與多數既有 spec（smoke／d10-import-match／d11-retired-badge／ux-compliance）對齊，
  // 只攔真正的 API 路徑。
  await page.route('/api/**', route => {
    const req = route.request()
    const url = req.url()
    const method = req.method()
    let body: any = null
    if (method !== 'GET') {
      try { body = req.postDataJSON() } catch { body = req.postData() }
    }
    seen.push({ method, url, body })
    const json = (payload: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })

    if (url.includes('/api/v2/me')) return json(me)

    if (url.includes('/api/v2/i18n/review/summary')) {
      const u = new URL(url)
      return json(backend.summaryFor(u.searchParams.get('entity_type') ?? undefined))
    }

    if (url.includes('/api/v2/i18n/review/pending')) {
      const u = new URL(url)
      return json(backend.pending(u.searchParams.get('entity_type'), u.searchParams.get('status')))
    }

    if (method === 'POST' && url.includes('/api/v2/i18n/review/')) {
      const override = opts.onWrite?.(url, body)
      if (override) return json(override.body, override.status)   // 錯誤路徑：狀態不變
      const row = backend.find(body)
      if (url.includes('mark-reviewed')) {
        backend.markReviewed(body)
        return json({
          ...row, status: null, target_en: body?.target_en ?? row?.target_en,
          review_source: 'human', reviewed_by: me.employee_no, reviewed_at: '2026-08-20T00:00:00Z',
        })
      }
      backend.assign(body, body?.assigned_to ?? null)
      return json({ ...row, assigned_to: body?.assigned_to ?? null, assigned_at: body?.assigned_to ? '2026-08-20T00:00:00Z' : null })
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

/**
 * viewer 版：側欄沒有「主數據管理」按鈕（minRole:'analyst'），所以改用 App 既有的
 * `ddm:switch-tab` 事件直接把分頁切過去。**這是刻意的**——只驗「viewer 點不到入口」
 * 等於只驗側欄；把 viewer 真的送進這一頁，才驗得到頁內第二層 `canEdit(me)` gating
 * （寫入按鈕不得出現）。兩層擋的是不同的事，失效模式也不同。
 */
async function openI18nReviewTabAsViewer(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'dictionaries' })))
  await page.getByRole('button', { name: '英文覆核' }).click()
  await page.waitForLoadState('networkidle')
}

test.describe('§I18N-01 入口角色 gating', () => {
  test('I18N-01-1: analyst 看得到「主數據管理」入口與「英文覆核」分頁', async ({ page }) => {
    await setup(page, { me: ANALYST_ME })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('button', { name: /主數據管理/ })).toBeVisible()
    await page.getByRole('button', { name: /主數據管理/ }).first().click()
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('button', { name: '英文覆核' })).toBeVisible()
  })

  test('I18N-01-2: viewer 看不到「主數據管理」入口（因此也到不了英文覆核分頁）', async ({ page }) => {
    await setup(page, { me: VIEWER_ME })
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

    // 整體：7 筆全部待審 → 0/7
    await expect(page.getByTestId('i18n-summary-overall')).toContainText('0/7')
    // 依類型：rule_option 5 筆、vocab_item 1 筆、motion_template 1 筆
    await expect(page.getByTestId('i18n-summary-rule_option')).toContainText('0/5')
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

  test('I18N-02-3: label 與 sentence 兩種 field 分得出來（D6 分母 63→126 的那一半）', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label').getByText('下拉標籤')).toBeVisible()
    await expect(page.getByTestId('i18n-row-rule_option:m:m_hand:sentence').getByText('敘事句面')).toBeVisible()
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

  test('I18N-03-4: 「只看指派給我」只留下 assigned_to ＝本人的列（前端篩選，不打新端點）', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    await page.getByTestId('i18n-mine-only').check()
    await expect(page.getByTestId('i18n-row-rule_option:g:g_touch:label')).toBeVisible()
    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label')).toHaveCount(0)
  })
})

test.describe('§I18N-04 source_changed／target_changed 視覺標示', () => {
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

  test('I18N-04-3: target_changed 是與 source_changed 正交的第二個徽章（不共用、不合併）', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    const touched = page.getByTestId('i18n-row-rule_option:g:g_touch:label')
    await expect(touched.getByTestId('i18n-target-changed-badge')).toBeVisible()
    await expect(touched.getByTestId('i18n-source-changed-badge')).toHaveCount(0) // 這一列只有譯文變了
    await expect(touched.getByText('已過期')).toBeVisible()                        // 兩者都歸 stale

    // 反向：只有來源變的那一列不得出現譯文徽章
    await expect(page.getByTestId('i18n-row-rule_option:x:x_dispense:label').getByTestId('i18n-target-changed-badge')).toHaveCount(0)
    await expect(page.getByTestId('i18n-target-changed-badge')).toHaveCount(1)
  })
})

// ══════════════════════════════════════════════════════════════════════════
// §I18N-05 寫入面守衛（取代 Phase B 的「本輪唯讀」消極斷言）
//
// **為什麼原本的守衛必須被取代**：Phase B 交付時後端只有 GET 兩支端點，所以
// I18N-05-1 斷言「頁面不出現『標記已覆核』或任何寫入按鈕／文案」、I18N-05-2 斷言
// 頁面明白標示「尚未開放」。這兩條守的是一個**已經過期的事實**（D6 後半的
// mutation 端點已於 2026-08-20 落地），它們現在會擋住正確的實作。
//
// **新守衛守什麼（等強替代，不是放寬）**：唯讀時期真正在保護的是「這一頁不得
// 產生未經 D4／D6 守門的寫入」。那個保護在有了寫入功能之後**變得更重要而不是消失**，
// 只是不變式從「零寫入」換成「寫入只能走這三支端點、且只有 analyst+ 看得到入口、
// 且沒有批次核准」：
//   05-1  網路層：全頁所有非 GET 請求都必須落在寫入白名單內（正向錨點：至少 1 筆寫入）。
//   05-2  角色：viewer 進到這一頁也看不到任何寫入入口（正向錨點：清單本身仍看得到）。
//   05-3  反橡皮圖章：沒有全選 / 批次核准入口（ADR-032 R1／I5；正向錨點：逐列入口存在）。
// ══════════════════════════════════════════════════════════════════════════

/**
 * 允許的寫入端點（ADR-032 D6 後半的三支）。這份清單與 `i18nReviewApi.ts` 檔頭
 * 那份是同一個政策的兩面：這裡守「實際飛出去的請求」，§I18N-07 守「原始碼裡的呼叫」。
 */
const ALLOWED_WRITE_PATHS: RegExp[] = [
  /^\/api\/v2\/i18n\/review\/mark-reviewed$/,
  /^\/api\/v2\/i18n\/review\/assign$/,
  /^\/api\/v2\/rule-sets\/[^/]+\/params\/[^/]+\/options\/[^/]+\/en$/,
]

function offAllowlist(seen: Captured[]): Captured[] {
  return seen.filter(w => w.method !== 'GET' && !ALLOWED_WRITE_PATHS.some(re => re.test(new URL(w.url).pathname)))
}

test.describe('§I18N-05 寫入面守衛', () => {
  test('I18N-05-1: 覆核與指派只打白名單內的端點（且真的有寫入發生）', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    // 正向錨點：清單真的渲染完成，下面的消極斷言才不是對著空畫面恆真通過。
    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label')).toBeVisible()

    // **把這一頁的互動面整個點過一遍**，不只點寫入按鈕：白名單斷言只看得到「真的飛
    // 出去的請求」，所以任何沒被點到的 handler 都等於沒被這道守衛檢查。實測把一支
    // `PATCH /api/v2/vocab/{id}` 掛在「複製本列」上，這一條與 §I18N-07 會同時綠
    // （2026-08-20 覆核發現的 M10）——動態白名單必須覆蓋整個互動面才擋得住。
    await page.getByTestId('i18n-open-editor-rule_option:g:g_grasp:label').click()
    await page.getByTestId('i18n-mark-reviewed-rule_option:g:g_grasp:label').click()
    await page.waitForLoadState('networkidle')

    await page.getByTestId('i18n-open-editor-vocab_item:vocab-uuid-1:name').click()
    await page.getByTestId('i18n-assign-me-vocab_item:vocab-uuid-1:name').click()
    await page.waitForLoadState('networkidle')

    // 取消指派（g:g_touch 一開始就指派給 TEST_ANALYST）
    await page.getByTestId('i18n-open-editor-rule_option:g:g_touch:label').click()
    await page.getByTestId('i18n-unassign-rule_option:g:g_touch:label').click()
    await page.waitForLoadState('networkidle')

    // 複製本列／複製全部（純前端剪貼簿操作，本來就不該產生任何請求）
    await page
      .getByTestId('i18n-row-rule_option:x:x_dispense:label')
      .getByRole('button', { name: '複製', exact: true })
      .click()
    await page.getByRole('button', { name: /複製全部/ }).click()
    await page.waitForLoadState('networkidle')

    const writes = seen.filter(w => w.method !== 'GET')
    expect(writes.length, '這一頁應該真的送出過寫入請求，否則下面的白名單斷言是恆真的').toBeGreaterThanOrEqual(2)
    expect(offAllowlist(seen), '出現了白名單以外的寫入請求').toEqual([])
  })

  test('I18N-05-2: viewer 進到這一頁也看不到任何寫入入口', async ({ page }) => {
    const seen = await setup(page, { me: VIEWER_ME })
    await openI18nReviewTabAsViewer(page)

    // 正向錨點：viewer 仍看得到清單（唯讀），所以下面的 count(0) 不是「畫面沒渲染」。
    await expect(page.getByTestId('i18n-row-rule_option:g:g_grasp:label')).toBeVisible()

    await expect(page.getByTestId('i18n-open-editor-rule_option:g:g_grasp:label')).toHaveCount(0)
    // exact:true——分頁標籤「英文覆核」本身含「覆核」二字，子字串比對會誤中它
    await expect(page.getByRole('button', { name: '覆核', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /標記已覆核/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /指派/ })).toHaveCount(0)
    await expect(page.getByTestId('i18n-mine-only')).toHaveCount(0)
    expect(seen.filter(w => w.method !== 'GET')).toHaveLength(0)
  })

  test('I18N-05-3: 沒有批次核准入口（逐條才擋得住 g_grasp/g_touch 那種誤譯）', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    // 正向錨點：逐列覆核入口存在，且數量＝列數（＝真的是「逐條」而不是一顆總按鈕）
    // 用 toHaveCount 而不是 `count()` + toBe：前者會重試等渲染完成，後者是一次性快照
    // （full run 下曾因此在清單還沒繪出時取到 0）。
    await expect(page.locator('[data-testid^="i18n-row-"]')).toHaveCount(ALL_ITEMS.length)
    await expect(page.locator('[data-testid^="i18n-open-editor-"]')).toHaveCount(ALL_ITEMS.length)

    // 消極：沒有全選 checkbox、沒有批次核准按鈕
    await expect(page.getByRole('button', { name: /全部.*覆核|批次|全選/ })).toHaveCount(0)
    await expect(page.locator('table input[type="checkbox"]')).toHaveCount(0)
  })
})

test.describe('§I18N-06 覆核操作', () => {
  test('I18N-06-1: 覆核時修正譯文——payload 帶新的 target_en 與 rule_set_code', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    const key = 'rule_option:g:g_grasp:label'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    await page.getByTestId(`i18n-en-input-${key}`).fill('grasp (firm)')
    await page.getByTestId(`i18n-mark-reviewed-${key}`).click()
    await page.waitForLoadState('networkidle')

    const req = seen.find(w => w.url.includes('mark-reviewed'))
    expect(req?.body).toMatchObject({
      entity_type: 'rule_option', scope_key: 'g:g_grasp', field: 'label',
      rule_set_code: 'MINIMOST_FACTORY_V2', target_en: 'grasp (firm)',
    })
    // 覆核成功後編輯器收起（該列會在下一次 pending 重抓時消失）
    await expect(page.getByTestId(`i18n-editor-${key}`)).toHaveCount(0)
  })

  test('I18N-06-2: 譯文沒改時 target_en 送 null（＝沿用現有譯文，不無謂覆寫）', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    const key = 'rule_option:g:g_grasp:label'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    await page.getByTestId(`i18n-mark-reviewed-${key}`).click()
    await page.waitForLoadState('networkidle')

    const req = seen.find(w => w.url.includes('mark-reviewed'))
    expect(req?.body?.target_en).toBeNull()
  })

  test('I18N-06-3: 沒有譯文的列——「標記已覆核」停用並說明原因（不讓人撞 422 才知道）', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    const key = 'rule_option:b:b_bend:label'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    await expect(page.getByTestId(`i18n-mark-reviewed-${key}`)).toBeDisabled()
    await expect(page.getByTestId(`i18n-blank-blocked-${key}`)).toBeVisible()
    expect(seen.filter(w => w.method !== 'GET')).toHaveLength(0)

    // 填了譯文就解鎖（正向錨點：不是「永遠停用」）
    await page.getByTestId(`i18n-en-input-${key}`).fill('Stand up or bend/sit')
    await expect(page.getByTestId(`i18n-mark-reviewed-${key}`)).toBeEnabled()
  })

  test('I18N-06-4: 句面留空可送出（D7.6 刻意不入句），且顯式送空字串＋前置提示', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    const key = 'rule_option:m:m_hand:sentence'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    // 提示：後端只在中文句面本身為空時接受（前端無法自行判斷，見 I18nReviewTab 檔頭）
    await expect(page.getByTestId(`i18n-blank-sentence-hint-${key}`)).toBeVisible()
    await expect(page.getByTestId(`i18n-mark-reviewed-${key}`)).toBeEnabled()

    await page.getByTestId(`i18n-mark-reviewed-${key}`).click()
    await page.waitForLoadState('networkidle')

    const req = seen.find(w => w.url.includes('mark-reviewed'))
    // 送 null 會被後端解讀成「沿用現有的 NULL」→ 必然 422；空字串才是那個有意義的值
    expect(req?.body?.target_en).toBe('')
  })

  test('I18N-06-5: 後端 409 EN_LABEL_NOT_UNIQUE——訊息（含撞到哪一條）原樣顯示', async ({ page }) => {
    await setup(page, {
      onWrite: (url) => url.includes('mark-reviewed')
        ? {
            status: 409,
            body: { detail: { code: 'EN_LABEL_NOT_UNIQUE', message: "英文標籤 'touch' 與同表既有選項 ['g_touch'] 正規化後相同（g_grasp）：同一參數內英文標籤必須可辨義（ADR-032 I5），請改用不同的字面" },
          } }
        : null,
    })
    await openI18nReviewTab(page)

    const key = 'rule_option:g:g_grasp:label'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    await page.getByTestId(`i18n-en-input-${key}`).fill('touch')
    await page.getByTestId(`i18n-mark-reviewed-${key}`).click()

    const err = page.getByTestId(`i18n-editor-error-${key}`)
    await expect(err).toContainText('EN_LABEL_NOT_UNIQUE')
    await expect(err).toContainText('g_touch') // 使用者要知道跟哪一條撞了
  })

  test('I18N-06-6: 後端 422 I18N_REVIEW_TARGET_MISSING——訊息原樣顯示，編輯器不關', async ({ page }) => {
    await setup(page, {
      onWrite: (url) => url.includes('mark-reviewed')
        ? {
            status: 422,
            body: { error: { code: 'I18N_REVIEW_TARGET_MISSING', message: 'rule_option/m:m_hand/sentence 目前沒有可覆核的英文譯文——要標記已覆核請在同一個請求帶入 `target_en`（不得把空白標成已覆核）。' } },
          }
        : null,
    })
    await openI18nReviewTab(page)

    const key = 'rule_option:m:m_hand:sentence'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    await page.getByTestId(`i18n-mark-reviewed-${key}`).click()

    await expect(page.getByTestId(`i18n-editor-error-${key}`)).toContainText('I18N_REVIEW_TARGET_MISSING')
    await expect(page.getByTestId(`i18n-editor-${key}`)).toBeVisible() // 不關，讓人就地補譯文
  })

  test('I18N-06-7: 指派與取消指派——payload 契約（null ＝取消）', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    const key = 'rule_option:g:g_touch:label'
    await page.getByTestId(`i18n-open-editor-${key}`).click()

    await page.getByTestId(`i18n-assign-input-${key}`).fill('IEC141289')
    await page.getByTestId(`i18n-assign-${key}`).click()
    await page.waitForLoadState('networkidle')
    expect(seen.filter(w => w.url.includes('/review/assign')).at(-1)?.body).toMatchObject({
      entity_type: 'rule_option', scope_key: 'g:g_touch', field: 'label', assigned_to: 'IEC141289',
    })

    await page.getByTestId(`i18n-unassign-${key}`).click()
    await page.waitForLoadState('networkidle')
    expect(seen.filter(w => w.url.includes('/review/assign')).at(-1)?.body?.assigned_to).toBeNull()
  })

  test('I18N-06-9: 覆核成功後摘要數字下降、該列消失（快取失效——D6「可下降」的本體）', async ({ page }) => {
    const seen = await setup(page)
    await openI18nReviewTab(page)

    await expect(page.getByTestId('i18n-summary-overall')).toContainText('0/7')
    await expect(page.getByTestId('i18n-summary-rule_option')).toContainText('0/5')

    const key = 'rule_option:g:g_grasp:label'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    await page.getByTestId(`i18n-mark-reviewed-${key}`).click()

    // 數字真的下降：分子 +1（分母不動——分母是「可譯欄位總數」，不是待審數）
    await expect(page.getByTestId('i18n-summary-overall')).toContainText('1/7')
    await expect(page.getByTestId('i18n-summary-rule_option')).toContainText('1/5')
    // 沒動到的類別不得跟著跳（避免「全部一起亂變」也算通過）
    await expect(page.getByTestId('i18n-summary-vocab_item')).toContainText('0/1')
    // 覆核完的列離開待審清單
    await expect(page.getByTestId(`i18n-row-${key}`)).toHaveCount(0)
    await expect(page.locator('[data-testid^="i18n-row-"]')).toHaveCount(ALL_ITEMS.length - 1)

    // 而且新數字是**重抓**來的，不是前端自己算的：POST 之後必須各有一發 GET。
    // （這一段直接對應 `i18nReviewApi.ts` 兩個 mutation 的 `onSuccess: invalidate`；
    //  把那兩行刪掉，上面的 1/7 與這裡的 GET 斷言都會紅。）
    const postIdx = seen.findIndex(w => w.method === 'POST' && w.url.includes('mark-reviewed'))
    expect(postIdx, '應該送出過 mark-reviewed').toBeGreaterThanOrEqual(0)
    const after = seen.slice(postIdx + 1).filter(w => w.method === 'GET')
    expect(
      after.filter(w => w.url.includes('/i18n/review/summary')).length,
      '覆核成功後必須重抓摘要，否則畫面數字會停在舊值',
    ).toBeGreaterThan(0)
    expect(
      after.filter(w => w.url.includes('/i18n/review/pending')).length,
      '覆核成功後必須重抓待審清單，否則已覆核的列會賴在畫面上',
    ).toBeGreaterThan(0)
  })

  test('I18N-06-10: 中文句面有字的句面列——留空被擋下（`source_is_fallback=false`）', async ({ page }) => {
    // 同一個 scope_key 但中文句面本身**有字**（`source_is_fallback: false`）：這時英文
    // 留空＝漏翻，後端會 422。前端拿 `/pending` 回的這個布林事前擋下，不讓人撞了才知道
    // （對照 I18N-06-4：同一列 `source_is_fallback: true` 時放行且顯式送空字串）。
    const items = ALL_ITEMS.map(i =>
      i.scope_key === 'm:m_hand' ? { ...i, source_is_fallback: false, source_zh: '用手' } : i,
    )
    const seen = await setup(page, { items })
    await openI18nReviewTab(page)

    const key = 'rule_option:m:m_hand:sentence'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    await expect(page.getByTestId(`i18n-blank-sentence-hint-${key}`)).toHaveCount(0)
    await expect(page.getByTestId(`i18n-blank-blocked-${key}`)).toBeVisible()
    await expect(page.getByTestId(`i18n-mark-reviewed-${key}`)).toBeDisabled()
    expect(seen.filter(w => w.method !== 'GET')).toHaveLength(0)

    // 正向錨點：填了譯文就解得開（不是「句面永遠停用」）
    await page.getByTestId(`i18n-en-input-${key}`).fill('by hand')
    await expect(page.getByTestId(`i18n-mark-reviewed-${key}`)).toBeEnabled()
  })

  test('I18N-06-11: 只多打空白不算改動——target_en 送 null，不製造 before==after 的稽核噪音', async ({ page }) => {
    // 後端 `I18nMarkReviewedIn.target_en` 是 `StringConstraints(strip_whitespace=True)`：
    // 送 'grasp ' 進去存成 'grasp'，稽核卻留下一筆 {before:'grasp', after:'grasp'}。
    // 比對與送出都先 trim，把這種噪音擋在前端（buildTargetEn）。
    const seen = await setup(page)
    await openI18nReviewTab(page)

    const key = 'rule_option:g:g_grasp:label'
    await page.getByTestId(`i18n-open-editor-${key}`).click()
    await page.getByTestId(`i18n-en-input-${key}`).fill('  grasp  ')
    await page.getByTestId(`i18n-mark-reviewed-${key}`).click()
    await page.waitForLoadState('networkidle')

    expect(seen.find(w => w.url.includes('mark-reviewed'))?.body?.target_en).toBeNull()
  })

  test('I18N-06-8: 未指派的列顯示「（未指派）」，已指派顯示員工號', async ({ page }) => {
    await setup(page)
    await openI18nReviewTab(page)

    await expect(page.getByTestId('i18n-assigned-rule_option:g:g_touch:label')).toContainText('TEST_ANALYST')
    await expect(page.getByTestId('i18n-assigned-rule_option:g:g_grasp:label')).toContainText('（未指派）')
  })
})

// ══════════════════════════════════════════════════════════════════════════
// §I18N-07 寫入面 source-level 守衛（取代 Phase B 的「唯讀 source-level 守衛」）
//
// **原守衛（舊 §I18N-06）守什麼**：`I18nReviewTab.tsx`／`i18nReviewApi.ts` 兩個檔案
// 裡不得出現 `apiPost`/`apiPut`/`apiPatch`/`apiDelete` 任一字面——零寫入。
// **為什麼必須改**：本輪這一頁**必須**寫入（D6 驗收定義：覆核進度要「可下降」），
// 零寫入的斷言與功能直接矛盾。
//
// **新守衛（等強）**：把「零寫入」換成「寫入面是封閉且窄的」，一樣是掃原始碼字面、
// 一樣不依賴畫面渲染時機、一樣有「掃描器非恆真」的後設測試：
//   07-2  `I18nReviewTab.tsx`（UI 層）仍是**零寫入呼叫端** —— UI 不得自己打 API，
//         一律經 `i18nReviewApi.ts` 的 hooks。這一半的強度與原守衛完全相同。
//   07-3  **覆核頁可達的每一個模組**（跟著 import 走，範圍限在 feature 目錄內），
//         寫入呼叫的 URL 必須落在 ALLOWED_WRITE_PATHS（＝ADR-032 D6 後半那三支端點）。
//         繞去 `PATCH /api/v2/vocab/{id}`（它也寫得到 `name_en`）＝繞過 D4 的欄位
//         白名單／retired 擋／I5 唯一性 ＋ D6 的反橡皮圖章 422，這正是這頁最需要被
//         擋住的事。
//   07-4  整個 feature 目錄不得出現裸 `fetch(`——一律走 `shared/api/client`。
//   07-5  fail-closed ＋ 後設測試：掃描器解析不出來的提及（別名、間接呼叫、包一層
//         helper）一律視為違規（ADR-032 I3「純欄位名 grep 看不穿函式邊界」的教訓），
//         各種繞道各合成一次證明真的會命中，**並反向證明合法寫法不會被誤判**。
//
// **2026-08-20 覆核修的三個實證漏洞**（每一個都有對應的合成案例）：
//   M5  UI 改用裸 `fetch(url, {method:'PATCH'})` → 純 helper 名的掃描器全盲。
//       修法：`fetch(` 算同一類呼叫端 ＋ 07-4 目錄級禁令。
//   M6  繞道寫入搬到同目錄第三個檔案、UI 從那裡 import → 只掃兩條硬路徑就看不到。
//       修法：掃描對象改成「從 Tab 出發的模組圖」，順帶解決路徑漂移。
//   誤判 多行 import 與註解裡提到 helper 名 → 守衛對純文件／重構喊狼，而喊狼守衛的
//       下場是被放寬。修法：先剝註解、import 改成吃到 `from '...'` 為止。
// ══════════════════════════════════════════════════════════════════════════
test.describe('§I18N-07 寫入面 source-level 守衛', () => {
  const HERE = path.dirname(fileURLToPath(import.meta.url))
  const FEATURE_DIR = path.resolve(HERE, '../src/features/dictionaries')
  const TAB_FILE = path.join(FEATURE_DIR, 'I18nReviewTab.tsx')

  /** `shared/api/client` 是被認可的寫入 helper 本體（它的工作就是包 `fetch`）——模組圖不追進去。 */
  const SANCTIONED_RE = /shared[/\\]api[/\\]client\.tsx?$/

  const WRITE_HELPERS = ['apiPost', 'apiPut', 'apiPatch', 'apiDelete', 'apiDeleteJson', 'apiUpload']

  /**
   * 「寫入呼叫端」的字面樣式：六個 helper ＋ 裸 `fetch(`。
   * 裸 `fetch` 一定要算進來——`fetch(url, { method: 'PATCH' })` 寫得到同一批資料卻
   * 完全不經 `client.ts`，只認 helper 名的掃描器對它是全盲的（M5）。要求後面緊跟 `(`
   * 是為了不誤中 `refetch`／`fetchQuery` 之外的無害提及（`\b` 已經擋掉前綴形）。
   */
  const CALLEE_SRC = `\\b(?:${WRITE_HELPERS.join('|')})\\b|\\bfetch(?=\\s*\\()`

  const CALL_RE = new RegExp(
    `(${CALLEE_SRC})(?:<[^()<>]*>)?\\s*\\(\\s*(['"\`])((?:\\\\.|(?!\\2)[\\s\\S])*?)\\2`,
    'g',
  )

  interface Hit { file: string; rule: string; detail: string }

  /**
   * 剝掉註解再數。**不剝就會對純文件改動喊狼**：實測在任一被掃檔案的註解裡寫下
   * 「一律經 `apiPost`」即誤判紅，而這兩個檔案的檔頭正好在大段論述這條政策——
   * 下一個人照著寫就把 CI 弄紅，最省事的修法會是把守衛放寬（典型死法）。
   * 行註解的判斷刻意跳過 `://`（網址）；這是行為近似，不是完整的 TS parser。
   */
  function stripComments(text: string): string {
    return text.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
  }

  /**
   * 剝掉 import 語句（**只有 'api' 模式用**；'ui' 模式反過來，import 到寫入 helper
   * 本身就是違規）。樣式是「非貪婪吃到 `from '...'`、中途不得再出現 import」，
   * 而不是原本的「只看 `^\s*import` 那一行」——加第三個 helper 時 prettier／eslint
   * 會自然把 import 折成多行，續行上的 helper 名沒被計入就會誤判成 unparsed。
   */
  function stripImports(text: string): string {
    return text.replace(/^[ \t]*import\b(?:(?!\bimport\b)[\s\S])*?\bfrom\s*['"][^'"]*['"]/gm, '')
  }

  function countMentions(text: string): number {
    return (text.match(new RegExp(`(?:${CALLEE_SRC})`, 'g')) ?? []).length
  }

  /** `/api/v2/rule-sets/${code}/params/...` → `/api/v2/rule-sets/X/params/...`（樣板參數視為單一路徑節）。 */
  function normalizePath(literal: string): string {
    return literal.replace(/\$\{[^}]*\}/g, 'X').split('?')[0]
  }

  /** 相對 import → 實體檔案（`.ts`/`.tsx`/`/index.*`）；解析不到、是被認可的 helper 本體、或跨出 `limitDir` 就回 null。 */
  function resolveImport(fromFile: string, spec: string, limitDir: string): string | null {
    const base = path.resolve(path.dirname(fromFile), spec)
    for (const c of [base, `${base}.ts`, `${base}.tsx`, path.join(base, 'index.ts'), path.join(base, 'index.tsx')]) {
      if (!fs.existsSync(c) || !fs.statSync(c).isFile()) continue
      if (SANCTIONED_RE.test(c)) return null
      if (path.relative(limitDir, c).startsWith('..')) return null
      return c
    }
    return null
  }

  /**
   * 從入口檔（覆核頁）出發的模組圖——**這才是「這一頁的寫入面」的正確定義**。
   * 原本只掃兩條硬寫死的路徑，所以把繞道寫入搬到同目錄第三個檔案、Tab 從那裡 import，
   * 兩層守衛可以同時綠（M6）。跟著 import 走之後，Tab 碰得到的每個模組都會被掃，
   * 路徑漂移也不再讓守衛形同虛設。
   *
   * **範圍刻意收在 feature 目錄內**：跨出去的是共用基礎設施（`shared/api/client` 本體、
   * `shared/auth/useMe` 有它自己合法的 `PATCH /me/locale`），拿這一頁的白名單去掃它們
   * 只會製造誤判。代價是「把繞道寫入藏到 `src/shared/` 再 import 進來」這一層掃不到——
   * 那一層由 §I18N-05-1 的動態白名單接（所以 05-1 現在把整個互動面都點過一遍）。
   */
  function reachableModules(entry: string, limitDir: string): string[] {
    const seen = new Set<string>([entry])
    const queue = [entry]
    while (queue.length) {
      const file = queue.shift() as string
      const text = stripComments(fs.readFileSync(file, 'utf-8'))
      const specs = [
        ...[...text.matchAll(/\bfrom\s*['"](\.[^'"]*)['"]/g)].map(m => m[1]),
        ...[...text.matchAll(/^[ \t]*import\s*['"](\.[^'"]*)['"]/gm)].map(m => m[1]),
      ]
      for (const spec of specs) {
        const resolved = resolveImport(file, spec, limitDir)
        if (resolved && !seen.has(resolved)) {
          seen.add(resolved)
          queue.push(resolved)
        }
      }
    }
    return [...seen]
  }

  /** 目錄下所有 `.ts`/`.tsx`（遞迴）。 */
  function sourceFiles(dir: string): string[] {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
      const full = path.join(dir, e.name)
      if (e.isDirectory()) return sourceFiles(full)
      return /\.tsx?$/.test(e.name) ? [full] : []
    })
  }

  /**
   * @param mode `'ui'` ＝UI 層，一個寫入呼叫端都不准提到（含裸 `fetch(`）；
   *             `'api'` ＝資料層，寫入呼叫的 URL 必須在白名單內，且每一次提及都要被解釋掉。
   */
  function scan(file: string, mode: 'ui' | 'api'): Hit[] {
    const code = stripComments(fs.readFileSync(file, 'utf-8'))
    const name = path.basename(file)
    const hits: Hit[] = []

    if (mode === 'ui') {
      const mentions = countMentions(code)
      if (mentions > 0) {
        hits.push({ file: name, rule: 'ui-must-not-write', detail: `UI 層出現 ${mentions} 處寫入呼叫端（helper 或裸 fetch）——請改用 i18nReviewApi 的 hooks` })
      }
      return hits
    }

    const body = stripImports(code)
    const calls = [...body.matchAll(CALL_RE)]
    for (const c of calls) {
      if (!ALLOWED_WRITE_PATHS.some(re => re.test(normalizePath(c[3])))) {
        hits.push({ file: name, rule: 'write-outside-allowlist', detail: `${c[1]}('${c[3]}')` })
      }
    }
    // 每一次提及都必須被解釋掉（import 已剝除，剩下的就該是解析得出的呼叫）。差額
    // 代表掃描器看不懂的用法（別名、動態呼叫、包一層 helper）——fail-closed，不默許。
    const mentions = countMentions(body)
    if (mentions > calls.length) {
      hits.push({ file: name, rule: 'unparsed-write-usage', detail: `${mentions} 處提及，只解析出 ${calls.length} 處呼叫` })
    }
    return hits
  }

  /** 裸 `fetch(`：整個 feature 目錄都不准出現——一律走 `shared/api/client` 的 helper。 */
  function scanBareFetch(file: string): Hit[] {
    const n = (stripComments(fs.readFileSync(file, 'utf-8')).match(/\bfetch\s*\(/g) ?? []).length
    return n > 0 ? [{ file: path.basename(file), rule: 'bare-fetch', detail: `${n} 處裸 fetch(` }] : []
  }

  test('I18N-07-1: 守衛入口與模組圖解析得動（後設守衛，避免路徑漂移後測試形同虛設）', () => {
    expect(fs.existsSync(TAB_FILE), `${TAB_FILE} 不存在，守衛入口的路徑可能已經漂移`).toBe(true)
    expect(sourceFiles(FEATURE_DIR).length, 'feature 目錄掃不到檔案').toBeGreaterThanOrEqual(2)

    // 模組圖真的跟著 import 走——否則 07-3 掃的是空集合，那條斷言會恆真
    const mods = reachableModules(TAB_FILE, FEATURE_DIR).map(f => path.basename(f))
    expect(mods).toContain('I18nReviewTab.tsx')
    expect(mods).toContain('i18nReviewApi.ts')
  })

  test('I18N-07-2: I18nReviewTab.tsx（UI 層）不直接使用任何寫入 helper／裸 fetch', () => {
    expect(scan(TAB_FILE, 'ui')).toEqual([])
  })

  test('I18N-07-3: 覆核頁可達的每個模組，寫入呼叫都落在 ADR-032 D6 的三支端點內', () => {
    const mods = reachableModules(TAB_FILE, FEATURE_DIR).filter(f => f !== TAB_FILE)
    const hits = mods.flatMap(f => scan(f, 'api'))
    expect(hits, `寫入面越界：${JSON.stringify(hits)}`).toEqual([])

    // 正向錨點：這些模組**確實有**寫入呼叫，否則上面的空清單是恆真的
    const calls = mods.flatMap(f => [...stripImports(stripComments(fs.readFileSync(f, 'utf-8'))).matchAll(CALL_RE)])
    expect(calls.length, '覆核頁的資料層應該有寫入呼叫（覆核＋指派）').toBeGreaterThanOrEqual(2)
  })

  test('I18N-07-4: feature 目錄內任何檔案都不得出現裸 fetch(', () => {
    const hits = sourceFiles(FEATURE_DIR).flatMap(f => scanBareFetch(f))
    expect(hits, `裸 fetch( 繞過了 shared/api/client：${JSON.stringify(hits)}`).toEqual([])
  })

  test('I18N-07-5: 掃描器抓得到各種繞道，也不對合法寫法誤判（非恆真的空清單斷言）', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'i18n-guard-'))
    const w = (name: string, src: string) => {
      const f = path.join(dir, name)
      fs.writeFileSync(f, src)
      return f
    }
    const CLIENT = "'../../shared/api/client'"
    try {
      // (a) UI 層 import 到寫入 helper
      expect(scan(w('a.tsx', `import { apiPost } from ${CLIENT}\n`), 'ui').map(h => h.rule))
        .toEqual(['ui-must-not-write'])

      // (b) UI 層改用裸 fetch 繞過 helper（M5）——UI 規則與目錄級禁令都要抓到，
      //     連 URL 白名單那一層也擋（三層都命中才是「等強替代」）
      const bare = w('b.tsx', "export const f = () => fetch('/api/v2/vocab/1', { method: 'PATCH', body: '{}' })\n")
      expect(scan(bare, 'ui').map(h => h.rule)).toEqual(['ui-must-not-write'])
      expect(scanBareFetch(bare).map(h => h.rule)).toEqual(['bare-fetch'])
      expect(scan(bare, 'api').map(h => h.rule)).toEqual(['write-outside-allowlist'])

      // (c) 寫入呼叫指向白名單外的端點（例：繞去 vocab 端點改 name_en）
      expect(scan(w('c.ts',
        `import { apiPatch } from ${CLIENT}\n` +
        "export const f = (id: string) => apiPatch<unknown>(`/api/v2/vocab/${id}`, { name_en: 'x' })\n",
      ), 'api').map(h => h.rule)).toEqual(['write-outside-allowlist'])

      // (d) 掃描器解析不出來的用法（別名／間接呼叫）——fail-closed
      expect(scan(w('d.ts',
        `import { apiPost } from ${CLIENT}\n` +
        "const send = apiPost\nexport const f = () => send('/api/v2/i18n/review/assign', {})\n",
      ), 'api').map(h => h.rule)).toEqual(['unparsed-write-usage'])

      // (e) 繞道寫入搬到第三個檔案、UI 從那裡 import（M6）——模組圖跟著 import 走才抓得到
      w('sneaky.ts',
        `import { apiPatch } from ${CLIENT}\n` +
        "export const f = (id: string) => apiPatch<unknown>(`/api/v2/vocab/${id}`, { name_en: 'x' })\n")
      const tab = w('tab.tsx', "import { f } from './sneaky'\nexport const T = () => f('1')\n")
      const mods = reachableModules(tab, dir)
      expect(mods.map(m => path.basename(m)).sort()).toEqual(['sneaky.ts', 'tab.tsx'])
      expect(scan(tab, 'ui'), 'UI 檔本身是乾淨的——所以只掃兩條硬路徑會整個漏掉這一種').toEqual([])
      expect(mods.filter(m => m !== tab).flatMap(m => scan(m, 'api')).map(h => h.rule))
        .toEqual(['write-outside-allowlist'])

      // (f) 反向一：合法用法不得被誤判（否則守衛會逼人繞路）
      expect(scan(w('f.ts',
        `import { apiPost } from ${CLIENT}\n` +
        "export const f = () => apiPost<unknown>('/api/v2/i18n/review/mark-reviewed', {})\n",
      ), 'api')).toEqual([])

      // (g) 反向二：多行 import（加第三個 helper 時 prettier／eslint 的自然結果）不得誤判
      expect(scan(w('g.ts',
        `import {\n  apiGet,\n  apiPost,\n  apiPut,\n} from ${CLIENT}\n` +
        "export const f = () => apiPost<unknown>('/api/v2/i18n/review/assign', {})\n",
      ), 'api')).toEqual([])

      // (h) 反向三：註解／檔頭論述提到 helper 名不得誤判（這兩個檔案的檔頭正好在論述這條政策）
      expect(scan(w('h.ts',
        '/** 一律經 apiPost 寫入；不得 apiPatch 繞道，也不准裸 fetch( 。 */\n' +
        '// 再提一次 apiDelete\n' +
        `import { apiPost } from ${CLIENT}\n` +
        "export const f = () => apiPost<unknown>('/api/v2/i18n/review/assign', {})\n",
      ), 'api')).toEqual([])
      expect(scan(w('h2.tsx', '// UI 層一律經 hooks，不直接 apiPost\nexport const T = () => null\n'), 'ui')).toEqual([])
    } finally {
      fs.rmSync(dir, { recursive: true, force: true })
    }
  })
})
