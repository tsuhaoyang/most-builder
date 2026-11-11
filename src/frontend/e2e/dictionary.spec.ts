/**
 * MOST 字典（ADR-023 D4）—— Type A（Mocked-API）。
 *
 * 覆蓋：L1 版本清單（狀態兩維徽章＋啟用中卡片）、L1↔L2 切換、七參數分頁＋次級 tab、
 * 選項型表格、帶型整組編輯、clone-on-write、activate/retire 二次確認，
 * 以及**寫入請求的 method／query／body 契約**（讓契約被改壞時會變紅）。
 *
 * 執行：E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test dictionary.spec.ts
 */
import { test, expect, type Page } from '@playwright/test'

const ADMIN_ME = { employee_no: 'IEC141289', roles: ['admin'], level: 3 }

/** 對照真實種子：V1 published+inactive、V2 published+active，兩者皆 certified_import。 */
const V1 = {
  id: 'rs-1', code: 'MINIMOST_FACTORY_V1', name_zh: 'MiniMOST 工廠規則 v1',
  status: 'published', multiplier: 1, is_active: false,
  provenance: 'certified_import', created_at: '2026-06-18T04:12:39Z', notes: null,
}
const V2 = {
  id: 'rs-2', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2（v3 IE 認證）',
  status: 'published', multiplier: 1, is_active: true,
  provenance: 'certified_import', created_at: '2026-07-07T10:24:25Z', notes: null,
}
/** 可直接寫入的草稿（cloned，非 certified_import）→ 不觸發 clone gate。 */
const DRAFT = {
  id: 'rs-3', code: 'MINIMOST_FACTORY_V2_DRAFT_202607210900', name_zh: 'v2 草稿',
  status: 'draft', multiplier: 1, is_active: false,
  provenance: 'cloned', created_at: '2026-07-21T09:00:00Z', notes: null,
}

/** 已封存版本（供解除封存動線）。 */
const RETIRED = {
  id: 'rs-4', code: 'MINIMOST_FACTORY_V0', name_zh: 'MiniMOST 工廠規則 v0',
  status: 'retired', multiplier: 1, is_active: false,
  provenance: 'manual', created_at: '2026-05-01T00:00:00Z', notes: null,
}

const G_ITEMS = [
  { id: 'g1', code: 'g_tap', label_zh: '輕按', label_en: null, sentence_text_zh: '輕按', sort_order: 0, is_active: true, modifier_key: null, requires_modifier: false, base_tmu: 3 },
  { id: 'g2', code: 'g_grasp', label_zh: '抓握', label_en: null, sentence_text_zh: '抓握', sort_order: 1, is_active: true, modifier_key: null, requires_modifier: false, base_tmu: 6 },
]
const P_ADDONS = [
  { id: 'pa1', code: 'p_precise', label_zh: '精確對位', label_en: null, sentence_text_zh: '對準', sort_order: 0, is_active: true, delta_tmu: 3, needs_precision: true, max_select: 2, display_rule: 'show_self' },
]
const A_REACH = [
  { id: 'a1', max_value: 2.5, index_value: 0, sort_order: 0, is_active: true },
  { id: 'a2', max_value: 20.0, index_value: 6, sort_order: 1, is_active: true },
  { id: 'a3', max_value: null, index_value: 24, sort_order: 2, is_active: true },
]

/** `GET /diff` 回應（D7 / H-1）。預設：有差異、無 clone 紀錄。 */
function makeDiff(over: Record<string, unknown> = {}) {
  return {
    target_code: V1.code,
    target_status: 'published',
    base_code: V2.code,
    base_is_active: true,
    compared_with_self: false,
    source_code: null,
    base_is_source: null,
    diff: {
      header: { name_zh: { before: 'MiniMOST 工廠規則 v2', after: 'MiniMOST 工廠規則 v1' } },
      sections: {
        g: {
          added: [{ key: 'g_new', after: { code: 'g_new', base_tmu: 5 } }],
          removed: [{ key: 'g_old', before: { code: 'g_old', base_tmu: 9 } }],
          changed: [{
            key: 'g_grasp',
            fields: {
              base_tmu: { before: 6, after: 12 },
              sentence_text_zh: { before: '抓握', after: '抓取' },
            },
          }],
        },
      },
      row_counts: { g: { before: 11, after: 11 }, b: { before: 4, after: 7 } },
      summary: {
        added: 1, removed: 1, changed: 1,
        changed_sections: ['g'], header_changed: ['name_zh'], identical: false,
      },
    },
    ...over,
  }
}

/** 區塊 0/0/0，header 只有 name_zh（＝剛 clone 未改任何值的實際形狀）。 */
const NAME_ONLY_DIFF = makeDiff({
  diff: {
    header: { name_zh: { before: 'v2', after: 'v2 (草稿)' } },
    sections: {},
    row_counts: { g: { before: 11, after: 11 } },
    summary: { added: 0, removed: 0, changed: 0, changed_sections: [], header_changed: ['name_zh'], identical: false },
  },
})

/** 區塊 0/0/0，但乘數變了 —— 唯一「值全變了卻看不出來」的情境。 */
const MULTIPLIER_ONLY_DIFF = makeDiff({
  diff: {
    header: { multiplier: { before: 1, after: 1.05 } },
    sections: {},
    row_counts: { g: { before: 11, after: 11 } },
    summary: { added: 0, removed: 0, changed: 0, changed_sections: [], header_changed: ['multiplier'], identical: false },
  },
})

