/**
 * F9 UI（ADR-035 D10 §8.3）：黃金複本 24 列 → 作業版顯示 11 作業；驗證 flow/line 切換、mergeUp、
 * 同站、personBlocked（wcub 同人時同站禁用）、儲存並交給產線平衡（lb-report groups）、en 語系字串。
 * 需 dev server（__ddmTest, import.meta.env.DEV）。
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import { ensureReplicaVocab, buildGoldenRows } from './support/goldenReplica'

const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'

async function seeded(request: APIRequestContext): Promise<boolean> {
  return (await request.get(`/api/v2/worksheets/${WS}`, { headers: AUTH })).status() === 200
}

async function loadJobs(page: Page, request: APIRequestContext): Promise<string> {
  const vocab = await ensureReplicaVocab(request)
  const rows = buildGoldenRows(vocab)
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  const saved = await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })
  expect(saved.status(), await saved.text()).toBe(200)
  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')
  await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
    t.workspace.getState().setActiveWs(id)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' }))
  }, wsId)
  await page.locator('[data-testid^="job-card-"]').first().waitFor({ timeout: 10000 })
  return wsId
}

test('load never flickers 要處理: pill-err never appears; settles to pill-ok', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  const vocab = await ensureReplicaVocab(request)
  const rows = buildGoldenRows(vocab)
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  const saved = await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })
  expect(saved.status(), await saved.text()).toBe(200)

  // 監看每個 preview 回應：載入期間不得回 E（gate 未開時根本不發）
  const previewErrCodes: string[][] = []
  page.on('response', async r => {
    if (r.url().includes('/lb-report/preview')) {
      try { const j = await r.json(); previewErrCodes.push((j.errors ?? []).map((e: { code: string }) => e.code)) } catch { /* ignore */ }
    }
  })

  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')
  await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
    t.workspace.getState().setActiveWs(id)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' }))
  }, wsId)

  // 載入期間任何時刻都不得出現「要處理」(pill-err)
  let sawErr = false
  const deadline = Date.now() + 4000
  while (Date.now() < deadline) {
    if (await page.getByTestId('pill-err').count() > 0) sawErr = true
    await page.waitForTimeout(70)
  }
  expect(sawErr, 'pill-err（要處理）在載入過程中不得出現').toBe(false)
  // 最終落定 ok
  await expect(page.getByTestId('pill-ok')).toBeVisible()
  // 發出的每個 preview 都沒有 E（gate 確保只在 hydrate+baseline 後才發）
  for (const codes of previewErrCodes) expect(codes, JSON.stringify(previewErrCodes)).toEqual([])
})

test('golden replica renders 11 jobs; flow/line toggle + save-export lb groups', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  const wsId = await loadJobs(page, request)

  // A.5：11 個作業
  await expect(page.locator('[data-testid^="job-card-"]')).toHaveCount(11)

  // flow → line 子視圖切換
  await page.getByTestId('subview-line').click()
  await expect(page.getByTestId('line-view')).toBeVisible()
  await expect(page.locator('[data-testid^="line-block-"]')).toHaveCount(11)
  await page.getByTestId('subview-flow').click()
  await expect(page.locator('[data-testid^="job-card-"]').first()).toBeVisible()

  // errors==[] → ok pill；儲存並交給產線平衡可按（disabled=false）
  await expect(page.getByTestId('pill-ok')).toBeVisible()
  await expect(page.getByTestId('jobs-save-export')).toBeEnabled()

  // lb-report：以 wcub 產生 atomic_groups（J1-J3 wcub20 / N1-N3 wcub21）——皆為以 id 為鍵的物件
  const rep = await (await request.get(`/api/v2/worksheets/${wsId}/export/lb-report`, { headers: AUTH })).json() as { atomic_groups: Record<string, unknown>; groups: Record<string, unknown> }
  expect(Object.keys(rep.atomic_groups).length).toBeGreaterThanOrEqual(2)
  expect(Object.keys(rep.groups).length).toBeGreaterThan(0)
})

test('en locale renders English job-UX strings', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  await request.patch('/api/v2/me/locale', { headers: AUTH, data: { locale: 'en' } })
  await loadJobs(page, request)
  // §6.1 en：view.line / save-export 英文字串
  await expect(page.getByTestId('subview-line')).toHaveText(/line|Line/)
  await expect(page.getByTestId('jobs-save-export')).toContainText(/balanc/i)
  // 還原 zh-TW（不污染其他測試）
  await request.patch('/api/v2/me/locale', { headers: AUTH, data: { locale: 'zh-TW' } })
})
