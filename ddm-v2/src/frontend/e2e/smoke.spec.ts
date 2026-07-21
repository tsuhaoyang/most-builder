import { test, expect } from '@playwright/test'

// 對單一伺服器預覽（preview_server :8099，含真實 DB）跑端對端冒煙。
test('app loads, identity + dashboard cards (ADR-021 default tab)', async ({ page }) => {
  await page.goto('/')
  // App title rendered as <h1> inside the AppLayout header
  await expect(page.getByRole('heading', { name: 'MOST Workbench' })).toBeVisible()
  await expect(page.getByText(/IEC141289/)).toBeVisible()               // 身分（/api/v2/me）
  // Sidebar nav button for MOST 工作台 (workbench-v3, ADR-021)
  await expect(page.getByRole('button', { name: /MOST 工作台/ })).toBeVisible()
  // 預設 tab = 儀表板：三張卡（資料來自真實 DB 種子）
  await expect(page.getByText('MOST 字典總覽')).toBeVisible()
  await expect(page.getByText('案件狀態統計')).toBeVisible()
  await expect(page.getByText('近期案件')).toBeVisible()
})

test('sidebar navigation renders each migrated feature', async ({ page }) => {
  await page.goto('/')

  // MOST 字典 tab（admin-gated；seed user IEC141289 是 admin）
  // ADR-023 D4：兩層結構，先落在 L1 版本清單
  await page.getByRole('button', { name: /MOST 字典/ }).click()
  await expect(page.getByRole('heading', { name: '字典版本管理' })).toBeVisible()
  await expect(page.getByTestId('dict-version-list')).toBeVisible()
  // 真後端種子：V2 為啟用中版本
  await expect(page.getByTestId('dict-active-card')).toBeVisible()
  // L2：唯一以真 API 進到內容層的路徑 —— 進版本 → 切 G 分頁 → 斷言有選項列
  await page.getByTestId('dict-version-MINIMOST_FACTORY_V2').getByRole('button', { name: '編輯' }).click()
  await expect(page.getByTestId('dict-option-editor')).toBeVisible()
  await page.getByRole('tab', { name: 'G 取得控制' }).click()
  await expect(page.getByTestId('dict-option-g_tap')).toBeVisible()
  await expect(page.locator('[data-testid^="dict-option-g_"]').first()).toBeVisible()
  // A 分頁（帶型）也以真 API 驗一次
  await page.getByRole('tab', { name: 'A 距離' }).click()
  await expect(page.getByTestId('dict-band-editor')).toBeVisible()
  await page.getByRole('button', { name: '← 返回版本列表' }).click()

  // NOTE: SOP 版本 tab has been retired (L-04). Removed from test.
  // NOTE: 主數據 tab has been retired (L-03). Not present in sidebar.

  // 使用者管理 tab
  await page.getByRole('button', { name: /使用者/ }).click()
  await expect(page.getByText(/使用者與角色/)).toBeVisible()
  await expect(page.getByText('IEC141289', { exact: false }).first()).toBeVisible()

  // NOTE: 匯出 tab 已收進分析案件詳情（ADR-021）；目錄 tab 已退場。

  // 字典管理 tab (admin-gated; seed user IEC141289 is admin) — smoke check (H-01)
  await page.getByRole('button', { name: /字典管理/ }).click()
  await expect(page.getByRole('heading', { name: '字典管理' })).toBeVisible()

  // 分析案件 tab — smoke check (G-01)
  await page.getByRole('button', { name: /分析案件/ }).click()
  // Case list renders filter tabs（exact:true 避免匹配到案件列 button 內含「草稿」badge）
  await expect(page.getByRole('button', { name: '全部', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '草稿', exact: true })).toBeVisible()
})

test('import wizard opens from header button', async ({ page }) => {
  await page.goto('/')
  // Import button is now in the header (no emoji, plain text)
  await page.getByRole('button', { name: /匯入 Excel/ }).click()
  await expect(page.getByRole('heading', { name: /匯入 Excel/ })).toBeVisible()
  await expect(page.getByText(/選擇 .xlsx 檔/)).toBeVisible()
})