const IDENTICAL_DIFF = makeDiff({
  diff: {
    header: {}, sections: {}, row_counts: {},
    summary: { added: 0, removed: 0, changed: 0, changed_sections: [], header_changed: [], identical: true },
  },
})

interface Captured { method: string; url: string; body: unknown }

/**
 * `withDraft`：版本清單是否含可寫草稿。
 * 回傳 `writes`：所有非 GET 請求（method/url/body），供契約斷言。
 */
async function setup(page: Page, opts: {
  withDraft?: boolean
  withRetired?: boolean
  /** DELETE 回 409 RULE_SET_IN_USE（帶各表引用筆數）。 */
  deleteInUse?: boolean
  /** `GET /diff` 的回應覆寫；'error' → 500（模擬取不到差異）。 */
  diff?: Record<string, unknown> | 'error'
} = {}) {
  const writes: Captured[] = []
  const state = { cloned: false, deleted: false, unretired: false }

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

    if (url.includes('/clone-draft') && method === 'POST') {
      state.cloned = true
      return json({ code: DRAFT.code, name_zh: DRAFT.name_zh })
    }
    if (url.includes('/publish') && method === 'POST') return json({ code: DRAFT.code, status: 'published' })
    if (url.includes('/activate') && method === 'POST') return json({ ok: true })
    // unretire 要先比對（/retire 是它的子字串）
    if (url.includes('/unretire') && method === 'POST') {
      state.unretired = true
      return json({ code: RETIRED.code, status: 'published', is_active: false })
    }
    if (url.includes('/retire') && method === 'POST') return json({ ok: true })

    // DELETE /rule-sets/{code}（非選項級 DELETE —— 後者路徑含 /params/）
    if (method === 'DELETE' && !url.includes('/params/')) {
      if (opts.deleteInUse) {
        return json({
          detail: {
            code: 'RULE_SET_IN_USE',
            message: '草稿已被引用，無法刪除',
            references: { most_cycles: 3, motion_module_versions: 1 },
          },
        }, 409)
      }
      state.deleted = true
      return json({ code: DRAFT.code, deleted: true })
    }

    if (url.includes('/api/v2/rule-sets/active')) return json({ id: V2.id, code: V2.code, name_zh: V2.name_zh })

    // 版本差異（D7 / H-1）
    if (url.includes('/diff')) {
      if (opts.diff === 'error') return json({ detail: '差異服務暫時無法使用' }, 500)
      return json(opts.diff ?? makeDiff())
    }
    if (url.includes('/synonyms')) return json([
      { id: 's1', parameter: 'G', option_code: 'g_grasp', synonym_raw: '握住', synonym_norm: '握住', priority: 1 },
    ])

    // 選項/帶讀取（PATCH/PUT 也會落到這裡，回同一份即可——寫入契約由 `writes` 斷言）
    if (url.includes('/params/G/')) return json({ rule_set_code: V2.code, param: 'G', section: 'default', kind: 'options', items: G_ITEMS })
    if (url.includes('/params/P/')) return json({ rule_set_code: V2.code, param: 'P', section: 'addon', kind: 'options', items: P_ADDONS })
    if (url.includes('/params/A/')) return json({ rule_set_code: V2.code, param: 'A', section: 'reach', kind: 'bands', items: A_REACH })
    if (url.includes('/params/')) return json({ rule_set_code: V2.code, param: 'X', section: 'default', kind: 'options', items: [] })

    if (url.match(/\/api\/v2\/rule-sets(\?|$)/)) {
      const list: Record<string, unknown>[] = [V1, V2]
      if ((opts.withDraft || state.cloned) && !state.deleted) list.push(DRAFT)
      // 解除封存後：同一版本以 published + 非 active 回傳
      if (opts.withRetired) list.push(state.unretired ? { ...RETIRED, status: 'published' } : RETIRED)
      return json(list)
    }

    // 未知端點：GET 回空陣列讓 App 其他區塊能渲染；**非 GET 一律 500**，
    // 避免「任何 method 任何 URL 都被吞掉回 200」而讓錯誤的寫入看起來成功。
    if (method !== 'GET') return json({ detail: `未預期的寫入：${method} ${url}` }, 500)
    return json([])
  })

  return writes
}

async function openDictionary(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  // .first()：React StrictMode 的 mount→unmount→remount 期間側欄可能短暫存在兩份
  await page.getByRole('button', { name: /MOST 字典/ }).first().click()
  await page.waitForLoadState('networkidle')
}

const openEditor = async (page: Page, code: string) => {
  await page.getByTestId(`dict-version-${code}`).getByRole('button', { name: '編輯' }).click()
}

