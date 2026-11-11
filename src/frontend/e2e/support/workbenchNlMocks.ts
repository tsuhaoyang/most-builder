// 共用 mock：MOST 工作台（workbench-v3）× NL 草稿 e2e（multiaction / guards 兩 spec 共用）。
// 後端契約（wi_ai_service）：頂層 slots/suggested_seq **永遠來自 rule_based** 的壓平相容
// 欄位；ai.drafts 是權威草稿（DDM_WI_AI_ENABLED=1 時可能來自 LLM，兩者可分歧）。
// 全部 API 以 page.route mock（測試資料自建，不依賴環境既存資料；CI_GATES 硬性規則 7）。
import type { Page, Route } from '@playwright/test'

export const RUN_ID = 'run-e2e-nl-1'
export const NEW_MODULE_ID = 'dddddddd-1111-2222-3333-444444444444'

export interface DraftFixture {
  action_id: string
  cycle: Record<string, unknown> | null
  complete: boolean
  engine_result: { total_tmu: number; total_seconds: number; tech_line: string } | null
  narrative: string
  issues: string[]
}

export const GM_CYCLE: Record<string, unknown> = {
  seq: 'GM', rule_set_code: 'MINIMOST_FACTORY_V2',
  a0: { reach_cm: 20, twist_deg: 0, foot_cm: 0 },
  b1: { b_code: null },
  g2: { g_code: 'g_simple', modifiers: {}, repeat_count: 1 },
  a3: { reach_cm: 35, twist_deg: 0, foot_cm: 0 },
  b4: { b_code: null },
  p5: { p_base_code: 'p_put', p_addon_codes: [], precision: false, repeat_count: 1 },
  a6: { reach_cm: 0, twist_deg: 0, foot_cm: 0 },
}
export const CM_CYCLE: Record<string, unknown> = {
  seq: 'CM', rule_set_code: 'MINIMOST_FACTORY_V2',
  a0: { reach_cm: 20, twist_deg: 0, foot_cm: 0 },
  b1: { b_code: null },
  g2: { g_code: 'g_simple', modifiers: {}, repeat_count: 1 },
  m3: { m_components: [{ verb_code: 'm_push', distance_cm: 45, angle_deg: 90, revolutions: 1, diameter_cm: 10 }] },
  x4: { x_code: 'x_none', x_seconds: 0 },
  i5: { i_code: 'i_none' },
  a6: { reach_cm: 0, twist_deg: 0, foot_cm: 0 },
}
// compiler 對「沒講距離」的 CM 會編出 distance_cm=0.0（後端 MComponent 預設）——
// 用來釘「前端不得把 0 捏造成 30」的守衛（cycle.ts payloadToState 的 ?? 修正）
export const CM_CYCLE_D0: Record<string, unknown> = {
  seq: 'CM', rule_set_code: 'MINIMOST_FACTORY_V2',
  a0: { reach_cm: 20, twist_deg: 0, foot_cm: 0 },
  b1: { b_code: null },
  g2: { g_code: 'g_simple', modifiers: {}, repeat_count: 1 },
  m3: { m_components: [{ verb_code: 'm_push', distance_cm: 0.0, angle_deg: 0, revolutions: 1, diameter_cm: 0 }] },
  x4: { x_code: 'x_none', x_seconds: 0 },
  i5: { i_code: 'i_none' },
  a6: { reach_cm: 0, twist_deg: 0, foot_cm: 0 },
}

