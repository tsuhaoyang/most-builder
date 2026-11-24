/**
 * ADR-038 W8：區域與距離畫面（mock API）。
 *
 * 全部 /api/** 由 page.route 攔截，FakeDistance 在記憶體裡模擬：區域、DSX 物件與同步、物件歸區、距離建議、套用、
 * 整份存檔（只寫回帶了 distance_status 的列）與核准的距離檢查（DISTANCE_STATUS_MISSING）。
 *
 * 涵蓋（delivery plan〈W8〉）：
 * - 第 1、2、5 項：設區域 → 同步 → 歸區 → 算距離 → 勾選套用 → 標「此動作無距離」→ 存檔 → 核准通過
 * - 第 4、5 項：缺狀態時核准被擋，錯誤指出是哪一列
 * - 第 3、6、7、9 項：DSX 連不到、同步時站別不同、同一 DSX 物件綁多個區域、套用 409 列出每列原因
 * - 第 11 項：admin 看到並發布距離設定
 */
import { test, expect, type Page, type Route } from '@playwright/test'

test.setTimeout(60_000)

const WS = 'ws-w8'
const SKU = 'sk-w8'
const ADMIN_ME = { employee_no: 'IEC141289', roles: ['admin'], level: 3 }
const MOCK_CASES = {
  total: 1,
  items: [{
    process_version_id: 'pv-w8', worksheet_id: WS, version_no: 'v1', status: 'draft',
    site_id: 'st-1', site_name: 'Site A', product_id: 'p1', product_name: 'Product X',
    sku_id: SKU, sku_name: 'SKU 008', process_name: '距離測試', total_tmu: 20,
    created_at: '2026-01-01T00:00:00Z', approved_at: null, model_label: null, version_count: 1,
    versions: [{ process_version_id: 'pv-w8', worksheet_id: WS, version_no: 'v1',
      status: 'draft', total_tmu: 20, created_at: '2026-01-01T00:00:00Z', approved_at: null }],
  }],
}
const MOCK_OPTS = {
  code: 'MINIMOST_FACTORY_V2', multiplier: 1,
  a_bands: { reach: [{ max_value: 5, index: 2 }], twist: [{ max_value: null, index: 0 }], foot: [{ max_value: null, index: 0 }] },
  b: [], g: [{ code: 'g_simple', label: '簡單抓握', modifier_key: null, requires_modifier: false }],
  p_bases: [{ code: 'p_put', label: '放置', label_en: 'Put' }], p_addons: [],
  m_verbs: [], x: [{ code: 'x_none', label: '無機器時間', mode: 'none' }],
  i: [{ code: 'i_none', label: '無', label_en: 'None' }],
}
const CAT = { id: 'cat-bin', code: 'bin', name_zh: '料盒', name_en: 'Bin', sort_order: 1, is_active: true }
const VOCAB = 'v-screw'
const NOW = '2026-11-24T10:00:00Z'

function row(id: string, seq: number, narrative: string) {
  return {
    wi_row_id: id, seq_no: seq, hand: 'RH', sub_activity: null, key_parts: null,
    object_vocab_id: VOCAB, from_vocab_id: null, to_vocab_id: null, tool_vocab_id: null,
    frequency: 1, simo_group_id: null, wi_group: '上料', distance_status: null as string | null,
    source_module_id: null, source_module_version: null,
    cycle: { seq_kind: 'GM', total_tmu: 10, total_seconds: 0.36, narrative, narrative_en: null,
      slot_inputs: { seq: 'GM', rule_set_code: 'MINIMOST_FACTORY_V2', a0: { reach_cm: 5 }, g2: { g_code: 'g_simple' } },
      rule_set_id: 'rs-1', breakdown: [] },
    level: null, lb_tags: null,
  }
}

