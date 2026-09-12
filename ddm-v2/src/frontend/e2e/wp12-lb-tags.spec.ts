/**
 * WP12（ADR-035）LB 投影標記 UI — 一條主線 + 一個反例（真實 API + 真實 DB，經 preview_server）。
 *
 * 主線：clone demo worksheet → 存三列 → 進 Level System → 圈三列設 wcub → 切一列 offline
 *       → 整組（同 wcub）同步 offline → 儲存 → 預覽 lb-report（帶 W 碼）→ 匯出成功。
 * 反例：freq>1 的列指派 wcub → 即時擋（client-side，backend 為權威；tool-held 因 Row 無工具欄
 *       走後端/lb-report，見 assignWcub 註）。
 *
 * ⚠️ 自建 fixture（clone demo 5555 worksheet）；跑完 clone 出的 worksheet 由 DB 隔離環境處理。
 *    需 preview_server 在跑（E2E_BASE_URL）。demo worksheet 未種則 skip。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'

const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'
const OBJ = '66666666-6666-6666-6666-666666666666'

const GM_CYCLE = {
  seq: 'GM',
  rule_set_code: 'MINIMOST_FACTORY_V1',
  a0: { reach_cm: 20 },
  g2: { g_code: 'g_grasp' },
  a3: { reach_cm: 25 },
  p5: { p_base_code: 'p_place_none' },
}

async function demoSeeded(request: APIRequestContext): Promise<boolean> {
  const r = await request.get(`/api/v2/worksheets/${WS}/export/wi-preview`, { headers: AUTH })
  return r.status() === 200
}

test.describe('WP12 LB projection tags UI', () => {
  test('main line: wcub group + offline → save → lb-report atomic_groups contains the three rows', async ({ page, request }) => {
    test.skip(!(await demoSeeded(request)), 'demo worksheet 未種（先跑 dev_seed_v2.py）')
    // 三列同一 wcub（wcub20）、皆 offline、freq=1；action_type 標籤讓投影乾淨
    const ids = [crypto.randomUUID(), crypto.randomUUID(), crypto.randomUUID()]
    const rows = ids.map((id, k) => ({
      id, seq_no: k + 1, hand: 'RH', object_vocab_id: OBJ, frequency: 1,
      narrative: `列 ${k + 1}`, cycle: GM_CYCLE,
      level: { ascription: 'main', level: '1', action_type: 'place', worker_cub: 'wcub20', offline: true },
    }))
    const clone = await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })
    expect(clone.status(), await clone.text()).toBe(200)
    const wsId = ((await clone.json()) as { new_worksheet_id: string }).new_worksheet_id
    const saved = await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })
    expect(saved.status(), await saved.text()).toBe(200)

    // lb-report 讀已儲存 worksheet：atomic_groups 含這三列（wcub20 → atomic_group 20）
    const rep = await request.get(`/api/v2/worksheets/${wsId}/export/lb-report`, { headers: AUTH })
    expect(rep.status(), await rep.text()).toBe(200)
    const report = (await rep.json()) as {
      tasks_out: number; atomic_groups: Record<string, number[]>; errors: unknown[]; warnings: unknown[]
    }
    expect(report.tasks_out).toBe(3)
    expect(report.atomic_groups['20']).toBeDefined()
    expect([...report.atomic_groups['20']].sort((a, b) => a - b)).toEqual([1, 2, 3])

    // UI smoke：切到 Level System tab（元件掛載）
    await page.goto('/')
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' })))
  })

  test('deep: toggleOffline propagates across same wcub members (DEV store hook)', async ({ page }) => {
    await page.goto('/')
    const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
    test.skip(!hasHook, '需 dev server（import.meta.env.DEV）暴露 __ddmTest；preview build 不掛')
    const result = await page.evaluate(() => {
      const t = (window as unknown as { __ddmTest: { wiStore: { getState: () => Record<string, unknown> }; levelStore: { getState: () => Record<string, unknown> } } }).__ddmTest
      const wi = t.wiStore.getState() as { setRows: (r: unknown[]) => void }
      const mkRow = (id: string) => ({ id, seq: 'GM', handCode: 'RH', freq: 1, simoGroup: '', nv: { obj: '', from: '', to: '' }, narr: `r${id}`, narrEn: null, tmu: 10, seconds: 0.36, payload: {} })
      wi.setRows([mkRow('a'), mkRow('b'), mkRow('c')])
      const lv = t.levelStore.getState() as {
        sync: () => void; assignWcub: (id: string, l: string) => void; toggleOffline: (id: string) => void
        levelMap: Record<string, { workerCub: string; offline: boolean }>
      }
      lv.sync()
      ;['a', 'b', 'c'].forEach(id => lv.assignWcub(id, 'wcub9'))
      ;(t.levelStore.getState() as typeof lv).toggleOffline('a')
      const m = (t.levelStore.getState() as typeof lv).levelMap
      return { a: m['a']?.offline, b: m['b']?.offline, c: m['c']?.offline, aw: m['a']?.workerCub }
    })
    expect(result.aw).toBe('wcub9')
    expect(result.a).toBe(true)
    expect(result.b).toBe(true)
    expect(result.c).toBe(true)
  })

  test('reverse: freq>1 row assigned to wcub is blocked client-side (DEV store hook)', async ({ page }) => {
    await page.goto('/')
    const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
    test.skip(!hasHook, '需 dev server 暴露 __ddmTest；preview build 不掛')
    const result = await page.evaluate(() => {
      const t = (window as unknown as { __ddmTest: { wiStore: { getState: () => Record<string, unknown> }; levelStore: { getState: () => Record<string, unknown> } } }).__ddmTest
      const wi = t.wiStore.getState() as { setRows: (r: unknown[]) => void }
      // freq=8 的 lot 列
      wi.setRows([{ id: 'lot', seq: 'GM', handCode: 'RH', freq: 8, simoGroup: '', nv: { obj: '', from: '', to: '' }, narr: 'lot', narrEn: null, tmu: 10, seconds: 0.36, payload: {} }])
      const lv = t.levelStore.getState() as {
        sync: () => void; assignWcub: (id: string, l: string) => void
        levelMap: Record<string, { workerCub: string }>; wcubError: string
      }
      lv.sync()
      ;(t.levelStore.getState() as typeof lv).assignWcub('lot', 'wcub9')
      const s = t.levelStore.getState() as typeof lv
      return { assigned: s.levelMap['lot']?.workerCub || '', err: s.wcubError }
    })
    expect(result.assigned).toBe('')      // 未指派（被擋）
    expect(result.err).toBe('lot')        // wcubError 指向被擋的列
  })
})