// ── MOST 工作台單頁（ADR-022 批次 B）──────────────────────────────────────────
// 三 tab shell 已移除：工作台＝單頁（建立器 → 動作清單 → WI 大綱 → WiItemInspector）。
// 用 page.route 攔截所有 /api/**（不依賴 preview_server 的資料狀態）。
test('MOST 工作台單頁：無 tab、WI 大綱展開、WiItemInspector 開合（mocked API）', async ({ page }) => {
  const ACTION_ID = 'aaaaaaaa-1111-2222-3333-444444444444'
  const WI_ID = 'bbbbbbbb-1111-2222-3333-444444444444'

  const CYCLE = {
    seq: 'GM',
    a0: { reach_cm: 20, twist_deg: 0, foot_cm: 0 },
    b1: { b_code: null },
    g2: { g_code: 'g_simple', modifiers: {} },
    a3: { reach_cm: 35, twist_deg: 0, foot_cm: 0 },
    b4: { b_code: null },
    p5: { p_base_code: 'p_put', p_addon_codes: [], precision: false },
    a6: { reach_cm: 0, twist_deg: 0, foot_cm: 0 },
  }
  // ADR-022 A-1：rows 帶後端持久化 computed ＋ narrative_zh
  const ROW = {
    hand: 'BH', frequency: 1, simo_pair_index: null,
    sub_activity: '搬取零件', narrative_zh: '雙手搬取零件至工作台',
    vocab_refs: {},
    computed: { total_tmu: 28, total_seconds: 1.008, eff_tmu: 28, contribution_tmu: 28 },
    cycle: CYCLE,
  }
  const versionDetail = (moduleId: string, versionNo: number) => ({
    id: 'ver-' + versionNo, module_id: moduleId, version_no: versionNo,
    rule_set_id: 'rs-1', rows: [ROW], narrative_zh: '雙手搬取零件至工作台',
    total_tmu: 28, total_seconds: 1.008,
    published_by: 'IEC141289', published_at: '2026-07-14T00:00:00Z',
  })
  const ACTION_SUMMARY = {
    id: ACTION_ID, site_id: null, name_zh: '搬取零件動作', category: 'action',
    keywords: [], scope: 'global', owner: null, status: 'standard', current_version: 1,
    created_at: '2026-07-14T00:00:00Z', updated_at: '2026-07-14T00:00:00Z',
    current_version_detail: null, total_tmu: 28, action_count: 1, seq_kind: 'GM', hand: 'BH',
    base_tmu: 28, frequency: 1,
  }
  // current_version=2 → WI 大綱顯示「已微調」badge
  const WI_SUMMARY = {
    id: WI_ID, site_id: null, name_zh: '搬取零件 WI', category: 'wi-template',
    keywords: [], scope: 'personal', owner: 'IEC141289', status: 'draft', current_version: 2,
    created_at: '2026-07-14T00:00:00Z', updated_at: '2026-07-14T00:00:00Z',
    current_version_detail: null, total_tmu: 28, action_count: 1, seq_kind: 'GM', hand: 'BH',
  }

  await page.route('/api/**', route => {
    const url = route.request().url()
    const method = route.request().method()

    // P1-B B-1：行內頻率 → PUT rows/0 → 後端重算發新版本（freq 2 → eff 56）
    if (method === 'PUT' && /\/rows\/\d+$/.test(url)) {
      const body = JSON.parse(route.request().postData() ?? '{}') as { frequency?: number }
      const freq = body.frequency ?? 1
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...versionDetail(ACTION_ID, 2),
          rows: [{ ...ROW, frequency: freq,
            computed: { total_tmu: 28, total_seconds: 1.008, eff_tmu: 28 * freq, contribution_tmu: 28 * freq } }],
          total_tmu: 28 * freq, total_seconds: 1.008 * freq,
        }),
      })
    }

    // 啟用中 rule-set（useActiveRuleSet；ADR-023 §3.5 取代寫死常數）
    if (url.includes('/api/v2/rule-sets/active')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' }) })
    }

    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 'MINIMOST_FACTORY_V2',
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
        }),
      })
    }

    if (url.includes('/api/v2/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ employee_no: 'IEC141289', roles: ['analyst'], level: 1 }),
      })
    }

    // 試算（builder / Inspector debounce）→ 固定回 28
    if (url.includes('/api/v2/minimost/calculate')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ seq: 'GM', total_tmu: 28, total_seconds: 1.008, tech_line: 'A6 B0 G6 A10 B0 P6 A0' }),
      })
    }

    // 動作清單（category=action）；scope=personal＝「我的」→ 此 mock 的動作是 global
    // scope 認證庫 → 我的為空（正是預設「全部」的理由，守則 §4）
    if (url.includes('/api/v2/motion-modules') && url.includes('category=action')) {
      const mine = url.includes('scope=personal')
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mine ? [] : [ACTION_SUMMARY]),
      })
    }

    // WI 大綱（category=wi-template）
    if (url.includes('/api/v2/motion-modules') && url.includes('category=wi-template')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([WI_SUMMARY]),
      })
    }

    // detail（動作清單每列 computed／WI 展開子列）
    if (url.includes(`/api/v2/motion-modules/${ACTION_ID}`)) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...ACTION_SUMMARY, current_version_detail: versionDetail(ACTION_ID, 1) }),
      })
    }
    if (url.includes(`/api/v2/motion-modules/${WI_ID}`)) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...WI_SUMMARY, current_version_detail: versionDetail(WI_ID, 2) }),
      })
    }

    // 其餘（vocab、cases、rule-sets 等）→ 空陣列
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: /MOST 工作台/ }).click()
  await page.waitForLoadState('networkidle')

  // 單頁：三 tab 按鈕不存在（ADR-022 B-1）
  await expect(page.getByRole('button', { name: '動作模組工作區' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'WI 組成工作區' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '製程途程工作區' })).toHaveCount(0)

  // 建立器直接可見（摘要列）＋動作清單列出個別動作（每列 Base/頻率/Eff 來自 computed）
  await expect(page.getByTestId('summary-bar')).toBeVisible()
  await expect(page.getByText('搬取零件動作')).toBeVisible()

  // WI 大綱區存在（ADR-022 B-3）：WI 列＋已微調 badge（version 2 > 1）
  const outline = page.getByTestId('wi-outline')
  await expect(outline).toBeVisible()
  await expect(outline.getByText('搬取零件 WI')).toBeVisible()
  await expect(outline.getByText('已微調')).toBeVisible()

  // 展開 WI → 子列（每列 narrative ＋ computed TMU）
  await outline.getByText('搬取零件 WI').click()
  await expect(outline.getByText('雙手搬取零件至工作台')).toBeVisible()

  // 點子列 → WiItemInspector 右抽屜開啟（ADR-022 B-4）
  await outline.getByText('雙手搬取零件至工作台').click()
  const inspector = page.getByTestId('wi-item-inspector')
  await expect(inspector).toBeVisible()
  await expect(inspector.getByRole('heading', { name: '動作模組詳情' })).toBeVisible()
  await expect(inspector.getByRole('button', { name: '重算並儲存' })).toBeVisible()

  // Inspector SIMO 配對選擇器可編輯（P1-B B-3；本 WI 僅一列 → 只有「無（獨立列）」）
  const simoSelect = inspector.getByTestId('inspector-simo-pair')
  await expect(simoSelect).toBeVisible()
  await expect(simoSelect).toHaveValue('')
  await expect(inspector.getByText('此 WI 僅一列，無可配對的對象。')).toBeVisible()

  // 取消 → 抽屜關閉
  await inspector.getByRole('button', { name: '取消' }).click()
  await expect(page.getByTestId('wi-item-inspector')).toHaveCount(0)

  // ── P1-B B-2：全部／我的 segmented（全部 1 筆、我的 0 筆＝global 認證庫不屬個人）──
  const ownerFilter = page.getByTestId('action-owner-filter')
  await expect(ownerFilter.getByRole('button', { name: /全部/ })).toHaveAttribute('aria-pressed', 'true')
  await ownerFilter.getByRole('button', { name: /我的/ }).click()
  await expect(page.getByText('共 0 筆')).toBeVisible()
  await ownerFilter.getByRole('button', { name: /全部/ }).click()
  await expect(page.getByText('共 1 筆')).toBeVisible()

  // ── P1-B B-1：行內頻率 input（1→2）→ PUT rows/0 → Eff 依後端回傳更新為 56 ────
  const freqInput = page.getByTestId('action-row-freq')
  await expect(freqInput).toHaveValue('1')
  await freqInput.fill('2')
  await expect(page.getByText(/已更新頻率並重算/)).toBeVisible()
  await expect(freqInput).toHaveValue('2')
  await expect(page.locator('tbody').getByText('56', { exact: true })).toBeVisible()
})