function suggestion(wiRowId: string, slot: string, status: string, extra: Record<string, unknown> = {}) {
  return {
    wi_row_id: wiRowId, slot, status, field: status === 'suggested' ? 'reach_cm' : null,
    distance_cm: status === 'suggested' ? 42 : null, reason: null,
    endpoints: { from: { source: 'person_offset' }, to: { source: 'zone_center' } },
    snapshot_id: 'snap-2', threshold_cm: 70, person_offset_cm: [0, 0, 140], modeling_policy_version_id: 'mp-1',
    computed_by: 'IEC141289', computed_at: NOW, ...extra,
  }
}

class FakeDistance {
  revision = 3
  status = 'draft'
  rows = [row('r1', 1, '拿起螺絲'), row('r2', 2, '放到治具')]
  zones: Array<Record<string, unknown>> = []
  snapshots: Array<Record<string, unknown>> = []
  assignments: Record<string, string | null> = {}
  suggestions: Array<Record<string, unknown>> = []
  dsx: { available: boolean; reason?: string } = { available: true }
  nextStation = 'ST-01'
  saves: Array<Record<string, unknown>> = []
  applies: Array<Record<string, unknown>> = []
  settingsPublished: Array<Record<string, unknown>> = []
  applyFail: { code: string; detail: Record<string, unknown> } | null = null
  publishes = 0
  checkRequired = true

  worksheet() {
    return { worksheet_id: WS, status: this.status, total_tmu: 20, rows: this.rows, default_rule_set: null,
      revision_no: this.revision, content_hash: null, distance_check_required: this.checkRequired }
  }
  zoneList() {
    return { sku_id: SKU, zones: this.zones, last_snapshot: this.snapshots.at(-1) ?? null }
  }
}

