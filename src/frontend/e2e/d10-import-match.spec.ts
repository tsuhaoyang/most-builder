/**
 * ADR-025 D10：匯入精靈逐行範本建議（match 預覽 → 採用 → submit row_adoptions）。
 *
 * 非空洞性（沿用 D8b 作法）：所有 /api/** 由 page.route 攔截；斷言 method＋URL＋body；
 * catch-all 對「非 GET」一律回 500 —— 前端若打了未預期的寫入端點會當場炸掉，不會靜默通過。
 *
 * 契約（ADR-025）：submit 的 row_adoptions 每項**只含 row_index＋template_id**（TMU 一律後端算）。
 *
 * 需 Vite dev server（或 E2E_BASE_URL）；不依賴 preview_server 的資料狀態。
 */
import { test, expect, type Page, type Route } from '@playwright/test'

const ADMIN_ME = { employee_no: 'IEC141289', roles: ['admin'], level: 3 }

const IMPORT_ID = 'aaaaaaaa-0000-0000-0000-000000000000'
const T_LOCK = '11111111-1111-1111-1111-111111111111'   // 鎖附螺絲（最佳命中）
const T_LOCK_PNEU = '22222222-2222-2222-2222-222222222222'  // 鎖附螺絲(氣動)（候選）
const T_CARRY = '33333333-3333-3333-3333-333333333333'   // 搬運（命中但算不出）

// 分析案件（用來設定 activeWs：編輯工時表 → setActiveCase）
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

const UPLOAD_OUT = {
  import_id: IMPORT_ID, source_name: 'test.xlsx',
  target_fields: ['description'], required_fields: ['description'],
  sheets: [{ name: '工作表1', n_rows: 4, n_cols: 1,
    grid: [['描述'], ['鎖附螺絲 M4'], ['自行確認拉力'], ['搬運箱子']] }],
  suggested_sheet: '工作表1', suggested_header_row: 0, profiles: [],
}

const opt = (o: Partial<Record<string, unknown>> & { template_id: string }) => ({
  template_name_zh: '', seq_kind: 'CM', score: 0, matched_keywords: [],
  computed_tmu: null, computed_seconds: null, error: null, ...o,
})

/** 大批匯入 preview 產生器：isHit(i) 決定該列是否命中可算範本（T_LOCK, 29 TMU）。 */
function bigPreview(n: number, isHit: (i: number) => boolean, withCand = false) {
  const rows = Array.from({ length: n }, (_, i) => isHit(i)
    ? {
      description: `命中列 ${i} 鎖附螺絲`, match: {
        ...opt({ template_id: T_LOCK, template_name_zh: '鎖附螺絲', seq_kind: 'CM',
          score: 10, matched_keywords: ['鎖', '螺絲'], computed_tmu: 29, computed_seconds: 1.044 }),
        candidates: withCand
          ? [opt({ template_id: T_LOCK_PNEU, template_name_zh: '鎖附螺絲(氣動)', seq_kind: 'CM',
              score: 6, matched_keywords: ['螺絲'], computed_tmu: 35, computed_seconds: 1.26 })]
          : [],
      },
    }
    : { description: `一般列 ${i}`, match: null })
  return { import_id: IMPORT_ID, fields: ['description'], n, warnings: [], rows }
}

// 三列預覽：命中可算 / 完全無命中 / 命中但算不出（active 缺）
const PREVIEW_OUT = {
  import_id: IMPORT_ID, fields: ['description'], n: 3, warnings: [],
  rows: [
    { description: '鎖附螺絲 M4', match: {
      ...opt({ template_id: T_LOCK, template_name_zh: '鎖附螺絲', seq_kind: 'CM',
        score: 10, matched_keywords: ['鎖', '螺絲'], computed_tmu: 29, computed_seconds: 1.044 }),
      candidates: [opt({ template_id: T_LOCK_PNEU, template_name_zh: '鎖附螺絲(氣動)', seq_kind: 'CM',
        score: 6, matched_keywords: ['螺絲'], computed_tmu: 35, computed_seconds: 1.26 })],
    } },
    { description: '自行確認拉力', match: null },
    { description: '搬運箱子', match: {
      ...opt({ template_id: T_CARRY, template_name_zh: '搬運', seq_kind: 'GM',
        score: 4, matched_keywords: ['搬'], computed_tmu: null, computed_seconds: null,
        error: '目前無啟用中的字典版本，無法計算' }),
      candidates: [],
    } },
  ],
}

interface SubmitBody { worksheet_id: string; row_adoptions?: { row_index: number; template_id: string }[] }

