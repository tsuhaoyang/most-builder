/**
 * ADR-024 §5 / D11-FE：同義詞 CRUD（把 D4 的唯讀顯示變可增刪）。
 *
 * 本批核心（最容易做反的一條）：同義詞寫入**必須繞過 clone-on-write gate**——
 * 在 published/certified 版本新增同義詞時，**不得**跳「建立草稿版本」對話框，
 * 而是直接 POST /synonyms（ADR-014：同義詞是已發布/認證版本唯一可後補的資料）。
 *
 * 非空洞性（沿用 D8b/D10 作法）：全部 /api/** 由 page.route 攔截，斷言 method＋URL＋body；
 * catch-all 對「非 GET」一律 500 —— 若同義詞寫入誤打到 /clone-draft 或其他端點會當場炸。
 *
 * 執行：E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test d11-synonym-crud.spec.ts
 */
import { test, expect, type Page } from '@playwright/test'

const ADMIN_ME = { employee_no: 'IEC141289', roles: ['admin'], level: 3 }

/** published + certified_import + active —— 值編輯會觸發 clone；同義詞則不該。 */
const V2 = {
  id: 'rs-2', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2',
  status: 'published', multiplier: 1, is_active: true,
  provenance: 'certified_import', created_at: '2026-07-07T10:24:25Z', notes: null,
}
/** retired（終態）—— 同義詞增刪控制必須隱藏（唯讀）。 */
const RETIRED = {
  id: 'rs-4', code: 'MINIMOST_FACTORY_V0', name_zh: 'MiniMOST 工廠規則 v0',
  status: 'retired', multiplier: 1, is_active: false,
  provenance: 'manual', created_at: '2026-05-01T00:00:00Z', notes: null,
}

const G_ITEMS = [
  { id: 'g1', code: 'g_tap', label_zh: '輕按', label_en: null, sentence_text_zh: '輕按', sort_order: 0, is_active: true, modifier_key: null, requires_modifier: false, base_tmu: 3 },
  { id: 'g2', code: 'g_grasp', label_zh: '抓握', label_en: null, sentence_text_zh: '抓握', sort_order: 1, is_active: true, modifier_key: null, requires_modifier: false, base_tmu: 6 },
]

interface Captured { method: string; url: string; body: unknown }

/** conflict：POST /synonyms 回 409 SYNONYM_CONFLICT（模擬已存在）。 */
async function setup(page: Page, opts: { withRetired?: boolean; conflict?: boolean } = {}) {
  const writes: Captured[] = []
  // GET /synonyms 的狀態化清單（新增/刪除後反映在畫面上，供截圖與重取）。
  let syns: Record<string, unknown>[] = [
    { id: 's1', parameter: 'G', option_code: 'g_grasp', synonym_raw: '握住', synonym_norm: '握住', priority: 1 },
  ]
  let nextId = 2

  await page.route('**/api/**', route => {
    const req = route.request()
    const url = req.url()
    const method = req.method()
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (method !== 'GET') {
      let body: unknown = null
      try { body = req.postDataJSON() } catch { body = req.postData() }
      writes.push({ method, url, body })
    }

    if (url.includes('/api/v2/me')) return json(ADMIN_ME)

    // ── 同義詞寫入路徑（本批核心）─────────────────────────────────────────
    if (/\/synonyms\/[^/]+$/.test(url) && method === 'DELETE') {
      const id = url.split('/').pop()!.replace(/\?.*$/, '')
      syns = syns.filter(s => s.id !== id)
      return route.fulfill({ status: 204, body: '' })
    }
    if (/\/synonyms$/.test(url) && method === 'POST') {
      if (opts.conflict) {
        return json({ detail: { code: 'SYNONYM_CONFLICT', message: '同義詞「握住」已存在於此參數' } }, 409)
      }
      const b = req.postDataJSON() as { parameter: string; option_code: string; synonym_raw: string }
      const created = { id: `s${nextId++}`, parameter: b.parameter, option_code: b.option_code, synonym_raw: b.synonym_raw, synonym_norm: b.synonym_raw, priority: 0 }
      syns = [...syns, created]
      return json(created)
    }
    if (/\/synonyms$/.test(url)) return json(syns)   // GET

    if (url.includes('/api/v2/rule-sets/active')) return json({ id: V2.id, code: V2.code, name_zh: V2.name_zh })
    if (url.includes('/diff')) return json({ detail: 'no diff needed' }, 200)

    if (url.includes('/params/G/')) return json({ rule_set_code: V2.code, param: 'G', section: 'default', kind: 'options', items: G_ITEMS })
    if (url.includes('/params/')) return json({ rule_set_code: V2.code, param: 'X', section: 'default', kind: 'options', items: [] })

    if (url.match(/\/api\/v2\/rule-sets(\?|$)/)) {
      const list: Record<string, unknown>[] = [V2]
      if (opts.withRetired) list.push(RETIRED)
      return json(list)
    }

    // catch-all：GET → 空陣列；非 GET → 500（未預期的寫入必須炸掉，含誤打 /clone-draft）
    if (method !== 'GET') return json({ detail: `未預期的寫入：${method} ${url}` }, 500)
    return json([])
  })

  return writes
}

async function openDictionary(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: /MOST 字典/ }).first().click()
  await page.waitForLoadState('networkidle')
}