test.describe('§D4-1 L1 版本清單', () => {
  test('D4-1-1: 啟用中卡片顯示版本名、來源、編輯/匯出鈕', async ({ page }) => {
    await setup(page)
    await openDictionary(page)

    const card = page.getByTestId('dict-active-card')
    await expect(card).toBeVisible()
    await expect(card.getByText(V2.name_zh)).toBeVisible()
    await expect(card.getByText('來源：認證匯入')).toBeVisible()
    await expect(card.getByRole('button', { name: '編輯字典' })).toBeVisible()
    await expect(card.getByRole('button', { name: '匯出 JSON' })).toBeVisible()
  })

  test('D4-1-2: 狀態欄兩維 — status 徽章 ＋ active 版另加「啟用中」', async ({ page }) => {
    await setup(page)
    await openDictionary(page)

    const rowV1 = page.getByTestId(`dict-version-${V1.code}`)
    const rowV2 = page.getByTestId(`dict-version-${V2.code}`)
    await expect(rowV1.getByText('已發布')).toBeVisible()
    await expect(rowV1.getByText('啟用中')).toHaveCount(0)
    await expect(rowV2.getByText('已發布')).toBeVisible()
    await expect(rowV2.getByText('啟用中')).toBeVisible()
  })

  test('D4-1-3: 操作按鈕依可變性矩陣 — V1(published 非 active) 有啟用/封存，V2(active) 沒有', async ({ page }) => {
    await setup(page)
    await openDictionary(page)

    const rowV1 = page.getByTestId(`dict-version-${V1.code}`)
    await expect(rowV1.getByRole('button', { name: '啟用' })).toBeVisible()
    await expect(rowV1.getByRole('button', { name: '封存' })).toBeVisible()

    const rowV2 = page.getByTestId(`dict-version-${V2.code}`)
    await expect(rowV2.getByRole('button', { name: '啟用' })).toHaveCount(0)
    await expect(rowV2.getByRole('button', { name: '封存' })).toHaveCount(0)
    await expect(rowV2.getByRole('button', { name: '編輯' })).toBeVisible()
  })
})

// ── 必修 A：破壞性版本操作的二次確認 ─────────────────────────────────
test.describe('§D4-A activate / retire 二次確認', () => {
  test('D4-A-1: 按「啟用」不直送 —— 先出確認框且說明不回溯', async ({ page }) => {
    const writes = await setup(page)
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '啟用' }).click()

    const dlg = page.getByTestId('dict-confirm-dialog')
    await expect(dlg).toBeVisible()
    await expect(dlg.getByText(/不會回溯修正已建立的資料/)).toBeVisible()
    // 尚未確認 → 不得已經送出
    expect(writes.filter(w => w.url.includes('/activate'))).toHaveLength(0)

    await dlg.getByRole('button', { name: '確認啟用' }).click()
    await expect(page.getByText('啟用成功')).toBeVisible()
    const acts = writes.filter(w => w.url.includes('/activate'))
    expect(acts).toHaveLength(1)
    expect(acts[0].method).toBe('POST')
    expect(acts[0].url).toContain(V1.code)
  })

  test('D4-A-2: 按「封存」先出一般確認框，確認後才送 POST /retire', async ({ page }) => {
    // 封存自 D3b 起可逆（有 unretire）→ 確認強度降為一般確認；
    // type-to-confirm 保留給真正不可逆的刪除（見 D4-B-1）。
    const writes = await setup(page)
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '封存' }).click()

    const dlg = page.getByTestId('dict-confirm-dialog')
    await expect(dlg).toBeVisible()
    // 尚未確認 → 不得已經送出
    expect(writes.filter(w => w.url.includes('/retire'))).toHaveLength(0)

    await dlg.getByRole('button', { name: '確認封存' }).click()
    await expect(page.getByText('封存成功')).toBeVisible()

    const rets = writes.filter(w => w.url.includes('/retire'))
    expect(rets).toHaveLength(1)
    expect(rets[0].method).toBe('POST')
    expect(rets[0].url).toContain(V1.code)
    // 不得誤打成 unretire
    expect(rets[0].url).not.toContain('/unretire')
  })
})

test.describe('§D4-1 L2 選項編輯', () => {
  test('D4-1-4: 進入 L2 後有七參數分頁與返回鈕；返回可回到 L1', async ({ page }) => {
    await setup(page)
    await openDictionary(page)
    await openEditor(page, V2.code)

    const editor = page.getByTestId('dict-option-editor')
    await expect(editor).toBeVisible()
    for (const label of ['A 距離', 'B 身體動作', 'G 取得控制', 'P 放置', 'M 控制移動', 'X 製程時間', 'I 對位/檢查']) {
      await expect(editor.getByRole('tab', { name: label })).toBeVisible()
    }
    await editor.getByRole('button', { name: '← 返回版本列表' }).click()
    await expect(page.getByTestId('dict-version-list')).toBeVisible()
  })

  test('D4-1-5: G 分頁顯示選項表格（代碼/顯示文字/WI 句子/TMU/同義詞）', async ({ page }) => {
    await setup(page)
    await openDictionary(page)
    await openEditor(page, V2.code)
    await page.getByRole('tab', { name: 'G 取得控制' }).click()

    const row = page.getByTestId('dict-option-g_grasp')
    await expect(row).toBeVisible()
    await expect(row.getByText('抓握').first()).toBeVisible()
    await expect(row.getByText('6')).toBeVisible()          // base_tmu → TMU 欄
    await expect(row.getByText('握住')).toBeVisible()        // 同義詞（獨立端點）
  })

  test('D4-1-6: A 分頁為帶型整組編輯 — 有次級 tab、帶界提示與「儲存帶」', async ({ page }) => {
    await setup(page)
    await openDictionary(page)
    await openEditor(page, V2.code)
    await page.getByRole('tab', { name: 'A 距離' }).click()

    for (const s of ['伸手', '手度', '腳步']) {
      await expect(page.getByRole('tab', { name: s })).toBeVisible()
    }
    const bands = page.getByTestId('dict-band-editor')
    await expect(bands).toBeVisible()
    await expect(bands.getByText(/上界必須遞增、不得重疊/)).toBeVisible()
    await expect(bands.getByText(/末帶必須是開放帶/)).toBeVisible()
    await expect(bands.getByRole('button', { name: '儲存帶' })).toBeVisible()
    await expect(bands.getByRole('button', { name: '+ 增加一帶' })).toBeVisible()
  })

  test('D4-1-7: M 分頁次級 tab 為 動詞/距離階梯/腳步/旋轉/手部角度', async ({ page }) => {
    await setup(page)
    await openDictionary(page)
    await openEditor(page, V2.code)
    await page.getByRole('tab', { name: 'M 控制移動' }).click()

    for (const s of ['動詞', '距離階梯', '腳步', '旋轉', '手部角度']) {
      await expect(page.getByRole('tab', { name: s })).toBeVisible()
    }
  })
})

