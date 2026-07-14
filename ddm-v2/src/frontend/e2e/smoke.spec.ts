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
  await expect(page.getByText('Rule-set 總覽')).toBeVisible()
  await expect(page.getByText('案件狀態統計')).toBeVisible()
  await expect(page.getByText('近期案件')).toBeVisible()
})

test('sidebar navigation renders each migrated feature', async ({ page }) => {
  await page.goto('/')

  // Rule-set tab (admin-gated; seed user IEC141289 is admin)
  await page.getByRole('button', { name: /Rule-set/ }).click()
  await expect(page.getByText(/A — 移動距離/)).toBeVisible()

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

    // 動作清單（category=action）
    if (url.includes('/api/v2/motion-modules') && url.includes('category=action')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([ACTION_SUMMARY]),
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

  // 取消 → 抽屜關閉
  await inspector.getByRole('button', { name: '取消' }).click()
  await expect(page.getByTestId('wi-item-inspector')).toHaveCount(0)
})