// ─────────────────────────────────────────────────────────────────────────────

test('D11-a: 在 published 版對選項新增同義詞 → 直接 POST /synonyms、method=POST、body 正確，且**不跳 clone 對話框**', async ({ page }) => {
  const writes = await setup(page)
  await openDictionary(page)
  // V2 published+certified → 用「編輯」進 L2（開啟不觸發 clone，clone 只在寫入時）
  await page.getByTestId(`dict-version-${V2.code}`).getByRole('button', { name: '編輯' }).click()
  await page.getByRole('tab', { name: 'G 取得控制' }).click()

  const cell = page.getByTestId('syn-cell-g_grasp')
  await expect(cell).toBeVisible()
  await expect(cell.getByTestId('syn-chip-s1')).toContainText('握住')   // 既有別名可見

  // 新增別名「握持」
  await cell.getByTestId('syn-input-g_grasp').fill('握持')
  await cell.getByTestId('syn-add-g_grasp').click()
  await expect(page.getByText('已新增同義詞「握持」')).toBeVisible()

  // 核心斷言 1：clone-on-write 對話框**未**出現（同義詞繞過 gate）
  await expect(page.getByTestId('dict-clone-dialog')).toHaveCount(0)
  await expect(page.getByTestId('dict-clone-created')).toHaveCount(0)
  // 核心斷言 2：沒有任何 clone-draft 寫入（沒被誤送去建草稿）
  expect(writes.filter(w => w.url.includes('/clone-draft'))).toHaveLength(0)
  // 核心斷言 3：確實打到 POST /synonyms，且 body 為 {parameter, option_code, synonym_raw}
  const posts = writes.filter(w => w.method === 'POST' && /\/synonyms$/.test(w.url))
  expect(posts).toHaveLength(1)
  expect(posts[0].url).toContain(`/api/v2/rule-sets/${V2.code}/synonyms`)
  expect(posts[0].body).toMatchObject({ parameter: 'G', option_code: 'g_grasp', synonym_raw: '握持' })

  // 新別名反映在畫面（狀態化 mock 重取）
  await expect(page.getByTestId('syn-cell-g_grasp')).toContainText('握持')
  await page.screenshot({ path: 'd11-synonym-crud.png', fullPage: true })
})

test('D11-b: 刪除同義詞 → DELETE /synonyms/{syn_id}（不跳 clone）', async ({ page }) => {
  const writes = await setup(page)
  await openDictionary(page)
  await page.getByTestId(`dict-version-${V2.code}`).getByRole('button', { name: '編輯' }).click()
  await page.getByRole('tab', { name: 'G 取得控制' }).click()

  await page.getByTestId('syn-del-s1').click()
  await expect(page.getByText('已刪除同義詞')).toBeVisible()

  await expect(page.getByTestId('dict-clone-dialog')).toHaveCount(0)
  const dels = writes.filter(w => w.method === 'DELETE' && w.url.includes('/synonyms/'))
  expect(dels).toHaveLength(1)
  expect(dels[0].url).toContain(`/api/v2/rule-sets/${V2.code}/synonyms/s1`)
  // 刪掉後該 chip 不再出現
  await expect(page.getByTestId('syn-chip-s1')).toHaveCount(0)
})

test('D11-conflict: 新增重複同義詞 → 顯示後端 409 SYNONYM_CONFLICT message，且不跳 clone', async ({ page }) => {
  const writes = await setup(page, { conflict: true })
  await openDictionary(page)
  await page.getByTestId(`dict-version-${V2.code}`).getByRole('button', { name: '編輯' }).click()
  await page.getByRole('tab', { name: 'G 取得控制' }).click()

  const cell = page.getByTestId('syn-cell-g_grasp')
  await cell.getByTestId('syn-input-g_grasp').fill('握住')
  await cell.getByTestId('syn-add-g_grasp').click()

  await expect(page.getByText(/同義詞「握住」已存在/)).toBeVisible()
  await expect(page.getByTestId('dict-clone-dialog')).toHaveCount(0)
  // 輸入內容保留供修正（失敗不清空）
  await expect(cell.getByTestId('syn-input-g_grasp')).toHaveValue('握住')
  expect(writes.filter(w => w.url.includes('/clone-draft'))).toHaveLength(0)
})

test('D11-c: retired（終態）版本 → 同義詞新增/刪除控制不顯示（唯讀），但既有別名仍看得到', async ({ page }) => {
  await setup(page, { withRetired: true })
  await openDictionary(page)
  // retired 版本以「檢視」進 L2
  await page.getByTestId(`dict-version-${RETIRED.code}`).getByRole('button', { name: '檢視' }).click()
  await page.getByRole('tab', { name: 'G 取得控制' }).click()

  const cell = page.getByTestId('syn-cell-g_grasp')
  await expect(cell).toBeVisible()
  // 既有別名仍可見（回放/查閱）
  await expect(cell.getByText('握住')).toBeVisible()
  // 但無新增輸入、無刪除鈕
  await expect(page.getByTestId('syn-input-g_grasp')).toHaveCount(0)
  await expect(page.getByTestId('syn-add-g_grasp')).toHaveCount(0)
  await expect(page.getByTestId('syn-del-s1')).toHaveCount(0)
})
