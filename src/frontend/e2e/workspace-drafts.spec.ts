/**
 * ADR-038 W4：工作區畫面（編輯區、三種輸入、寫入工時表）。
 *
 * 全部 /api/** 由 page.route 攔截，編輯區由一個記憶體內的假後端（FakeDrafts）模擬狀態機：
 * 新增→pending、確認→confirmed、寫入→committed。非 GET 的未預期端點一律 500（不讓前端靜默打錯端點）。
 *
 * 涵蓋（delivery plan〈W4〉第 6、7 項）：
 * - 手動新增 → 進編輯區（不是直接進工時表）→ 確認 → 寫入（帶 base_revision）
 * - 單句 → 一組草稿 → 整組確認 → 寫入；AI 降級訊息
 * - 寫入 409（版本衝突）→ 提示並保留已確認；409 DRAFT_INCOMPLETE 顯示對應文案
 * - 過期與不完整的標示；編輯草稿 → PATCH；表上有未存檔修改時擋寫入
 * - 畫面上不再有「採用到編輯器」
 */
import { test, expect, type Page, type Route } from '@playwright/test'

test.setTimeout(60_000)

const WS = 'ws-w4'
const ADMIN_ME = { employee_no: 'IEC141289', roles: ['admin'], level: 3 }
const MOCK_CASES = {
  total: 1,
  items: [{
    process_version_id: 'pv-w4', worksheet_id: WS, version_no: 'v1', status: 'draft',
    site_id: 'st-1', site_name: 'Site A', product_id: 'p1', product_name: 'Product X',
    sku_id: 'sk1', sku_name: 'SKU 001', process_name: '工作區測試', total_tmu: 0,
    created_at: '2026-01-01T00:00:00Z', approved_at: null, model_label: null, version_count: 1,
    versions: [{ process_version_id: 'pv-w4', worksheet_id: WS, version_no: 'v1',
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
const IMPORT = 'imp-w5'
const GM = { seq: 'GM', rule_set_code: 'MINIMOST_FACTORY_V2', a0: { reach_cm: 5 }, g2: { g_code: 'g_simple' } }

interface Draft {
  id: string; worksheet_id: string; group_key: string; order_in_group: number; sort_order: number
  source: string; status: string; content: Record<string, unknown>
  ai_candidates: null; ai_parse_run_id: null; import_row_id: null; source_revision: number
  created_by: string; created_at: string; updated_by: string | null; updated_at: string
  confirmed_by: string | null; confirmed_at: string | null; committed_by: string | null
  committed_at: string | null; committed_wi_row_id: string | null
  source_rule_set_id: null; parse_snapshot: Record<string, unknown> | null; stale_reason: string | null
}

class FakeDrafts {
  drafts: Draft[] = []
  revision = 1
  rows: Array<Record<string, unknown>> = []
  commits: Array<Record<string, unknown>> = []
  saves: Array<Record<string, unknown>> = []
  patches: Array<Record<string, unknown>> = []
  uploadQuery: string | null = null
  jobBody: Record<string, unknown> | null = null
  jobPolls = 0
  blankRequests: string[][] = []
  sentence: { status: 'ai_service' | 'degraded' | 'rule_based'; reason?: { error_kind: string } } = { status: 'rule_based' }
  commitFails: Array<{ status: number; code: string }> = []
  private n = 0

  add(content: Record<string, unknown>, extra: Partial<Draft> = {}): Draft {
    this.n += 1
    const now = new Date().toISOString()
    const d: Draft = {
      id: `d${this.n}`, worksheet_id: WS, group_key: extra.group_key ?? `g${this.n}`, order_in_group: 0,
      sort_order: this.n, source: 'manual', status: 'pending', content, ai_candidates: null,
      ai_parse_run_id: null, import_row_id: null, source_revision: this.revision, created_by: 'IEC141289',
      created_at: now, updated_by: null, updated_at: now, confirmed_by: null, confirmed_at: null,
      committed_by: null, committed_at: null, committed_wi_row_id: null, source_rule_set_id: null,
      parse_snapshot: null, stale_reason: null, ...extra,
    }
    this.drafts.push(d)
    return d
  }

  worksheet() {
    return { worksheet_id: WS, status: 'draft', total_tmu: 0, rows: this.rows, default_rule_set: null,
      revision_no: this.revision, content_hash: null, distance_check_required: false }
  }
}

function install(page: Page, fake: FakeDrafts) {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const err = (route: Route, status: number, code: string, detail: Record<string, unknown> = {}) =>
    json(route, { error: { code, message: code, detail: { code, ...detail } } }, status)

  return page.route('/api/**', async route => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()
    const body = () => JSON.parse(req.postData() ?? '{}')

    if (path === `/api/v2/worksheets/${WS}/drafts` && method === 'GET')
      return json(route, { worksheet_id: WS, items: fake.drafts })
    if (path === `/api/v2/worksheets/${WS}/drafts` && method === 'POST') {
      const items = (body().items as Array<{ content: Record<string, unknown> }>).map(i => fake.add(i.content))
      return json(route, { worksheet_id: WS, items }, 201)
    }
    if (path === `/api/v2/worksheets/${WS}/drafts/confirm` && method === 'POST') {
      const b = body()
      const hit = fake.drafts.filter(d => (b.draft_ids ? b.draft_ids.includes(d.id) : d.group_key === b.group_key))
      const incomplete = hit.filter(d => d.status === 'pending' && d.parse_snapshot?.complete === false)
      if (incomplete.length)
        return err(route, 409, 'DRAFT_INCOMPLETE', { incomplete_count: incomplete.length, draft_ids: incomplete.map(d => d.id) })
      for (const d of hit) if (d.status === 'pending') { d.status = 'confirmed'; d.confirmed_by = 'IEC141289'; d.confirmed_at = 'x' }
      return json(route, { worksheet_id: WS, items: hit })
    }
    if (path === `/api/v2/worksheets/${WS}/drafts/commit` && method === 'POST') {
      const b = body()
      fake.commits.push(b)
      const fail = fake.commitFails.shift()
      if (fail) return err(route, fail.status, fail.code, { current_revision: String(fake.revision + 1) })
      if (b.base_revision !== fake.revision) return err(route, 409, 'WORKSHEET_REVISION_CONFLICT')
      const done = fake.drafts.filter(d => d.status === 'confirmed')
      for (const d of done) {
        d.status = 'committed'; d.committed_by = 'IEC141289'; d.committed_at = 'x'; d.committed_wi_row_id = `r-${d.id}`
        fake.rows.push({ wi_row_id: `r-${d.id}`, seq_no: fake.rows.length + 1, hand: 'RH', sub_activity: null,
          key_parts: null, object_vocab_id: null, from_vocab_id: null, to_vocab_id: null, tool_vocab_id: null,
          frequency: 1, simo_group_id: null, wi_group: (d.content.wi_group as string) ?? null, distance_status: null,
          source_module_id: null, source_module_version: null,
          cycle: { seq_kind: 'GM', total_tmu: 10, total_seconds: 0.36, narrative: `已寫入 ${d.id}`, narrative_en: null,
            slot_inputs: d.content.cycle, rule_set_id: 'rs-1', breakdown: [] },
          level: null, lb_tags: null })
      }
      fake.revision += 1
      return json(route, { worksheet_id: WS, revision_no: fake.revision, committed: done })
    }
    const patch = path.match(/^\/api\/v2\/worksheet-drafts\/([^/]+)$/)
    if (patch && method === 'PATCH') {
      const d = fake.drafts.find(x => x.id === patch[1])!
      fake.patches.push(body())
      d.content = body().content; d.status = 'pending'; d.confirmed_by = null; d.confirmed_at = null
      return json(route, d)
    }
    if (patch && method === 'DELETE') {
      fake.drafts = fake.drafts.filter(x => x.id !== patch[1])
      return route.fulfill({ status: 204 })
    }
    if (path === `/api/v2/worksheets/${WS}/drafts/from-sentence` && method === 'POST') {
      const b = body()
      const key = `s${fake.drafts.length + 1}`
      const source = fake.sentence.status === 'ai_service' ? 'ai_service' : 'rule_based'
      const snap = (complete: boolean) => ({ complete, issues: complete ? [] : ['missing_core_g'], cycle_hash: 'h',
        ai_status: fake.sentence.status, action_id: 'a', routing_status: 'review', wi_group_truncated: false })
      const items = [
        fake.add({ cycle: GM, wi_group: b.text, hand: b.hand, narrative: '拿起螺絲' }, { group_key: key, order_in_group: 0, source, parse_snapshot: snap(true) }),
        fake.add({ cycle: GM, wi_group: b.text, hand: b.hand, narrative: '放到治具' }, { group_key: key, order_in_group: 1, source, parse_snapshot: snap(true) }),
      ]
      return json(route, { worksheet_id: WS, group_key: key, items,
        ai: { run_id: null, status: fake.sentence.status, reason: fake.sentence.reason ?? null,
          routing_status: 'review', routing_reasons: [] } }, 201)
    }
    if (path === '/api/v2/imports/upload' && method === 'POST') {
      fake.uploadQuery = url.search.replace(/^\?/, '')
      return json(route, { import_id: IMPORT, source_name: 'w5.xlsx', target_fields: ['description'],
        required_fields: ['description'], suggested_sheet: 'S1', suggested_header_row: 0, profiles: [],
        sheets: [{ name: 'S1', n_rows: 3, n_cols: 1, grid: [['描述'], ['拿起螺絲'], ['長'.repeat(30)]] }] })
    }
    if (path === `/api/v2/imports/${IMPORT}/map` && method === 'POST')
      return json(route, { import_id: IMPORT, fields: ['description'], n: 2, warnings: [],
        rows: [{ description: '拿起螺絲' }, { description: '長'.repeat(30) }] })
    if (path === `/api/v2/imports/${IMPORT}/parse-jobs` && method === 'POST') {
      fake.jobBody = body()
      return json(route, { id: 'job-w5', import_id: IMPORT, status: 'queued', total: 2, processed: 0,
        succeeded: 0, review: 0, failed: 0 }, 201)
    }
    if (path === `/api/v2/imports/${IMPORT}/parse-jobs/job-w5` && method === 'GET') {
      fake.jobPolls += 1
      if (fake.jobPolls === 2) fake.add({ cycle: GM, narrative: '拿起螺絲' }, { source: 'rule_based', import_row_id: 'ir1' } as never)
      const done = fake.jobPolls >= 2
      return json(route, { id: 'job-w5', import_id: IMPORT, status: done ? 'completed' : 'running', total: 2,
        processed: done ? 2 : 0, succeeded: 0, review: done ? 2 : 0, failed: 0 })
    }
    if (path === `/api/v2/worksheets/${WS}/drafts/blank-from-import` && method === 'POST') {
      const ids = body().import_row_ids as string[]
      fake.blankRequests.push(ids)
      const made = ids.filter(id => !fake.drafts.some(d => d.import_row_id === id)).map(id =>
        fake.add({ cycle: { seq: 'GM' }, narrative: '長'.repeat(30) }, { source: 'imported', import_row_id: id,
          parse_snapshot: { complete: false, issues: ['blank_from_import'] } } as never))
      return json(route, { worksheet_id: WS, items: made }, 201)
    }
    if (path === `/api/v2/imports/${IMPORT}/parse-jobs/job-w5/items`) {
      const done = fake.jobPolls >= 2
      const has = (id: string) => fake.drafts.some(d => d.import_row_id === id)
      return json(route, { job_id: 'job-w5', items: done ? [
        { item_id: 'i1', import_row_id: 'ir1', source_row_no: 1, description: '拿起螺絲', status: 'review', has_drafts: has('ir1'), reason: null, ai_error_kind: null },
        { item_id: 'i2', import_row_id: 'ir2', source_row_no: 2, description: '長'.repeat(30), status: 'review', has_drafts: has('ir2'), reason: 'text_too_long', ai_error_kind: null },
      ] : [] })
    }
    if (path === '/api/v2/wi-ai/status') return json(route, { enabled: false, available: false })
    if (path === `/api/v2/worksheets/${WS}` && method === 'PUT') {
      // 整份存檔：前端不送 distance_status；後端（這裡模擬）把改了距離輸入的 confirmed 退回 null
      fake.saves.push(body())
      fake.revision += 1
      fake.rows = fake.rows.map(r => ({ ...r, distance_status: null }))
      return json(route, { ...fake.worksheet(), total_tmu: 10 })
    }
    if (path === `/api/v2/worksheets/${WS}`) return json(route, fake.worksheet())
    if (path === '/api/v2/minimost/calculate')
      return json(route, { seq: 'GM', total_tmu: 10, total_seconds: 0.36, tech_line: 'A1 B0 G1' })
    if (path === '/api/v2/me') return json(route, ADMIN_ME)
    if (path === '/api/v2/rule-sets/active') return json(route, { id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'v2' })
    if (path.startsWith('/api/v2/rule-sets/') && path.endsWith('/options')) return json(route, MOCK_OPTS)
    if (path === '/api/v2/cases') return json(route, MOCK_CASES)
    if (path === '/api/v2/audit-log') return json(route, { total: 0, items: [] })
    if (method === 'GET') return json(route, [])
    return json(route, { detail: `unexpected ${method} ${path}` }, 500)
  })
}

async function enterWorkspace(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: /分析案件/ }).click()
  await page.getByText('工作區測試').click()
  await page.getByRole('button', { name: '編輯工時表' }).click()
  await expect(page.getByTestId('draft-area')).toBeVisible()
}

async function waitAddable(page: Page) {
  // 編輯器的試算由後端（mock）回 10 TMU 後，加入按鈕才可用
  await expect(page.getByTestId('editor-add')).toBeEnabled()
}

test('手動新增進編輯區（不直接進工時表）→ 確認 → 寫入工時表（帶 base_revision）', async ({ page }) => {
  const fake = new FakeDrafts()
  await install(page, fake)
  await enterWorkspace(page)
  await expect(page.getByText('採用到編輯器')).toHaveCount(0)

  await page.getByTestId('editor-wi-group').fill('上料')
  await waitAddable(page)
  await page.getByTestId('editor-add').click()
  await expect(page.getByTestId('editor-msg')).toContainText('已加入編輯區')
  const row = page.getByTestId('draft-row')
  await expect(row).toHaveCount(1)
  await expect(row).toHaveAttribute('data-status', 'pending')
  await expect(page.getByTestId('draft-group-name')).toHaveText('上料')
  expect(fake.drafts[0].content.wi_group).toBe('上料')
  expect(fake.drafts[0].content.cycle).toBeTruthy()
  expect(fake.rows).toHaveLength(0)

  await expect(page.getByTestId('draft-commit')).toBeDisabled()
  await row.getByTestId('draft-confirm').click()
  await expect(row).toHaveAttribute('data-status', 'confirmed')
  await page.getByTestId('draft-commit').click()
  await expect(page.getByTestId('draft-msg')).toContainText('已寫入 1 列')
  expect(fake.commits).toEqual([{ base_revision: 1 }])
  await expect(page.getByText('已寫入 d1')).toBeVisible()  // 重新讀回工時表
  await expect(page.getByTestId('draft-row')).toHaveCount(0)  // 已寫入的紀錄預設隱藏
})

test('單句 → 一組草稿 → 整組確認 → 寫入；AI 降級時提示', async ({ page }) => {
  const fake = new FakeDrafts()
  fake.sentence.status = 'degraded'
  fake.sentence.reason = { error_kind: 'no_motion' }
  await install(page, fake)
  await enterWorkspace(page)
  await page.getByTestId('input-mode-sentence').click()
  await expect(page.getByTestId('ai-status')).toContainText('AI 解析未開啟')
  await page.getByTestId('sentence-text').fill('左手拿起螺絲放到治具')
  await page.getByTestId('sentence-submit').click()
  await expect(page.getByTestId('sentence-result')).toContainText('AI 判定這句沒有可建模的動作，已改用規則解析')
  await expect(page.getByTestId('draft-group')).toHaveCount(1)
  await expect(page.getByTestId('draft-row')).toHaveCount(2)
  await expect(page.getByTestId('draft-row').first()).toHaveAttribute('data-source', 'rule_based')
  await expect(page.getByTestId('draft-group-name')).toHaveText('左手拿起螺絲放到治具')

  await page.getByTestId('draft-confirm-group').click()
  await expect(page.getByTestId('draft-counts')).toContainText('已確認 2')
  await page.getByTestId('draft-commit').click()
  await expect(page.getByTestId('draft-msg')).toContainText('已寫入 2 列')
})

test('寫入遇到版本衝突：提示重新載入，草稿維持已確認，再按一次可寫入', async ({ page }) => {
  const fake = new FakeDrafts()
  fake.add({ cycle: GM, narrative: '甲' }, { status: 'confirmed', confirmed_by: 'x', confirmed_at: 'x' })
  fake.commitFails.push({ status: 409, code: 'WORKSHEET_REVISION_CONFLICT' })
  await install(page, fake)
  await enterWorkspace(page)
  await page.getByTestId('draft-commit').click()
  await expect(page.getByTestId('draft-msg')).toContainText('已被其他人更新')
  await expect(page.getByTestId('draft-row')).toHaveAttribute('data-status', 'confirmed')
  await page.getByTestId('draft-commit').click()
  await expect(page.getByTestId('draft-msg')).toContainText('已寫入 1 列')
})

test('不完整與過期的標示；確認不完整的草稿 → 409 DRAFT_INCOMPLETE 文案；編輯後 PATCH 回到待確認', async ({ page }) => {
  const fake = new FakeDrafts()
  fake.add({ cycle: { seq: 'GM' }, narrative: '缺格位' }, {
    source: 'ai_service', parse_snapshot: { complete: false, issues: ['missing_core_g'], wi_group_truncated: true },
  })
  fake.add({ cycle: GM, narrative: '過期' }, { stale_reason: 'import_row_changed', source: 'imported' })
  await install(page, fake)
  await enterWorkspace(page)
  const [incomplete, stale] = [page.getByTestId('draft-row').nth(0), page.getByTestId('draft-row').nth(1)]
  await expect(incomplete.getByTestId('draft-incomplete')).toBeVisible()
  await expect(incomplete.getByTestId('draft-issues')).toContainText('missing_core_g')
  await expect(incomplete).toContainText('已截斷')
  await expect(stale.getByTestId('draft-stale')).toContainText('刪除這列後重新解析')

  await incomplete.getByTestId('draft-confirm').click()
  await expect(page.getByTestId('draft-msg')).toContainText('解析不完整')
  await expect(incomplete).toHaveAttribute('data-status', 'pending')

  await incomplete.getByTestId('draft-edit').click()
  await expect(page.getByTestId('editing-draft')).toBeVisible()
  await waitAddable(page)
  await page.getByTestId('editor-add').click()
  await expect(page.getByTestId('editor-msg')).toContainText('草稿已更新')
  expect(fake.patches).toHaveLength(1)
  expect(fake.patches[0].content).toMatchObject({ narrative: '缺格位' })
})

test('表上有未存檔的修改時擋「寫入工時表」', async ({ page }) => {
  const fake = new FakeDrafts()
  fake.rows.push({ wi_row_id: 'r0', seq_no: 1, hand: 'RH', sub_activity: null, key_parts: null,
    object_vocab_id: null, from_vocab_id: null, to_vocab_id: null, tool_vocab_id: null, frequency: 1,
    simo_group_id: null, wi_group: null, distance_status: null, source_module_id: null, source_module_version: null,
    cycle: { seq_kind: 'GM', total_tmu: 10, total_seconds: 0.36, narrative: '既有列', narrative_en: null,
      slot_inputs: GM, rule_set_id: 'rs-1', breakdown: [] }, level: null, lb_tags: null })
  fake.add({ cycle: GM, narrative: '甲' }, { status: 'confirmed', confirmed_by: 'x', confirmed_at: 'x' })
  await install(page, fake)
  await enterWorkspace(page)
  await expect(page.getByText('既有列')).toBeVisible()
  // 在表上刪掉既有列（本地修改、尚未存檔）
  page.once('dialog', d => d.accept())
  await page.getByRole('row').filter({ hasText: '既有列' }).getByRole('button').last().click()
  await page.getByTestId('draft-commit').click()
  await expect(page.getByTestId('draft-msg')).toContainText('先按「儲存」')
  expect(fake.commits).toHaveLength(0)
})


test('整份存檔不送距離狀態；已確認的距離被後端退回時提示', async ({ page }) => {
  const fake = new FakeDrafts()
  fake.rows.push({ wi_row_id: 'r0', seq_no: 1, hand: 'RH', sub_activity: null, key_parts: null,
    object_vocab_id: null, from_vocab_id: null, to_vocab_id: null, tool_vocab_id: null, frequency: 1,
    simo_group_id: null, wi_group: null, distance_status: 'confirmed', source_module_id: null, source_module_version: null,
    cycle: { seq_kind: 'GM', total_tmu: 10, total_seconds: 0.36, narrative: '既有列', narrative_en: null,
      slot_inputs: GM, rule_set_id: 'rs-1', breakdown: [] }, level: null, lb_tags: null })
  await install(page, fake)
  await enterWorkspace(page)
  await expect(page.getByText('既有列')).toBeVisible()
  await page.getByRole('button', { name: '儲存', exact: true }).click()
  await expect(page.getByText('距離狀態已退回未標示')).toBeVisible()
  const sent = (fake.saves[0].rows as Array<Record<string, unknown>>)[0]
  expect('distance_status' in sent).toBe(false)
})

test('編輯草稿不改格位就存：原 cycle 原封保留（含編輯器放不下的多個 M 分量），並提示會被簡化的情況', async ({ page }) => {
  const fake = new FakeDrafts()
  const cm = { seq: 'CM', rule_set_code: 'MINIMOST_FACTORY_V2', a0: { reach_cm: 5 }, g2: { g_code: 'g_simple' },
    m3: { m_components: [{ verb_code: 'm_push', distance_cm: 12 }, { verb_code: 'm_push', distance_cm: 30 }] } }
  fake.add({ cycle: cm, narrative: 'AI 兩段推' }, { source: 'ai_service' })
  await install(page, fake)
  await enterWorkspace(page)
  await page.getByTestId('draft-edit').click()
  await expect(page.getByTestId('editing-simplify')).toBeVisible()
  await waitAddable(page)
  await page.getByTestId('editor-add').click()
  await expect(page.getByTestId('editor-msg')).toContainText('草稿已更新')
  expect(fake.patches[0].content).toMatchObject({ cycle: cm, narrative: 'AI 兩段推' })
})

test('整份上傳：上傳（綁工時表）→ 欄位對應 → 開始解析 → 進度 → 草稿出現 → 沒草稿的列建空白草稿 → 確認 → 寫入', async ({ page }) => {
  const fake = new FakeDrafts()
  await install(page, fake)
  await enterWorkspace(page)
  await page.getByTestId('input-mode-upload').click()
  await page.getByTestId('upload-open').click()
  await expect(page.getByRole('heading', { name: /匯入 Excel/ })).toBeVisible()
  await page.setInputFiles('input[type=file]',
    { name: 'w5.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('x') })
  await page.locator('label', { hasText: '描述（必）' }).locator('select').selectOption('0')
  await page.getByRole('button', { name: '預覽' }).click()
  await expect(page.getByTestId('import-drafts-confirm')).toBeVisible()
  await page.getByTestId('import-start-parse').click()
  expect(fake.uploadQuery).toBe(`worksheet_id=${WS}`)
  expect(fake.jobBody).toEqual({ rule_set_code: 'MINIMOST_FACTORY_V2', idempotency_key: `workspace:${IMPORT}` })
  await expect(page.getByRole('heading', { name: /匯入 Excel/ })).toHaveCount(0)

  await expect(page.getByTestId('upload-counts')).toContainText('已處理 2／2 列', { timeout: 15_000 })
  await expect(page.getByTestId('draft-row')).toHaveCount(1)
  await expect(page.getByTestId('upload-missing-row')).toHaveCount(1)
  await expect(page.getByTestId('upload-missing-row')).toContainText('描述超過 2000 字')
  await page.getByTestId('upload-blank-all').click()
  await expect(page.getByTestId('upload-msg')).toContainText('已建立 1 列空白草稿')
  await expect(page.getByTestId('draft-row')).toHaveCount(2)
  expect(fake.blankRequests).toEqual([['ir2']])
  await expect(page.getByTestId('upload-missing-row')).toHaveCount(0)  // 有草稿了：不再列出，也就不會重複建
  await expect(page.getByTestId('draft-row').nth(1).getByTestId('draft-incomplete')).toBeVisible()

  await page.getByTestId('draft-row').first().getByTestId('draft-confirm').click()
  await page.getByTestId('draft-commit').click()
  await expect(page.getByTestId('draft-msg')).toContainText('已寫入 1 列')
})

test('確認被 409 DRAFT_INCOMPLETE 擋下時，標出是哪一列', async ({ page }) => {
  const fake = new FakeDrafts()
  const key = 'gx'
  fake.add({ cycle: GM, narrative: '好的' }, { group_key: key, order_in_group: 0, parse_snapshot: { complete: true } })
  const bad = fake.add({ cycle: { seq: 'GM' }, narrative: '缺的' }, { group_key: key, order_in_group: 1, parse_snapshot: { complete: false } })
  await install(page, fake)
  await enterWorkspace(page)
  await page.getByTestId('draft-confirm-group').click()
  await expect(page.getByTestId('draft-msg')).toContainText('解析不完整')
  await expect(page.locator(`[data-testid=draft-row][data-flagged=true]`)).toHaveCount(1)
  await expect(page.locator(`[data-testid=draft-row][data-flagged=true]`)).toContainText('缺的')
  expect(bad.status).toBe('pending')
})

test('降級原因不認得或沒給時，顯示通用說明', async ({ page }) => {
  const fake = new FakeDrafts()
  fake.sentence.status = 'degraded'
  fake.sentence.reason = { error_kind: 'contract_mismatch' }
  await install(page, fake)
  await enterWorkspace(page)
  await page.getByTestId('input-mode-sentence').click()
  await page.getByTestId('sentence-text').fill('右手拿起螺絲')
  await page.getByTestId('sentence-submit').click()
  await expect(page.getByTestId('sentence-result')).toContainText('AI 服務暫時無法使用，已改用規則解析')
})


test('匯入草稿顯示 Excel 數量的預填依據', async ({ page }) => {
  const fake = new FakeDrafts()
  fake.add({ cycle: GM, narrative: '鎖螺絲', frequency: 2 }, { source: 'imported',
    parse_snapshot: { complete: true, quantity: { excel: 2, rule: '2', applied: true, reason: null } } })
  fake.add({ cycle: GM, narrative: '拿螺絲' }, { source: 'imported',
    parse_snapshot: { complete: true, quantity: { excel: 2, rule: '2', applied: false, reason: 'other_motion_not_applied' } } })
  await install(page, fake)
  await enterWorkspace(page)
  const q = page.getByTestId('draft-quantity')
  await expect(q.nth(0)).toContainText('Excel 數量 2：已預填（規則 2）')
  await expect(q.nth(1)).toContainText('只套用到加工與放置類動作')
})
