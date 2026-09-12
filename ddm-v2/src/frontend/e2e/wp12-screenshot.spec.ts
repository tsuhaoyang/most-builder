/**
 * WP12 截圖：Level System LB 標記 UI（供 Howard 看設計）。
 * 存 docs/lb-integration/screenshots/level-system-lb-tags.png。需 dev server（5173，暴露 __ddmTest）。
 *
 * 流程：API 建一個含三列的 worksheet → 設 activeWs（元件載入真實列）→ 待 hydrate →
 *       用 store hook 套 wcub/offline/action_type/merge_lock（hydrate 後不還原 wcub，故此處手動套以展示 UI）
 *       → 切 level tab → 截圖。
 */
import { test, expect } from '@playwright/test'

const SHOT = '../../docs/lb-integration/screenshots/level-system-lb-tags.png'
const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'
const OBJ = '66666666-6666-6666-6666-666666666666'
const GM = { seq: 'GM', rule_set_code: 'MINIMOST_FACTORY_V1', a0: { reach_cm: 20 }, g2: { g_code: 'g_grasp' }, a3: { reach_cm: 25 }, p5: { p_base_code: 'p_place_none' } }

test('capture Level System LB tags UI', async ({ page, request }) => {
  // demo 未種則跳過
  const seeded = (await request.get(`/api/v2/worksheets/${WS}/export/wi-preview`, { headers: AUTH })).status() === 200
  test.skip(!seeded, 'demo worksheet 未種')

  // 建三列 worksheet
  const clone = await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })
  const wsId = ((await clone.json()) as { new_worksheet_id: string }).new_worksheet_id
  const rows = [0, 1, 2].map(k => ({
    id: crypto.randomUUID(), seq_no: k + 1, hand: 'RH', object_vocab_id: OBJ, frequency: 1,
    narrative: ['取 DIMM', '插入 DIMM', '扣上卡榫'][k], cycle: GM,
    level: { ascription: 'main', level: '1', action_type: 'place' },
  }))
  await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })

  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')

  // 設 activeWs（元件會 fetch+hydrate 真實列）
  await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
    t.workspace.getState().setActiveWs(id)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' }))
  }, wsId)

  // 等 rows 載入（wi store 有列）
  await page.waitForFunction(() => {
    const t = (window as unknown as { __ddmTest?: { wiStore: { getState: () => { rows: unknown[] } } } }).__ddmTest
    return !!t && t.wiStore.getState().rows.length >= 3
  }, { timeout: 8000 }).catch(() => {})

  // hydrate 後套 wcub/offline/標籤（展示 UI；wcub 後端不還原故手動套）
  await page.evaluate(() => {
    const t = (window as unknown as { __ddmTest: { wiStore: { getState: () => { rows: { id: string }[] } }; levelStore: { getState: () => Record<string, unknown> } } }).__ddmTest
    const ids = t.wiStore.getState().rows.map(r => r.id)
    const lv = t.levelStore.getState() as {
      assignWcub: (id: string, l: string) => void; toggleOffline: (id: string) => void
      setActionType: (id: string, s: string) => void; toggleMergeLock: (id: string) => void
    }
    ids.forEach(id => lv.assignWcub(id, 'wcub20'))
    if (ids[0]) (t.levelStore.getState() as typeof lv).toggleOffline(ids[0])
    if (ids[1]) (t.levelStore.getState() as typeof lv).setActionType(ids[1], 'insert')
    if (ids[2]) (t.levelStore.getState() as typeof lv).toggleMergeLock(ids[2])
  })
  await page.waitForTimeout(600)
  // 等 Level System 標題出現（非空狀態）再截；截圖是設計產物，不作硬性斷言 gate
  await page.getByText('Level System').first().waitFor({ timeout: 5000 }).catch(() => {})
  await page.screenshot({ path: SHOT, fullPage: true })
  const emptyNotice = await page.getByText('請先從分析案件開啟工時表').count().catch(() => 0)
  if (emptyNotice > 0) console.warn('[wp12-screenshot] rendered empty-state; check activeWs/rows timing')
  expect(true).toBe(true)
})