/** 攔截全部 /api/**；回傳被攔到的 submit body（供斷言）。非 GET 未匹配 → 500（非空洞）。 */
function installRoutes(page: Page, opts: { previewRows?: unknown } = {}) {
  const captured: { submit: SubmitBody | null } = { submit: null }
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  page.route('/api/**', route => {
    const req = route.request()
    const url = req.url()
    const method = req.method()

    // ── 匯入端點（寫入路徑）────────────────────────────────────────────────
    if (url.includes('/api/v2/imports/upload')) {
      expect(method).toBe('POST')
      return json(route, UPLOAD_OUT)
    }
    if (/\/api\/v2\/imports\/[^/]+\/map$/.test(url)) {
      expect(method).toBe('POST')
      const body = JSON.parse(req.postData() ?? '{}')
      expect(body.column_map).toEqual({ description: 0 })   // 斷言 body 形狀
      return json(route, opts.previewRows ?? PREVIEW_OUT)
    }
    if (/\/api\/v2\/imports\/[^/]+\/submit$/.test(url)) {
      expect(method).toBe('POST')
      captured.submit = JSON.parse(req.postData() ?? '{}') as SubmitBody
      return json(route, { worksheet_id: 'ws-001', n_rows: 3, n_with_analysis: 1, n_need_review: 1, warnings: [] })
    }

    // ── 讀取路徑（導覽到有 activeWs 的工時表情境所需）────────────────────────
    if (url.includes('/api/v2/me')) return json(route, ADMIN_ME)
    if (url.includes('/api/v2/rule-sets/active'))
      return json(route, { id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' })
    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) return json(route, MOCK_OPTS)
    if (url.match(/\/api\/v2\/rule-sets(\?|$)/))
      return json(route, [{ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2',
        status: 'published', multiplier: 1, is_active: true, provenance: 'certified_import',
        created_at: '2026-07-07T10:24:25Z', notes: null }])
    if (url.match(/\/api\/v2\/cases(\?|$)/)) return json(route, MOCK_CASES)
    if (url.includes('/api/v2/audit-log')) return json(route, { total: 0, items: [] })
    if (url.includes('/api/v2/worksheets/'))
      return json(route, { worksheet_id: 'ws-001', status: 'draft', total_tmu: 0, rows: [] })

    // catch-all：GET → 空陣列；非 GET → 500（未預期的寫入端點必須炸掉）
    if (method === 'GET') return json(route, [])
    return json(route, { detail: `unexpected ${method} ${url}` }, 500)
  })

  return captured
}

/** 導覽到分析案件 → 編輯工時表（設定 activeWs），讓匯入精靈可提交。 */
async function enterWorksheetContext(page: Page) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.getByRole('button', { name: /分析案件/ }).click()
  await page.waitForLoadState('networkidle')
  await page.getByText('組裝站作業').click()
  await page.getByRole('button', { name: '編輯工時表' }).click()
  await page.waitForLoadState('networkidle')
}