export const DRAFT_1: DraftFixture = {
  action_id: 'act-1',
  cycle: GM_CYCLE,
  complete: true,
  engine_result: { total_tmu: 28, total_seconds: 1.008, tech_line: 'A6 B0 G6 A10 B0 P6 A0' },
  narrative: '從料架取得DIMM，放至流水線',
  issues: [],
}
export const DRAFT_2: DraftFixture = {
  action_id: 'act-2',
  cycle: CM_CYCLE,
  complete: true,
  engine_result: { total_tmu: 29, total_seconds: 1.044, tech_line: 'A10 B0 G3 M16 X0 I0 A0' },
  narrative: '推治具到位',
  issues: [],
}
// LLM 判 CM（distance 未提及 → 0）的權威草稿——與 rule 相容欄位（GM）不一致的情境
export const DRAFT_CM_D0: DraftFixture = {
  action_id: 'act-cm0',
  cycle: CM_CYCLE_D0,
  complete: true,
  engine_result: { total_tmu: 24, total_seconds: 0.864, tech_line: 'A10 B0 G3 M11 X0 I0 A0' },
  narrative: '推治具到位（未講距離）',
  issues: [],
}
// 無 cycle 的草稿（composite_unknown）：永遠採用不了——keepNl 不得因它讓面板永不收
export const DRAFT_NULL: DraftFixture = {
  action_id: 'act-2',
  cycle: null,
  complete: false,
  engine_result: null,
  narrative: '（無法拆解的複合描述）',
  issues: ['composite_unknown'],
}

// 舊相容欄位（slots/suggested_seq）＝rule_based 的 GM 壓平——正是
// 「靜默只取第一筆」與「LLM/rule 不一致仍覆蓋成 rule 猜測」兩支 bug 的來源
export const LEGACY_FIELDS = {
  raw_text: '',
  normalized_text: '',
  suggested_seq: 'GM',
  overall_confidence: 0.82,
  slots: [
    { slot_index: 2, field: 'g_code', chosen: { option_code: 'g_simple', score: 0.9, source: 'exact' }, needs_review: false },
    { slot_index: 5, field: 'p_base_code', chosen: { option_code: 'p_put', score: 0.7, source: 'longest_match' }, needs_review: false },
  ],
  provenance: { parser: 'rule_based_v1' },
}

export function nlDraftResponse(drafts: DraftFixture[], multi: boolean) {
  return {
    ...LEGACY_FIELDS,
    ai: {
      run_id: RUN_ID,
      plan: {
        schema_version: 'v2', source_text: '', normalized_text: '',
        actions: drafts.map((d, i) => ({
          action_id: d.action_id,
          action_type: d.cycle == null ? 'composite_unknown' : (d.cycle.seq === 'CM' ? 'controlled_move' : 'move_place'),
          sequence_order: i + 1,
          roles: {},
        })),
        unresolved: [],
      },
      slot_candidates: [],
      drafts,
      routing_status: 'review',
      routing_reasons: multi ? ['multi_action'] : [],
      provenance: { planner: 'rule_based_v1', fallback: true },
      source_revision: null,
    },
    multi_action_warning: multi,
  }
}

export interface Captured {
  /** POST /minimost/calculate 的 request bodies（偵測「未經採用就套進編輯器」＋距離捏造） */
  calcBodies: Array<Record<string, unknown>>
  /** POST /nl-drafts/{run}/reviews 的 bodies（逐筆 accept_plan 事件） */
  reviewBodies: Array<Record<string, unknown>>
}

export interface MockOptions {
  /** /api/v2/me 的 RBAC level（前端 canEdit = level>=1）；預設 1（IE） */
  meLevel?: number
  /** POST reviews 的回應狀態；預設 201。403 等失敗仍會記錄 body（驗「有送但失敗」） */
  reviewStatus?: number
}

/** CM 的 TMU 依 distance 給值（斷言才有鑑別力：0 捏造成 30 會直接算出不同 TMU） */
const CM_TMU_BY_DISTANCE: Record<string, { tmu: number; sec: number; tech: string }> = {
  '45': { tmu: 29, sec: 1.044, tech: 'A10 B0 G3 M16 X0 I0 A0' },
  '30': { tmu: 16, sec: 0.576, tech: 'A0 B0 G0 M16 X0 I0 A0' },
  '0': { tmu: 24, sec: 0.864, tech: 'A10 B0 G3 M11 X0 I0 A0' },
}