// ── 必修 D：寫入請求的 method／query／body 契約 ───────────────────────
test.describe('§D4-D 寫入契約', () => {
  test('D4-D-1: 選項儲存送 PATCH ＋ 正確 ?section= ＋ 正確 payload 形狀', async ({ page }) => {
    const writes = await setup(page, { withDraft: true })
    await openDictionary(page)
    await openEditor(page, DRAFT.code)   // draft/cloned → 不觸發 clone gate
    await page.getByRole('tab', { name: 'P 放置' }).click()
    await page.getByRole('tab', { name: '附加' }).click()

    await page.getByTestId('dict-option-p_precise').getByRole('button', { name: '編輯' }).click()
    await page.locator('#fld-delta_tmu').fill('5')
    await page.getByRole('button', { name: '儲存' }).click()
    await expect(page.getByText('已儲存')).toBeVisible()

    const patches = writes.filter(w => w.method === 'PATCH')
    expect(patches).toHaveLength(1)
    const p = patches[0]
    // P 的次級選擇名為 section（A 才是 component）
    expect(p.url).toContain('/params/P/options/p_precise')
    expect(p.url).toContain('section=addon')
    expect(p.url).not.toContain('component=')
    // 定址鍵 code 不得出現在 PATCH body（改 code＝刪+建）
    const body = p.body as Record<string, unknown>
    expect(body.code).toBeUndefined()
    expect(body.delta_tmu).toBe(5)
    expect(body.max_select).toBe(2)          // 未改動的欄位沿用現值
    expect(body.display_rule).toBe('show_self')
    // 後端 extra='forbid' → 不得夾帶 API 回應的 id
    expect(body.id).toBeUndefined()
  })

  test('D4-D-2: 帶型儲存送 PUT /bands ＋ ?component= ＋ {items} 包裝（不含 id）', async ({ page }) => {
    const writes = await setup(page, { withDraft: true })
    await openDictionary(page)
    await openEditor(page, DRAFT.code)
    await page.getByRole('tab', { name: 'A 距離' }).click()

    const bands = page.getByTestId('dict-band-editor')
    await bands.getByLabel('指數 第 1 列').fill('2')
    await bands.getByRole('button', { name: '儲存帶' }).click()
    await expect(bands.getByText('帶已儲存')).toBeVisible()

    const puts = writes.filter(w => w.method === 'PUT')
    expect(puts).toHaveLength(1)
    const p = puts[0]
    expect(p.url).toContain('/params/A/bands')
    // A 的次級選擇名為 component（非 section）
    expect(p.url).toContain('component=reach')
    expect(p.url).not.toContain('section=')

    const body = p.body as { items: Record<string, unknown>[] }
    expect(Array.isArray(body.items)).toBe(true)
    expect(body.items).toHaveLength(3)                    // 整組替換，不是單筆
    expect(body.items[0].index_value).toBe(2)             // 改到的值
    expect(body.items[0].max_value).toBe(2.5)
    expect(body.items[2].max_value).toBeNull()            // 末帶維持開放
    for (const it of body.items) expect(it.id).toBeUndefined()
  })

  test('D4-D-3: 切換啟用 toggle 送 PATCH，body 僅含 is_active', async ({ page }) => {
    const writes = await setup(page, { withDraft: true })
    await openDictionary(page)
    await openEditor(page, DRAFT.code)
    await page.getByRole('tab', { name: 'G 取得控制' }).click()
    // 用 click 而非 uncheck：checkbox 是受控元件，值來自 API，而 mock 固定回 is_active:true，
    // 重取後會彈回勾選；本測試要驗的是**送出的請求**，不是視覺最終狀態。
    await page.getByLabel('啟用 g_tap').click()
    await expect(page.getByText('切換啟用成功')).toBeVisible()

    const patches = writes.filter(w => w.method === 'PATCH')
    expect(patches).toHaveLength(1)
    expect(patches[0].url).toContain('/params/G/options/g_tap')
    expect(patches[0].body).toEqual({ is_active: false })
  })
})