/** 開啟匯入精靈並走到 preview 步驟（上傳 → 對應 description → 預覽）。 */
async function openImportToPreview(page: Page) {
  await page.getByRole('button', { name: /匯入 Excel/ }).click()
  await expect(page.getByRole('heading', { name: /匯入 Excel/ })).toBeVisible()
  await page.setInputFiles('input[type=file]',
    { name: 'test.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('x') })
  // map 步驟：把「描述」對應到第 0 欄
  const descSelect = page.locator('label', { hasText: '描述（必）' }).locator('select')
  await expect(descSelect).toBeVisible()
  await descSelect.selectOption('0')
  await page.getByRole('button', { name: '預覽' }).click()
  await expect(page.getByTestId('match-panel')).toBeVisible()
}

// ─────────────────────────────────────────────────────────────────────────────

test('D10-a/c/d/e: 命中預選＋TMU、無命中須手動、命中但算不出不可採、submit 只送 row_index+template_id', async ({ page }) => {
  const captured = installRoutes(page)
  await enterWorksheetContext(page)
  await openImportToPreview(page)

  // (a) 有 match 的行預設勾選且顯示後端算的 computed_tmu（29），非前端自算
  const cb0 = page.getByTestId('adopt-checkbox-0')
  await expect(cb0).toBeChecked()
  await expect(page.getByTestId('match-tmu-0')).toHaveText('29')
  await expect(page.getByTestId('match-row-0')).toContainText('鎖附螺絲')

  // (c) match:null 的行標「須手動建模」，且無勾選框（不可採用）
  await expect(page.getByTestId('match-manual-1')).toContainText('須手動建模')
  await expect(page.getByTestId('adopt-checkbox-1')).toHaveCount(0)

  // (d) computed_tmu:null＋error 的行：勾選框停用、顯示錯誤、**不顯示任何 TMU 數字**
  //     （與 (a) 對照：同樣有 match，一個可採一個不可採）
  const cb2 = page.getByTestId('adopt-checkbox-2')
  await expect(cb2).toBeDisabled()
  await expect(cb2).not.toBeChecked()
  await expect(page.getByTestId('match-error-2')).toHaveText('無法計算')
  await expect(page.getByTestId('match-error-msg-2')).toContainText('目前無啟用中的字典版本')
  await expect(page.getByTestId('match-tmu-2')).not.toContainText(/\d/)   // 絕不顯示數字

  await page.screenshot({ path: 'd10-import-match-preview.png', fullPage: true })

  // (e) 送出：row_adoptions 只含被採用（可算）的第 0 列，且每項**只有** row_index＋template_id
  await page.getByRole('button', { name: /提交到工序表/ }).click()
  await expect(page.getByText(/匯入完成/)).toBeVisible()

  expect(captured.submit).not.toBeNull()
  const ra = captured.submit!.row_adoptions ?? []
  expect(ra).toHaveLength(1)
  expect(ra[0]).toEqual({ row_index: 0, template_id: T_LOCK })   // 恰好兩鍵、無 tmu
  expect(Object.keys(ra[0]).sort()).toEqual(['row_index', 'template_id'])
  // 無命中(1)／算不出(2)的列不得出現在 row_adoptions
  expect(ra.map(x => x.row_index)).not.toContain(1)
  expect(ra.map(x => x.row_index)).not.toContain(2)
})

test('D10-b: 取消採用後，該行不出現在 row_adoptions（送出空陣列）', async ({ page }) => {
  const captured = installRoutes(page)
  await enterWorksheetContext(page)
  await openImportToPreview(page)

  const cb0 = page.getByTestId('adopt-checkbox-0')
  await expect(cb0).toBeChecked()
  await cb0.uncheck()
  await expect(cb0).not.toBeChecked()
  await expect(page.getByTestId('adopt-count')).toContainText('0 列採用')

  await page.getByRole('button', { name: /提交到工序表/ }).click()
  await expect(page.getByText(/匯入完成/)).toBeVisible()

  expect(captured.submit).not.toBeNull()
  expect(captured.submit!.row_adoptions ?? []).toEqual([])   // 取消採用 → 不落任何範本
})

test('D10-candidate: 換候選範本 → 顯示的 TMU 隨後端該範本值改變（前端不自算）', async ({ page }) => {
  const captured = installRoutes(page)
  await enterWorksheetContext(page)
  await openImportToPreview(page)

  // 預設選最佳命中「鎖附螺絲」→ 29 TMU
  await expect(page.getByTestId('match-tmu-0')).toHaveText('29')
  // 換成候選「鎖附螺絲(氣動)」→ TMU 換成後端給該範本的 35（不是前端算的）
  await page.getByTestId('match-select-0').selectOption(T_LOCK_PNEU)
  await expect(page.getByTestId('match-tmu-0')).toHaveText('35')
  await expect(page.getByTestId('adopt-checkbox-0')).toBeChecked()   // 換選後仍採用

  await page.getByRole('button', { name: /提交到工序表/ }).click()
  await expect(page.getByText(/匯入完成/)).toBeVisible()
  // 送出的是換選後的候選 template_id（仍只有 row_index＋template_id）
  expect(captured.submit!.row_adoptions).toEqual([{ row_index: 0, template_id: T_LOCK_PNEU }])
})

// ── 中高缺陷回歸：渲染上限 vs 採用/送出範圍不一致 → >100 列命中被看不到地落盤 ──────
// 若 MatchPanel 改回 rows.slice(0,100)，第 120 列定位不到 → 本組測試變紅（非空洞）。

test('D10-large-adopt: 150 列匯入，第 120 列命中 → 面板可見/可捲到，預設採用且進 row_adoptions', async ({ page }) => {
  const captured = installRoutes(page, { previewRows: bigPreview(150, i => i % 10 === 0) })
  await enterWorksheetContext(page)
  await openImportToPreview(page)

  // (a) 第 120 列在採用面板中「渲染得出、捲得到、看得見」——不是被藏在 slice 之外
  const cb120 = page.getByTestId('adopt-checkbox-120')
  await cb120.scrollIntoViewIfNeeded()
  await expect(cb120).toBeVisible()
  await expect(page.getByTestId('match-row-120')).toContainText('鎖附螺絲')
  await expect(cb120).toBeChecked()          // 命中可算 → 預選採用
  await expect(page.getByTestId('match-tmu-120')).toHaveText('29')

  await page.screenshot({ path: 'd10fix-large-import.png' })

  // (d) 不取消 → 第 120 列在 row_adoptions 裡（且仍只含 row_index＋template_id）
  await page.getByRole('button', { name: /提交到工序表/ }).click()
  await expect(page.getByText(/匯入完成/)).toBeVisible()
  const ra = captured.submit!.row_adoptions ?? []
  expect(ra.find(x => x.row_index === 120)).toEqual({ row_index: 120, template_id: T_LOCK })
  expect(ra.length).toBe(15)   // 150 列每 10 列一命中 → 15 列（全採用，全渲染才數得對）
})

test('D10-large-uncheck: 捲到第 120 列取消採用 → 提交時 row_adoptions 不含它（其餘命中仍在）', async ({ page }) => {
  const captured = installRoutes(page, { previewRows: bigPreview(150, i => i % 10 === 0) })
  await enterWorksheetContext(page)
  await openImportToPreview(page)

  // (b)(c) 捲到第 120 列並取消 —— 只有「看得見、點得到」才可能被 IE 否決
  const cb120 = page.getByTestId('adopt-checkbox-120')
  await cb120.scrollIntoViewIfNeeded()
  await cb120.uncheck()
  await expect(cb120).not.toBeChecked()

  await page.getByRole('button', { name: /提交到工序表/ }).click()
  await expect(page.getByText(/匯入完成/)).toBeVisible()
  const ra = captured.submit!.row_adoptions ?? []
  expect(ra.find(x => x.row_index === 120)).toBeUndefined()                 // 已否決 → 不落盤
  expect(ra.find(x => x.row_index === 110)).toEqual({ row_index: 110, template_id: T_LOCK }) // 未動的仍在
  expect(ra.length).toBe(14)
})

test('D10-perf-1000: 1000 列全渲染，末列/中列可覆核（實測 render 與互動耗時）', async ({ page }) => {
  installRoutes(page, { previewRows: bigPreview(1000, () => true, /* withCand */ true) })
  await enterWorksheetContext(page)

  const t0 = Date.now()
  await openImportToPreview(page)                    // 含 upload+map（mock）+全渲染
  const renderMs = Date.now() - t0

  // 全部 1000 列都在 DOM（截斷會少一截）
  await expect(page.getByTestId('match-row-999')).toHaveCount(1)

  // 捲到中段第 500 列並操作（換候選 → TMU 隨後端值變、可取消）
  const t1 = Date.now()
  const sel500 = page.getByTestId('match-select-500')
  await sel500.scrollIntoViewIfNeeded()
  await sel500.selectOption(T_LOCK_PNEU)
  await expect(page.getByTestId('match-tmu-500')).toHaveText('35')
  const cb999 = page.getByTestId('adopt-checkbox-999')
  await cb999.scrollIntoViewIfNeeded()
  await cb999.uncheck()
  await expect(cb999).not.toBeChecked()
  const interactMs = Date.now() - t1

  // eslint-disable-next-line no-console
  console.log(`[D10-perf] 1000 列(含候選 select)：render=${renderMs}ms，捲動+換候選+取消末列=${interactMs}ms`)
})

test('D10-no-active: 全表命中但無 active 字典 → 每列不可採用、顯示錯誤、無 TMU、送出空 row_adoptions', async ({ page }) => {
  // 模擬 active 缺失：兩列都命中但 computed_tmu=null＋error
  const NO_ACTIVE = {
    import_id: IMPORT_ID, fields: ['description'], n: 2, warnings: [],
    rows: [
      { description: '鎖附螺絲 M4', match: {
        ...opt({ template_id: T_LOCK, template_name_zh: '鎖附螺絲', seq_kind: 'CM',
          score: 10, matched_keywords: ['鎖', '螺絲'], error: '目前無啟用中的字典版本，無法計算' }),
        candidates: [] } },
      { description: '搬運箱子', match: {
        ...opt({ template_id: T_CARRY, template_name_zh: '搬運', seq_kind: 'GM',
          score: 4, matched_keywords: ['搬'], error: '目前無啟用中的字典版本，無法計算' }),
        candidates: [] } },
    ],
  }
  const captured = installRoutes(page, { previewRows: NO_ACTIVE })
  await enterWorksheetContext(page)
  await openImportToPreview(page)

  // 兩列都：停用、無 TMU 數字、顯示錯誤（絕不塞 0 或空白）
  for (const i of [0, 1]) {
    await expect(page.getByTestId(`adopt-checkbox-${i}`)).toBeDisabled()
    await expect(page.getByTestId(`match-tmu-${i}`)).not.toContainText(/\d/)
    await expect(page.getByTestId(`match-error-msg-${i}`)).toContainText('目前無啟用中的字典版本')
  }
  await expect(page.getByTestId('adopt-count')).toContainText('0 列採用')

  await page.screenshot({ path: 'd10-import-no-active.png', fullPage: true })

  // 全部採用批次也不能讓算不出的列變可採
  await page.getByTestId('adopt-all').click()
  await expect(page.getByTestId('adopt-count')).toContainText('0 列採用')

  await page.getByRole('button', { name: /提交到工序表/ }).click()
  await expect(page.getByText(/匯入完成/)).toBeVisible()
  expect(captured.submit!.row_adoptions ?? []).toEqual([])
})