function install(page: Page, fake: FakeDistance) {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  const err = (route: Route, status: number, code: string, detail: Record<string, unknown> = {}) =>
    json(route, { error: { code, message: code, detail: { code, ...detail } } }, status)

  return page.route('/api/**', async route => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    const method = req.method()
    const body = () => JSON.parse(req.postData() ?? '{}')

    if (path === `/api/v2/worksheets/${WS}/objects`)
      return json(route, { worksheet_id: WS, sku_id: SKU, objects: [
        { vocab_item_id: VOCAB, kind: 'object', name_zh: '螺絲', name_en: 'Screw', roles: ['object'], row_count: 2,
          zone_id: fake.assignments[VOCAB] ?? null },
      ] })
    if (path === '/api/v2/zone-categories') return json(route, [CAT])
    if (path === `/api/v2/skus/${SKU}/zones` && method === 'GET') return json(route, fake.zoneList())
    if (path === `/api/v2/skus/${SKU}/zones` && method === 'POST') {
      const b = body()
      const z = { id: `z${fake.zones.length + 1}`, sku_id: SKU, category_id: b.category_id, name: b.name,
        dsx_object_id: b.dsx_object_id ?? null, center: null, center_snapshot_id: null, updated_at: NOW }
      fake.zones.push(z)
      return json(route, z, 201)
    }
    if (path === '/api/v2/dsx/objects')
      return json(route, fake.dsx.available
        ? { available: true, objects: [{ id: 'bin-a', label_zh: '螺絲盒', vocab_code: null, visible: true }] }
        : { available: false, reason: fake.dsx.reason, objects: [] })
    if (path === `/api/v2/skus/${SKU}/zones/sync` && method === 'POST') {
      const prev = fake.snapshots.at(-1) ?? null
      const snap = { id: `snap-${fake.snapshots.length + 1}`, sku_id: SKU, dsx_station_id: fake.nextStation,
        placement_revision: fake.snapshots.length + 7, synced_by: 'IEC141289', synced_at: NOW, placement_count: 1 }
      fake.snapshots.push(snap)
      for (const z of fake.zones) if (z.dsx_object_id) { z.center = { x: 30, y: 20, z: 90 }; z.center_snapshot_id = snap.id }
      return json(route, { snapshot: snap, previous_snapshot: prev, zones: fake.zones, missing_zone_ids: [],
        unbound_zone_ids: fake.zones.filter(z => !z.dsx_object_id).map(z => z.id) })
    }
    if (path === `/api/v2/skus/${SKU}/object-zones` && method === 'PUT') {
      for (const i of body().items as Array<{ vocab_item_id: string; zone_id: string | null }>) fake.assignments[i.vocab_item_id] = i.zone_id
      return json(route, { sku_id: SKU, items: [] })
    }
    if (path === `/api/v2/worksheets/${WS}/distance-suggestions` && method === 'GET')
      return json(route, { worksheet_id: WS, items: fake.suggestions })
    if (path === `/api/v2/worksheets/${WS}/distance-suggestions/compute` && method === 'POST') {
      fake.suggestions = [
        suggestion('r1', 'a0', 'suggested'), suggestion('r1', 'a6', 'suggested'),
        suggestion('r2', 'a0', 'suggested'), suggestion('r2', 'a6', 'needs_ie', { reason: 'a6_over_threshold', distance_cm: 95 }),
      ]
      return json(route, { worksheet_id: WS, items: fake.suggestions })
    }
    if (path === `/api/v2/worksheets/${WS}/distance-suggestions/apply` && method === 'POST') {
      const b = body()
      fake.applies.push(b)
      if (fake.applyFail) return err(route, 409, fake.applyFail.code, fake.applyFail.detail)
      if (b.base_revision !== fake.revision) return err(route, 409, 'WORKSHEET_REVISION_CONFLICT')
      for (const r of fake.rows) if ((b.wi_row_ids as string[]).includes(r.wi_row_id)) r.distance_status = 'confirmed'
      fake.revision += 1
      return json(route, { revision_no: fake.revision, rows: fake.rows })
    }
    if (path === '/api/v2/modeling-policy/distance-settings' && method === 'GET')
      return json(route, { modeling_policy_version_id: 'mp-1', version_no: 1, reach_foot_threshold_cm: 70,
        person_offset_cm: [0, 0, 140], source: 'default' })
    if (path === '/api/v2/modeling-policy/distance-settings' && method === 'POST') {
      fake.settingsPublished.push(body())
      return json(route, { modeling_policy_version_id: 'mp-2', version_no: 2, ...body(), source: 'policy' }, 201)
    }
    if (path === `/api/v2/worksheets/${WS}` && method === 'PUT') {
      // 後端行為：帶了 distance_status 的列以帶的為準；沒帶的保留
      const b = body()
      fake.saves.push(b)
      for (const r of b.rows as Array<{ id?: string; distance_status?: string | null }>) {
        const hit = fake.rows.find(x => x.wi_row_id === r.id)
        if (hit && 'distance_status' in r) hit.distance_status = r.distance_status ?? null
      }
      fake.revision += 1
      return json(route, fake.worksheet())
    }
    if (path === `/api/v2/worksheets/${WS}/publish` && method === 'POST') {
      fake.publishes += 1
      const missing = fake.rows.filter(r => !r.distance_status)
      if (missing.length)
        return err(route, 409, 'DISTANCE_STATUS_MISSING', { missing_count: missing.length,
          rows: missing.map(r => ({ wi_row_id: r.wi_row_id, seq_no: r.seq_no })) })
      fake.status = 'approved'
      return json(route, { worksheet_id: WS, status: 'approved' })
    }
    if (path === `/api/v2/worksheets/${WS}`) return json(route, fake.worksheet())
    if (path === `/api/v2/worksheets/${WS}/drafts`) return json(route, { worksheet_id: WS, items: [] })
    if (path === '/api/v2/wi-ai/status') return json(route, { enabled: false, available: false })
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
  await page.getByText('距離測試').click()
  await page.getByRole('button', { name: '編輯工時表' }).click()
  await expect(page.getByTestId('distance-panel')).toBeVisible()
}

async function addZoneAndSync(page: Page, name = '螺絲盒區') {
  await page.getByTestId('zones-edit-toggle').click()
  await page.getByTestId('zone-add-category').selectOption(CAT.id)
  await page.getByTestId('zone-add-name').fill(name)
  await page.getByTestId('zone-add-object').selectOption('bin-a')
  await page.getByTestId('zone-add-submit').click()
  await expect(page.getByTestId('zone-row').filter({ hasText: name })).toBeVisible()
  await page.getByTestId('zones-sync').click()
  await expect(page.getByTestId('zones-msg')).toContainText('已同步')
}

test('設區域 → 同步 → 歸區 → 算距離 → 套用 → 標無距離 → 存檔 → 核准通過', async ({ page }) => {
  const fake = new FakeDistance()
  await install(page, fake)
  await enterWorkspace(page)

  await addZoneAndSync(page)
  await expect(page.getByTestId('zone-row').first()).toContainText('(30, 20, 90) cm')
  await expect(page.getByTestId('zones-snapshot')).toContainText('IEC141289')

  await page.getByTestId('object-zone').selectOption('z1')
  await expect.poll(() => fake.assignments[VOCAB]).toBe('z1')

  await page.getByTestId('distance-compute').click()
  const rows = page.getByTestId('distance-row')
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0).getByTestId('suggestion-a0')).toContainText('42 cm')
  await expect(rows.nth(0).getByTestId('suggestion-a0')).toContainText('伸手')
  await expect(rows.nth(1).getByTestId('suggestion-a6')).toHaveAttribute('data-status', 'needs_ie')
  await expect(rows.nth(1).getByTestId('suggestion-a6')).toContainText('需 IE 裁決')
  // 有格位需 IE 裁決的列不能勾
  await expect(rows.nth(1).getByTestId('distance-pick')).toHaveCount(0)

  await rows.nth(0).getByTestId('distance-pick').check()
  await page.getByTestId('distance-apply').click()
  await expect(page.getByTestId('distance-msg')).toContainText('已套用 1 列')
  expect(fake.applies[0]).toEqual({ base_revision: 3, computed_at: NOW, wi_row_ids: ['r1'] })
  await expect(rows.nth(0).getByTestId('distance-status')).toContainText('已確認')

  await rows.nth(1).getByTestId('distance-mark-na').click()
  await expect(rows.nth(1).getByTestId('distance-status')).toContainText('此動作無距離（未儲存）')
  await page.getByRole('button', { name: '儲存', exact: true }).click()
  await expect(rows.nth(1).getByTestId('distance-status')).not.toContainText('未儲存')
  // 只帶改過的列的距離狀態（r1 沒帶 → 後端保留 confirmed）
  const saved = fake.saves[0].rows as Array<Record<string, unknown>>
  expect(saved.find(r => r.id === 'r2')?.distance_status).toBe('not_applicable')
  expect('distance_status' in (saved.find(r => r.id === 'r1') ?? {})).toBe(false)
  expect(fake.rows.map(r => r.distance_status)).toEqual(['confirmed', 'not_applicable'])

  await page.getByRole('button', { name: /分析案件/ }).first().click()
  await page.getByText('距離測試').first().click()
  await page.getByRole('button', { name: '核准', exact: true }).click()
  await expect.poll(() => fake.status).toBe('approved')
  await expect(page.getByTestId('approve-error')).toHaveCount(0)
})