test.describe('§D4-2 clone-on-write', () => {
  test('D4-2-1: 在已發布版按編輯動作 → 跳確認 dialog（使用者不撞 409）', async ({ page }) => {
    await setup(page)
    await openDictionary(page)
    await openEditor(page, V2.code)
    await page.getByRole('tab', { name: 'G 取得控制' }).click()
    await page.getByTestId('dict-option-g_grasp').getByRole('button', { name: '編輯' }).click()

    const dialog = page.getByTestId('dict-clone-dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText(/是否建立草稿版本後編輯/)).toBeVisible()
    await expect(dialog.getByText(/認證匯入版本不可直接編輯/)).toBeVisible()
    await expect(dialog.getByRole('button', { name: '建立草稿版本' })).toBeVisible()
  })

  test('D4-2-2: 確認後建立草稿，但**不自動跳轉**，且明講修改未被套用', async ({ page }) => {
    const writes = await setup(page)
    await openDictionary(page)
    await openEditor(page, V2.code)
    await page.getByRole('tab', { name: 'G 取得控制' }).click()
    await page.getByTestId('dict-option-g_grasp').getByRole('button', { name: '編輯' }).click()
    await page.getByTestId('dict-clone-dialog').getByRole('button', { name: '建立草稿版本' }).click()

    const done = page.getByTestId('dict-clone-created')
    await expect(done).toBeVisible()
    await expect(done.getByText(DRAFT.code)).toBeVisible()
    await expect(done.getByText(/未.*套用到草稿/)).toBeVisible()

    // 仍停在原版本（未自動跳轉），且沒有開啟編輯表單、沒有假成功橫幅
    await expect(page.getByTestId('dict-option-editor').getByText(V2.code)).toBeVisible()
    await expect(page.getByText('編輯成功')).toHaveCount(0)
    expect(writes.filter(w => w.method === 'PATCH')).toHaveLength(0)

    // 由使用者按鈕決定前往
    await done.getByRole('button', { name: '前往草稿' }).click()
    await expect(page.getByTestId('dict-option-editor').getByText(DRAFT.code)).toBeVisible()
  })

  test('D4-2-2b: 帶型改值後觸發 clone → 訊息可見、未跳轉、且編輯內容保留（不靜默丟失）', async ({ page }) => {
    const writes = await setup(page)
    await openDictionary(page)
    await openEditor(page, V2.code)
    await page.getByRole('tab', { name: 'A 距離' }).click()

    const bands = page.getByTestId('dict-band-editor')
    await bands.getByLabel('指數 第 1 列').fill('9')
    await bands.getByRole('button', { name: '儲存帶' }).click()

    // clone 確認 → 建立
    await page.getByTestId('dict-clone-dialog').getByRole('button', { name: '建立草稿版本' }).click()
    const done = page.getByTestId('dict-clone-created')
    await expect(done).toBeVisible()
    await expect(done.getByText(/未.*套用到草稿/)).toBeVisible()

    await done.getByRole('button', { name: '留在此頁' }).click()
    // 未寫入、未跳轉、使用者輸入的 9 仍在畫面上（未靜默丟失），且仍標示未儲存
    expect(writes.filter(w => w.method === 'PUT')).toHaveLength(0)
    await expect(page.getByTestId('dict-option-editor').getByText(V2.code)).toBeVisible()
    await expect(bands.getByLabel('指數 第 1 列')).toHaveValue('9')
    await expect(bands.getByText('有未儲存的變更')).toBeVisible()
    await expect(bands.getByText('帶已儲存')).toHaveCount(0)
  })

  test('D4-2-3: 取消則不建立草稿、留在原版本', async ({ page }) => {
    const writes = await setup(page)
    await openDictionary(page)
    await openEditor(page, V2.code)
    await page.getByRole('tab', { name: 'G 取得控制' }).click()
    await page.getByTestId('dict-option-g_grasp').getByRole('button', { name: '編輯' }).click()
    await page.getByTestId('dict-clone-dialog').getByRole('button', { name: '取消' }).click()

    await expect(page.getByTestId('dict-clone-dialog')).toHaveCount(0)
    await expect(page.getByTestId('dict-option-editor').getByText(V2.code)).toBeVisible()
    expect(writes.filter(w => w.url.includes('/clone-draft'))).toHaveLength(0)
  })
})

// ── 必修 C：開 dialog 不得宣告成功 ────────────────────────────────────
test.describe('§D4-C 假成功回饋', () => {
  test('D4-C-1: 在 draft 點「編輯」只開表單，不得出現成功橫幅；取消後仍無', async ({ page }) => {
    await setup(page, { withDraft: true })
    await openDictionary(page)
    await openEditor(page, DRAFT.code)
    await page.getByRole('tab', { name: 'G 取得控制' }).click()
    await page.getByTestId('dict-option-g_tap').getByRole('button', { name: '編輯' }).click()

    // dialog 開了，但什麼都還沒存
    const dlg = page.getByTestId('dict-option-dialog')
    await expect(dlg).toBeVisible()
    await expect(dlg.getByText('編輯字典選項')).toBeVisible()
    await expect(page.getByText('編輯成功')).toHaveCount(0)

    await dlg.getByRole('button', { name: '取消' }).click()
    await expect(page.getByText('編輯成功')).toHaveCount(0)
    await expect(page.getByText('已儲存')).toHaveCount(0)
  })

  test('D4-C-2: 點「+ 新增」只開表單，不得出現「新增成功」', async ({ page }) => {
    await setup(page, { withDraft: true })
    await openDictionary(page)
    await openEditor(page, DRAFT.code)
    await page.getByRole('tab', { name: 'G 取得控制' }).click()
    await page.getByRole('button', { name: /\+ 新增取得控制/ }).click()

    await expect(page.getByTestId('dict-option-dialog').getByText('新增字典選項')).toBeVisible()
    await expect(page.getByText('新增成功')).toHaveCount(0)
  })
})

// ── D3b：刪除草稿 / 解除封存（反向操作） ─────────────────────────────
test.describe('§D4-B 反向操作（D3b）', () => {
  test('D4-B-1: 刪除 draft 需打字確認，確認後送 DELETE /rule-sets/{code}', async ({ page }) => {
    const writes = await setup(page, { withDraft: true })
    await openDictionary(page)

    const row = page.getByTestId(`dict-version-${DRAFT.code}`)
    await row.getByRole('button', { name: '刪除' }).click()

    const dlg = page.getByTestId('dict-confirm-dialog')
    await expect(dlg.getByText(/此操作不可逆/)).toBeVisible()
    const btn = dlg.getByRole('button', { name: '確認刪除' })
    // 未打字 → 不可按，且尚未送出
    await expect(btn).toBeDisabled()
    expect(writes.filter(w => w.method === 'DELETE')).toHaveLength(0)

    await dlg.locator('#confirm-code').fill(DRAFT.code)
    await expect(btn).toBeEnabled()
    await btn.click()
    await expect(page.getByText('刪除成功')).toBeVisible()

    const dels = writes.filter(w => w.method === 'DELETE')
    expect(dels).toHaveLength(1)
    expect(dels[0].url).toContain(`/api/v2/rule-sets/${DRAFT.code}`)
    // 版本級刪除，不是選項級
    expect(dels[0].url).not.toContain('/params/')
    // 刪除後清單不再有該草稿
    await expect(page.getByTestId(`dict-version-${DRAFT.code}`)).toHaveCount(0)
  })

  test('D4-B-2: 刪除被 RULE_SET_IN_USE 擋下時顯示各表引用筆數（人話）', async ({ page }) => {
    await setup(page, { withDraft: true, deleteInUse: true })
    await openDictionary(page)

    await page.getByTestId(`dict-version-${DRAFT.code}`).getByRole('button', { name: '刪除' }).click()
    const dlg = page.getByTestId('dict-confirm-dialog')
    await dlg.locator('#confirm-code').fill(DRAFT.code)
    await dlg.getByRole('button', { name: '確認刪除' }).click()

    // references: {most_cycles: 3, motion_module_versions: 1} → 人話
    await expect(dlg.getByText(/3 筆動作循環/)).toBeVisible()
    await expect(dlg.getByText(/1 筆動作模組版本/)).toBeVisible()
    await expect(dlg.getByText(/無法刪除/)).toBeVisible()
    // 沒被誤報成成功，草稿仍在
    await expect(page.getByText('刪除成功')).toHaveCount(0)
    await expect(page.getByTestId(`dict-version-${DRAFT.code}`)).toBeVisible()
  })

  test('D4-B-3: 封存確認框已無「不可逆」字樣，且不需打字（可逆操作）', async ({ page }) => {
    await setup(page)
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '封存' }).click()

    const dlg = page.getByTestId('dict-confirm-dialog')
    await expect(dlg.getByText(/可再解除封存/)).toBeVisible()
    await expect(dlg.getByText(/不可逆/)).toHaveCount(0)
    await expect(dlg.getByText(/沒有「取消封存」功能/)).toHaveCount(0)
    // 保留：回放不受影響
    await expect(dlg.getByText(/回放不受影響/)).toBeVisible()
    // 可逆 → 不要求打字，直接可按
    await expect(dlg.locator('#confirm-code')).toHaveCount(0)
    await expect(dlg.getByRole('button', { name: '確認封存' })).toBeEnabled()
  })

  test('D4-B-4: 解除封存 → 回到已發布，且**未**變成啟用中', async ({ page }) => {
    const writes = await setup(page, { withRetired: true })
    await openDictionary(page)

    const row = page.getByTestId(`dict-version-${RETIRED.code}`)
    await expect(row.getByText('已封存')).toBeVisible()
    await row.getByRole('button', { name: '解除封存' }).click()

    const dlg = page.getByTestId('dict-confirm-dialog')
    // 必須明說解封 ≠ 啟用
    await expect(dlg.getByText(/仍不是啟用中版本/)).toBeVisible()
    await dlg.getByRole('button', { name: '確認解除封存' }).click()
    await expect(page.getByText('解除封存成功')).toBeVisible()

    expect(writes.filter(w => w.url.includes('/unretire'))).toHaveLength(1)
    // 狀態回到已發布，但不是啟用中（啟用中仍是 V2）
    const after = page.getByTestId(`dict-version-${RETIRED.code}`)
    await expect(after.getByText('已發布')).toBeVisible()
    await expect(after.getByText('啟用中')).toHaveCount(0)
    await expect(page.getByTestId(`dict-version-${V2.code}`).getByText('啟用中')).toBeVisible()
  })

  test('D4-B-5: 只有 draft 有刪除鈕；published/retired 沒有', async ({ page }) => {
    await setup(page, { withDraft: true, withRetired: true })
    await openDictionary(page)

    await expect(page.getByTestId(`dict-version-${DRAFT.code}`).getByRole('button', { name: '刪除' })).toBeEnabled()
    await expect(page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '刪除' })).toHaveCount(0)
    await expect(page.getByTestId(`dict-version-${V2.code}`).getByRole('button', { name: '刪除' })).toHaveCount(0)
    await expect(page.getByTestId(`dict-version-${RETIRED.code}`).getByRole('button', { name: '刪除' })).toHaveCount(0)
  })
})