// ── P1-B code-review 回歸（M1/M2/M3）─────────────────────────────────────────
// M1: apiErrorMessage 需同時吃 FastAPI array 型與服務層 object 型 422 detail
// M2: 輸入無效（刪空）不得丟棄草稿 → 使用者續打的數字不會被接在舊值後
// M3: commit 的比較基準不得用 render closure 快照 → 在途改回原值不被靜默吞掉
test('P1-B 回歸：行內頻率草稿保留（M2）／在途改回值仍送出（M3）／422 訊息人話（M1）', async ({ page }) => {
  const ACTION_ID = 'cccccccc-1111-2222-3333-444444444444'
  const CYCLE = {
    seq: 'GM',
    a0: { reach_cm: 20, twist_deg: 0, foot_cm: 0 },
    b1: { b_code: null },
    g2: { g_code: 'g_simple', modifiers: {} },
    a3: { reach_cm: 35, twist_deg: 0, foot_cm: 0 },
    b4: { b_code: null },
    p5: { p_base_code: 'p_put', p_addon_codes: [], precision: false },
    a6: { reach_cm: 0, twist_deg: 0, foot_cm: 0 },
  }
  const ROW = {
    hand: 'BH', frequency: 1, simo_pair_index: null,
    sub_activity: '回歸動作', narrative_zh: '回歸動作敘述', vocab_refs: {},
    computed: { total_tmu: 28, total_seconds: 1.008, eff_tmu: 28, contribution_tmu: 28 },
    cycle: CYCLE,
  }
  const SUMMARY = {
    id: ACTION_ID, site_id: null, name_zh: '回歸動作', category: 'action',
    keywords: [], scope: 'global', owner: null, status: 'standard', current_version: 1,
    created_at: '2026-07-14T00:00:00Z', updated_at: '2026-07-14T00:00:00Z',
    current_version_detail: null, total_tmu: 28, action_count: 1, seq_kind: 'GM', hand: 'BH',
    base_tmu: 28, frequency: 1,
  }

  // 送出到後端的 frequency 序列（保序斷言用）
  const putFreqs: number[] = []
  let putMode: 'ok' | 'slow' | 'fastapi422' | 'service422' = 'ok'

  await page.route('/api/**', async route => {
    const url = route.request().url()
    const method = route.request().method()

    if (method === 'PUT' && /\/rows\/\d+$/.test(url)) {
      const body = JSON.parse(route.request().postData() ?? '{}') as { frequency?: number }
      const freq = body.frequency ?? 1
      putFreqs.push(freq)
      if (putMode === 'fastapi422') {
        // FastAPI/Pydantic 驗證錯誤：detail 恆為 array
        return route.fulfill({
          status: 422, contentType: 'application/json',
          body: JSON.stringify({ detail: [{ type: 'missing', loc: ['body', 'frequency'], msg: 'Field required' }] }),
        })
      }
      if (putMode === 'service422') {
        return route.fulfill({
          status: 422, contentType: 'application/json',
          body: JSON.stringify({ detail: { code: 'SIMO_PAIR_INVALID', message: '主列不得自身宣告配對' } }),
        })
      }
      if (putMode === 'slow') await new Promise(r => setTimeout(r, 1500))   // 在途窗（M3）
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          id: 'ver', module_id: ACTION_ID, version_no: 2, rule_set_id: 'rs-1',
          rows: [{ ...ROW, frequency: freq,
            computed: { total_tmu: 28, total_seconds: 1.008, eff_tmu: 28 * freq, contribution_tmu: 28 * freq } }],
          narrative_zh: '回歸動作敘述', total_tmu: 28 * freq, total_seconds: 1.008 * freq,
          published_by: 'IEC141289', published_at: '2026-07-14T00:00:00Z',
        }),
      })
    }

    // 啟用中 rule-set（useActiveRuleSet；ADR-023 §3.5 取代寫死常數）
    if (url.includes('/api/v2/rule-sets/active')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' }) })
    }

    if (url.includes('/api/v2/rule-sets/') && url.includes('/options')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({
          code: 'MINIMOST_FACTORY_V2', multiplier: 1,
          a_bands: { reach: [{ max_value: 5, index: 2 }], twist: [{ max_value: null, index: 0 }], foot: [{ max_value: null, index: 0 }] },
          b: [], g: [{ code: 'g_simple', label: '簡單抓握', modifier_key: null, requires_modifier: false }],
          p_bases: [{ code: 'p_put', label: '放置', label_en: 'Put' }], p_addons: [],
          m_verbs: [{ code: 'm_push', label: '推', pricing_kind: 'distance_ladder' }],
          x: [{ code: 'x_none', label: '無機器時間', mode: 'none' }],
          i: [{ code: 'i_none', label: '無', label_en: 'None' }],
        }) })
    }
    if (url.includes('/api/v2/minimost/calculate')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ seq: 'GM', total_tmu: 28, total_seconds: 1.008, tech_line: 'A6 B0 G6 A10 B0 P6 A0' }) })
    }
    if (url.includes('/api/v2/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ employee_no: 'IEC141289', roles: ['analyst'], level: 1 }) })
    }
    if (url.includes('/api/v2/motion-modules') && url.includes('category=action')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify(url.includes('scope=personal') ? [] : [SUMMARY]) })
    }
    if (url.includes(`/api/v2/motion-modules/${ACTION_ID}`)) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ ...SUMMARY, current_version_detail: {
          id: 'ver', module_id: ACTION_ID, version_no: 1, rule_set_id: 'rs-1', rows: [ROW],
          narrative_zh: '回歸動作敘述', total_tmu: 28, total_seconds: 1.008,
          published_by: 'IEC141289', published_at: '2026-07-14T00:00:00Z' } }) })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  })

  await page.goto('/')
  await page.getByRole('button', { name: /MOST 工作台/ }).click()
  await page.waitForLoadState('networkidle')

  const freq = page.getByTestId('action-row-freq')
  await expect(freq).toHaveValue('1')

  // ── M2：全選刪除 → 草稿保留為空（不跳回舊值）→ 續打 2 → 值必須是 "2" 而非 "12" ──
  await freq.fill('')
  await expect(freq).toHaveValue('')
  await page.waitForTimeout(700)                 // 跨過 debounce：無效輸入不得 commit
  expect(putFreqs).toEqual([])                   // 未送出任何 PUT
  await expect(freq).toHaveValue('')             // 草稿仍空（未被丟棄回舊值）
  await freq.pressSequentially('2')
  await expect(freq).toHaveValue('2')            // 若草稿被丟棄，這裡會是 "12"
  await expect(page.getByText(/已更新頻率並重算/)).toBeVisible()
  expect(putFreqs).toEqual([2])

  // ── M3：在途（存檔中）改回原值 → 不得被靜默吞掉，必須再送一次 PUT ────────────
  putMode = 'slow'
  await freq.fill('5')
  await page.waitForTimeout(700)                 // 第一發已送出、仍在途（1500ms 延遲）
  expect(putFreqs).toEqual([2, 5])
  await freq.fill('2')                           // 在途期間改回先前的值
  await page.waitForTimeout(4000)                // 等序列（5 → 2）跑完
  expect(putFreqs).toEqual([2, 5, 2])            // 「改回 2」有真的送出（未被 closure 快照吞掉）
  await expect(freq).toHaveValue('2')

  // ── M1a：FastAPI array 型 422 → 顯示人話，不得出現原始 JSON ─────────────────
  putMode = 'fastapi422'
  await freq.fill('7')
  await expect(page.getByText(/頻率更新失敗/)).toBeVisible()
  await expect(page.getByText(/frequency: Field required/)).toBeVisible()
  await expect(page.getByText(/\[\{"type"/)).toHaveCount(0)
  await expect(freq).toHaveValue('2')            // 失敗 → 回復後端原值

  // ── M1b：服務層 object 型 422 → 取 message ────────────────────────────────
  putMode = 'service422'
  await freq.fill('9')
  await expect(page.getByText(/主列不得自身宣告配對/)).toBeVisible()
  await expect(page.getByText(/SIMO_PAIR_INVALID/)).toHaveCount(0)
})