test('缺距離狀態時核准被擋，並指出是哪一列', async ({ page }) => {
  const fake = new FakeDistance()
  fake.rows[0].distance_status = 'manual'
  await install(page, fake)
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: /分析案件/ }).click()
  await page.getByText('距離測試').click()
  await page.getByRole('button', { name: '核准', exact: true }).click()
  await expect(page.getByTestId('approve-error')).toContainText('共 1 列還沒標距離狀態：#2')
  expect(fake.status).toBe('draft')
})

test('DSX 連不到、站別不同、同一物件綁多個區域、套用 409 列出原因', async ({ page }) => {
  const fake = new FakeDistance()
  await install(page, fake)
  await enterWorkspace(page)

  await addZoneAndSync(page, '區A')
  await page.getByTestId('zone-add-category').selectOption(CAT.id)
  await page.getByTestId('zone-add-name').fill('區B')
  await page.getByTestId('zone-add-object').selectOption('bin-a')
  await page.getByTestId('zone-add-submit').click()
  // 第二個區域綁同一個 DSX 物件 → 提示
  await expect(page.getByTestId('zones-dup')).toContainText('bin-a（區A、區B）')

  fake.nextStation = 'ST-99'
  await page.getByTestId('zones-sync').click()
  await expect(page.getByTestId('zones-msg')).toContainText('DSX 站別與上次不同（ST-01 → ST-99）')
  await expect(page.getByTestId('zones-msg')).toContainText('DSX 擺放已更新')

  await page.getByTestId('distance-compute').click()
  fake.applyFail = { code: 'DISTANCE_NOT_APPLICABLE', detail: { row_count: 1, rows: [{ wi_row_id: 'r1', reason: 'zone_not_synced' }] } }
  await page.getByTestId('distance-row').nth(0).getByTestId('distance-pick').check()
  await page.getByTestId('distance-apply').click()
  await expect(page.getByTestId('distance-row').nth(0)).toHaveAttribute('data-flag', 'zone_not_synced')
  await expect(page.getByTestId('distance-row').nth(0)).toContainText('區域還沒有座標')

  fake.applyFail = { code: 'DISTANCE_SUGGESTION_CHANGED', detail: { row_count: 1, wi_row_ids: ['r1'] } }
  await page.getByTestId('distance-apply').click()
  await expect(page.getByTestId('distance-row').nth(0)).toHaveAttribute('data-flag', 'suggestion_changed')
  await expect(page.getByTestId('distance-row').nth(0)).toContainText('請按「算距離」後再確認')

  // DSX 連不到：清快取後重新打開區域編輯
  fake.dsx = { available: false, reason: 'dsx_unreachable' }
  await page.reload()
  await page.waitForLoadState('networkidle')
  await enterWorkspace(page)
  await page.getByTestId('zones-edit-toggle').click()
  await expect(page.getByTestId('dsx-unavailable')).toContainText('DSX 無法連線')
})