// ── D8：發布/啟用前的版本差異（H-1 覆核者資訊） ────────────────────
test.describe('§D8 版本差異', () => {
  test('D8-1: 發布確認框內嵌 summary，並標明比較基準 base_code', async ({ page }) => {
    const writes = await setup(page, { withDraft: true })
    await openDictionary(page)
    await page.getByTestId(`dict-version-${DRAFT.code}`).getByRole('button', { name: '發布' }).click()

    const dlg = page.getByTestId('dict-confirm-dialog')
    await expect(dlg).toBeVisible()
    const sum = dlg.getByTestId('diff-summary')
    await expect(sum).toBeVisible()
    // 新增/刪除/變更筆數
    await expect(sum.getByText('新增')).toBeVisible()
    await expect(sum.getByText('刪除')).toBeVisible()
    await expect(sum.getByText('變更')).toBeVisible()
    // 受影響區塊以中文顯示
    await expect(sum.getByText(/G 取得控制/)).toBeVisible()
    // 必須標明比較基準
    await expect(dlg.getByTestId('diff-view').getByText(V2.code, { exact: true }).first()).toBeVisible()
    await expect(dlg.getByText(/目前啟用中/)).toBeVisible()
    // 尚未確認 → 不得已送出
    expect(writes.filter(w => w.url.includes('/publish'))).toHaveLength(0)

    await dlg.getByRole('button', { name: '確認發布' }).click()
    await expect(page.getByText('發布成功')).toBeVisible()
    const pubs = writes.filter(w => w.url.includes('/publish'))
    expect(pubs).toHaveLength(1)
    expect(pubs[0].method).toBe('POST')
    expect(pubs[0].url).toContain(DRAFT.code)
  })

  test('D8-2: 啟用確認框同時有「不回溯」警語與差異（警語才完整）', async ({ page }) => {
    await setup(page)
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '啟用' }).click()

    const dlg = page.getByTestId('dict-confirm-dialog')
    await expect(dlg.getByText(/不會回溯修正已建立的資料/)).toBeVisible()
    await expect(dlg.getByTestId('diff-summary')).toBeVisible()
  })

  test('D8-3: 展開逐欄差異可見前後值，且 TMU 欄標示「影響工時」', async ({ page }) => {
    await setup(page)
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '檢視差異' }).click()

    const panel = page.getByTestId('dict-diff-panel')
    await expect(panel).toBeVisible()
    const detail = panel.getByTestId('diff-detail')
    await expect(detail).toBeVisible()
    // g_grasp 的 base_tmu 6 → 12
    await expect(detail.getByText('g_grasp')).toBeVisible()
    await expect(detail.getByText('6', { exact: true })).toBeVisible()
    await expect(detail.getByText('12', { exact: true })).toBeVisible()
    // 值欄要被標為影響工時；文案欄不標
    await expect(detail.getByText('影響工時').first()).toBeVisible()
    // 整批換掉的區塊：列數 before→after 可見
    await expect(detail.getByText(/列數 11 → 11/)).toBeVisible()
  })

  test('D8-4: base_is_source=false → 顯示後端 lineage_note（不自造句）', async ({ page }) => {
    const note = '比較基準是目前 active 的 V2，但本版是從 V0 clone 出來的——不可全部視為本次改動。'
    await setup(page, {
      diff: makeDiff({ source_code: 'MINIMOST_FACTORY_V0', base_is_source: false, lineage_note: note }),
    })
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '檢視差異' }).click()

    const warn = page.getByTestId('diff-lineage-warning')
    await expect(warn).toBeVisible()
    await expect(warn.getByText(note)).toBeVisible()
  })

  test('D8-5: source_code=null → 說明無法判斷血緣（不猜成來自 active）', async ({ page }) => {
    await setup(page)   // 預設 source_code: null
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '檢視差異' }).click()

    const unknown = page.getByTestId('diff-lineage-unknown')
    await expect(unknown).toBeVisible()
    await expect(unknown.getByText(/無法判斷血緣/)).toBeVisible()
    await expect(page.getByTestId('diff-lineage-warning')).toHaveCount(0)
  })

  test('D8-6: compared_with_self 與 identical 是不同文案（不得都說「無差異」）', async ({ page }) => {
    // (a) 本版就是 active → 沒有比較對象
    await setup(page, { diff: makeDiff({ compared_with_self: true, target_code: V2.code }) })
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V2.code}`).getByRole('button', { name: '檢視差異' }).click()
    const self = page.getByTestId('diff-self')
    await expect(self).toBeVisible()
    await expect(self.getByText(/沒有可比較的基準/)).toBeVisible()
    await expect(page.getByTestId('diff-identical')).toHaveCount(0)
    const selfText = (await self.textContent()) ?? ''
    await page.getByTestId('dict-diff-panel').getByRole('button', { name: '關閉' }).last().click()

    // (b) 逐欄相同 → 明說完全相同
    await setup(page, { diff: IDENTICAL_DIFF })
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '檢視差異' }).click()
    const ident = page.getByTestId('diff-identical')
    await expect(ident).toBeVisible()
    await expect(ident.getByText(/逐欄比對完全相同/)).toBeVisible()
    await expect(page.getByTestId('diff-self')).toHaveCount(0)

    // 兩者文案必須不同（都顯示同一句就是空洞通過）
    const identText = (await ident.textContent()) ?? ''
    expect(identText.trim()).not.toBe(selfText.trim())
  })

  test('D8-7: diff 載入失敗 → 顯示錯誤，且確認鈕不可按（不靜默放行）', async ({ page }) => {
    const writes = await setup(page, { withDraft: true, diff: 'error' })
    await openDictionary(page)
    await page.getByTestId(`dict-version-${DRAFT.code}`).getByRole('button', { name: '發布' }).click()

    const dlg = page.getByTestId('dict-confirm-dialog')
    await expect(dlg.getByTestId('diff-error')).toBeVisible()
    await expect(dlg.getByText(/無法取得版本差異/)).toBeVisible()
    // 不得當成「沒有差異」而放行
    await expect(dlg.getByRole('button', { name: '確認發布' })).toBeDisabled()
    await expect(dlg.getByTestId('confirm-blocked-reason')).toBeVisible()
    await expect(dlg.getByTestId('diff-summary')).toHaveCount(0)
    await expect(dlg.getByTestId('diff-identical')).toHaveCount(0)
    expect(writes.filter(w => w.url.includes('/publish'))).toHaveLength(0)
  })

  test('D8-8: 「檢視差異」只對 draft/published 顯示；retired 沒有', async ({ page }) => {
    await setup(page, { withDraft: true, withRetired: true })
    await openDictionary(page)
    for (const code of [DRAFT.code, V1.code, V2.code]) {
      await expect(page.getByTestId(`dict-version-${code}`).getByRole('button', { name: '檢視差異' })).toBeVisible()
    }
    await expect(page.getByTestId(`dict-version-${RETIRED.code}`).getByRole('button', { name: '檢視差異' })).toHaveCount(0)
  })

  test('D8-9: diff 走 GET /rule-sets/{code}/diff（method 與 URL 契約）', async ({ page }) => {
    const seen: { method: string; url: string }[] = []
    await setup(page)
    // 後註冊者優先：spy 記錄後 fallback 給 setup 的處理器回實際資料
    await page.route('**/diff*', async route => {
      seen.push({ method: route.request().method(), url: route.request().url() })
      await route.fallback()
    })
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '檢視差異' }).click()
    await expect(page.getByTestId('diff-view')).toBeVisible()

    expect(seen.length).toBeGreaterThan(0)
    expect(seen[0].method).toBe('GET')
    expect(seen[0].url).toContain(`/api/v2/rule-sets/${V1.code}/diff`)
  })
})

// ── D8b：「值未變動」的判準（兩案例互為對照，單獨一個會空洞通過） ──
test.describe('§D8b 值未變動 vs 乘數變動', () => {
  test('D8b-1: 區塊 0/0/0 ＋ header 僅 name_zh → 顯示「值未變動」', async ({ page }) => {
    await setup(page, { diff: NAME_ONLY_DIFF })
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '檢視差異' }).click()

    const banner = page.getByTestId('diff-values-unchanged')
    await expect(banner).toBeVisible()
    await expect(banner.getByText(/僅版本名稱不同/)).toBeVisible()
    // 不得同時出現乘數警示
    await expect(page.getByTestId('diff-multiplier-warning')).toHaveCount(0)
  })

  test('D8b-2: 區塊 0/0/0 ＋ header 含 multiplier → 不得說「值未變動」，且乘數警示可見', async ({ page }) => {
    await setup(page, { diff: MULTIPLIER_ONLY_DIFF })
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '檢視差異' }).click()

    const panel = page.getByTestId('dict-diff-panel')
    // 這是本組的核心：乘數會等比縮放所有 TMU，絕不能宣告「值未變動」
    await expect(panel.getByTestId('diff-values-unchanged')).toHaveCount(0)
    await expect(panel.getByText('值未變動')).toHaveCount(0)

    const warn = panel.getByTestId('diff-multiplier-warning')
    await expect(warn).toBeVisible()
    await expect(warn.getByText(/等比影響本版所有工時/)).toBeVisible()
    await expect(warn.getByText(/TMU 乘數/)).toBeVisible()
    // 逐欄仍看得到 1 → 1.05
    await expect(panel.getByTestId('diff-detail').getByText('1.05')).toBeVisible()
  })

  test('D8b-3: 有區塊變更時兩種橫幅都不出現（判準要求區塊零變更）', async ({ page }) => {
    await setup(page)   // 預設 fixture：g 區塊有增刪改
    await openDictionary(page)
    await page.getByTestId(`dict-version-${V1.code}`).getByRole('button', { name: '檢視差異' }).click()

    await expect(page.getByTestId('diff-summary')).toBeVisible()
    await expect(page.getByTestId('diff-values-unchanged')).toHaveCount(0)
    await expect(page.getByTestId('diff-multiplier-warning')).toHaveCount(0)
  })
})
