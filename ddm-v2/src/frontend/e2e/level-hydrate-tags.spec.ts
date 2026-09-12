/**
 * F1（ADR-035 D10）：hydrate 還原 lb_tags + 重建 workerCubMeta。
 * API 存三列帶 offline／worker_cub／segment → 設 activeWs 載入 → __ddmTest.levelStore 的
 * levelMap 帶回同值、workerCubMeta 重建。需 dev server（__ddmTest，import.meta.env.DEV）。
 */
import { test, expect, type APIRequestContext } from '@playwright/test'

const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'
const OBJ = '66666666-6666-6666-6666-666666666666'
const GM = { seq: 'GM', rule_set_code: 'MINIMOST_FACTORY_V1', a0: { reach_cm: 20 }, g2: { g_code: 'g_grasp' }, a3: { reach_cm: 25 }, p5: { p_base_code: 'p_place_none' } }

async function seeded(request: APIRequestContext): Promise<boolean> {
  return (await request.get(`/api/v2/worksheets/${WS}`, { headers: AUTH })).status() === 200
}

test('hydrate restores lb_tags and rebuilds workerCubMeta', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  // 三列同一 wcub、皆帶 offline/segment、freq=1
  const ids = [crypto.randomUUID(), crypto.randomUUID(), crypto.randomUUID()]
  const rows = ids.map((id, k) => ({
    id, seq_no: k + 1, hand: 'RH', object_vocab_id: OBJ, frequency: 1,
    narrative: `列 ${k + 1}`, wi_group: '裝 HDD', cycle: GM,
    level: {
      ascription: 'main', level: '2',
      worker_cub: 'wcub20', offline: true, segment: 'dimm', action_type: 'insert',
    },
  }))
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  const saved = await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })
  expect(saved.status(), await saved.text()).toBe(200)

  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')

  await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
    t.workspace.getState().setActiveWs(id)
    // 切到 level tab → LevelSystem 掛載 useWorksheetWorkspace → 觸發 hydrate
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' }))
  }, wsId)

  // 等 hydrate（levelMap 有三列且帶回 offline）
  await page.waitForFunction((rowIds) => {
    const t = (window as unknown as { __ddmTest?: { levelStore: { getState: () => { levelMap: Record<string, { offline: boolean }> } } } }).__ddmTest
    if (!t) return false
    const m = t.levelStore.getState().levelMap
    return rowIds.every((id: string) => m[id]?.offline === true)
  }, ids, { timeout: 8000 })

  const result = await page.evaluate((rowIds) => {
    const t = (window as unknown as { __ddmTest: { levelStore: { getState: () => { levelMap: Record<string, { workerCub: string; offline: boolean; segment: string; actionType: string; level: string }>; workerCubMeta: Record<string, unknown> } } } }).__ddmTest
    const s = t.levelStore.getState()
    const first = s.levelMap[rowIds[0]]
    return {
      workerCub: first.workerCub, offline: first.offline, segment: first.segment,
      actionType: first.actionType, level: first.level,
      allSameWcub: rowIds.every((id: string) => s.levelMap[id]?.workerCub === 'wcub20'),
      wcubMetaHas: Object.prototype.hasOwnProperty.call(s.workerCubMeta, 'wcub20'),
    }
  }, ids)

  expect(result.workerCub).toBe('wcub20')
  expect(result.offline).toBe(true)
  expect(result.segment).toBe('dimm')
  expect(result.actionType).toBe('insert')
  expect(result.level).toBe('2')          // I-1：同 chain level 統一為 '2'
  expect(result.allSameWcub).toBe(true)
  expect(result.wcubMetaHas).toBe(true)   // workerCubMeta 重建
})