export async function installMocks(page: Page, opts: MockOptions = {}): Promise<Captured> {
  const { meLevel = 1, reviewStatus = 201 } = opts
  const captured: Captured = { calcBodies: [], reviewBodies: [] }

  await page.route('/api/**', (route: Route) => {
    const url = route.request().url()
    const method = route.request().method()
    const pathname = new URL(url).pathname
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (pathname === '/api/v2/worksheets/nl-draft' && method === 'POST') {
      const body = JSON.parse(route.request().postData() ?? '{}') as { text?: string }
      const text = body.text ?? ''
      if (text.includes('單動作')) return json(nlDraftResponse([DRAFT_1], false))
      // 單 action、但相容欄位（GM/rule）與權威草稿（CM/LLM）不一致
      if (text.includes('不一致')) return json(nlDraftResponse([DRAFT_CM_D0], false))
      // 多 action，其中一筆無 cycle（composite_unknown）
      if (text.includes('含無法拆解')) return json(nlDraftResponse([DRAFT_1, DRAFT_NULL], true))
      return json(nlDraftResponse([DRAFT_1, DRAFT_2], true))
    }

    if (/\/api\/v2\/nl-drafts\/[^/]+\/reviews$/.test(pathname) && method === 'POST') {
      captured.reviewBodies.push(JSON.parse(route.request().postData() ?? '{}'))
      if (reviewStatus >= 400) return json({ detail: 'mock review rejected' }, reviewStatus)
      return json({ run_id: RUN_ID, event_ids: ['ev-1'], candidate_ids: [] }, reviewStatus)
    }

    if (pathname === '/api/v2/minimost/calculate' && method === 'POST') {
      const body = JSON.parse(route.request().postData() ?? '{}') as Record<string, unknown>
      captured.calcBodies.push(body)
      const g2 = body.g2 as { g_code?: string | null } | undefined
      if (!g2?.g_code) {
        // 空編輯器（初始/清空後 debounce 試算）→ 0，讓草稿值成為「內容被套用」的專屬訊號
        return json({ seq: body.seq, total_tmu: 0, total_seconds: 0, tech_line: '' })
      }
      if (body.seq === 'CM') {
        const m3 = body.m3 as { m_components?: Array<{ distance_cm?: number }> } | undefined
        const dist = String(m3?.m_components?.[0]?.distance_cm ?? '')
        const hit = CM_TMU_BY_DISTANCE[dist] ?? { tmu: 13, sec: 0.468, tech: 'A10 B0 G3 M?? X0 I0 A0' }
        return json({ seq: 'CM', total_tmu: hit.tmu, total_seconds: hit.sec, tech_line: hit.tech })
      }
      // GM：依 g_code 給值（g_heavy 供「編輯器既有內容」的鑑別）
      const heavy = g2.g_code === 'g_heavy'
      return json({
        seq: 'GM',
        total_tmu: heavy ? 34 : 28,
        total_seconds: heavy ? 1.224 : 1.008,
        tech_line: heavy ? 'A6 B0 G12 A10 B0 P6 A0' : 'A6 B0 G6 A10 B0 P6 A0',
      })
    }

    if (pathname === '/api/v2/rule-sets/active') {
      return json({ id: 'rs-1', code: 'MINIMOST_FACTORY_V2', name_zh: 'MiniMOST 工廠規則 v2' })
    }

    if (pathname.startsWith('/api/v2/rule-sets/') && pathname.endsWith('/options')) {
      return json({
        code: 'MINIMOST_FACTORY_V2',
        multiplier: 1,
        a_bands: {
          reach: [{ max_value: 25, index: 6 }, { max_value: 50, index: 10 }],
          twist: [{ max_value: null, index: 0 }],
          foot: [{ max_value: null, index: 0 }],
        },
        b: [{ code: 'b_eye', label: '眼睛移動' }],
        g: [
          { code: 'g_simple', label: '簡單抓握', modifier_key: null, requires_modifier: false },
          { code: 'g_heavy', label: '重物抓握', modifier_key: null, requires_modifier: false },
        ],
        p_bases: [{ code: 'p_put', label: '放置', label_en: 'Put' }],
        p_addons: [],
        m_verbs: [{ code: 'm_push', label: '推', pricing_kind: 'distance_ladder' }],
        x: [{ code: 'x_none', label: '無機器時間', mode: 'none' }],
        i: [{ code: 'i_none', label: '無', label_en: 'None' }],
      })
    }

    if (pathname === '/api/v2/me') {
      return json({ employee_no: 'IEC141289', roles: meLevel >= 1 ? ['IE'] : ['viewer'], level: meLevel })
    }

    // 儲存迴圈（採用→新增動作→採用下一筆）：create → 可見性輪詢 GET → publish
    if (pathname === '/api/v2/motion-modules' && method === 'POST') {
      return json({
        id: NEW_MODULE_ID, site_id: null, name_zh: 'E2E多動作-1', category: 'action',
        keywords: [], scope: 'personal', owner: 'IEC141289', status: 'draft', current_version: 0,
        created_at: '2026-08-15T00:00:00Z', updated_at: '2026-08-15T00:00:00Z',
        current_version_detail: null, total_tmu: null, action_count: 0, seq_kind: null, hand: null,
      }, 201)
    }
    if (pathname === `/api/v2/motion-modules/${NEW_MODULE_ID}` && method === 'GET') {
      return json({
        id: NEW_MODULE_ID, site_id: null, name_zh: 'E2E多動作-1', category: 'action',
        keywords: [], scope: 'personal', owner: 'IEC141289', status: 'draft', current_version: 0,
        created_at: '2026-08-15T00:00:00Z', updated_at: '2026-08-15T00:00:00Z',
        current_version_detail: null, total_tmu: null, action_count: 0, seq_kind: null, hand: null,
      })
    }
    if (pathname === `/api/v2/motion-modules/${NEW_MODULE_ID}/publish` && method === 'POST') {
      return json({
        id: 'ver-1', module_id: NEW_MODULE_ID, version_no: 1, rule_set_id: 'rs-1',
        rows: [{
          hand: 'RH', frequency: 1, simo_pair_index: null, sub_activity: 'E2E多動作-1',
          narrative_zh: 'E2E多動作-1', vocab_refs: {},
          computed: { total_tmu: 28, total_seconds: 1.008, eff_tmu: 28, contribution_tmu: 28 },
          cycle: GM_CYCLE,
        }],
        narrative_zh: 'E2E多動作-1', total_tmu: 28, total_seconds: 1.008,
        published_by: 'IEC141289', published_at: '2026-08-15T00:00:00Z',
      }, 201)
    }

    // 其餘（動作清單、WI 大綱、vocab…）→ 空陣列
    return json([])
  })

  return captured
}

export async function gotoWorkbench(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: /MOST 工作台/ }).click()
  await page.waitForLoadState('networkidle')
}

export async function gotoWorkbenchAndParse(page: Page, text: string) {
  await gotoWorkbench(page)
  await parseNl(page, text)
}

export async function parseNl(page: Page, text: string) {
  await page.locator('input[placeholder*="輸入動作描述"]').fill(text)
  await page.getByRole('button', { name: 'AI 預填' }).click()
  await page.getByTestId('nl-result-panel').waitFor({ state: 'visible' })
}

/** 是否有任何「草稿內容」被送去試算＝草稿被套進了編輯器（g_simple 或 CM 形） */
export function draftContentCalculated(calcBodies: Array<Record<string, unknown>>): boolean {
  return calcBodies.some(b => {
    const g2 = b.g2 as { g_code?: string | null } | undefined
    return g2?.g_code === 'g_simple' || b.seq === 'CM'
  })
}