test('admin 看到距離設定並發布新版（說明只影響之後新建的工時表）', async ({ page }) => {
  const fake = new FakeDistance()
  await install(page, fake)
  await enterWorkspace(page)
  const s = page.getByTestId('distance-settings')
  await expect(s).toContainText('門檻 70 cm')
  await expect(s).toContainText('只影響之後新建的工時表')
  page.once('dialog', d => void d.accept())
  await page.getByTestId('settings-threshold').fill('80')
  await page.getByTestId('settings-publish').click()
  await expect(page.getByTestId('settings-msg')).toContainText('已發布')
  expect(fake.settingsPublished).toEqual([{ reach_foot_threshold_cm: 80, person_offset_cm: [0, 0, 140] }])
  await expect(s).toContainText('V2')
})

test('不需距離檢查的舊工時表：區域與距離預設收起，可展開', async ({ page }) => {
  const fake = new FakeDistance()
  fake.checkRequired = false
  await install(page, fake)
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: /分析案件/ }).click()
  await page.getByText('距離測試').click()
  await page.getByRole('button', { name: '編輯工時表' }).click()
  await expect(page.getByTestId('distance-unmarked')).toHaveText('2 列未標距離狀態')
  await expect(page.getByTestId('distance-row')).toHaveCount(0)
  await page.getByTestId('distance-toggle').click()
  await expect(page.getByTestId('distance-row')).toHaveCount(2)
})
