/**
 * F9 截圖（ADR-035 D10 §8.3）：黃金複本 24 列 → 11 作業載入狀態，截 4 張：
 *   level-jobs-flow.png（作業順序）、level-jobs-drawer.png（作業內容抽屜）、
 *   level-jobs-line.png（產線視圖）、level-jobs-flow.en.png（英文）。
 * 需 dev server（__ddmTest, import.meta.env.DEV）。
 * 預設寫進本測試的輸出目錄（test-results/，gitignore）；要更新版控的 docs/lb-integration/screenshots/
 * 才帶 UPDATE_SCREENSHOTS=1——平常跑 e2e 不應改動文件截圖。
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import path from 'node:path'
import { ensureReplicaVocab, buildGoldenRows, FIXTURES_DIR } from './support/goldenReplica'

const AUTH = { 'X-Username': 'IEC141289' }
const WS = '55555555-5555-5555-5555-555555555555'
// 相對 spec 檔解析（FIXTURES_DIR＝<repo>/ddm-v2/docs/lb-integration/fixtures），不隨執行目錄跑掉
const DOCS_DIR = path.resolve(FIXTURES_DIR, '..', 'screenshots')
const shot = (name: string): string =>
  process.env.UPDATE_SCREENSHOTS === '1' ? `${DOCS_DIR}/${name}` : test.info().outputPath(name)

async function seeded(request: APIRequestContext): Promise<boolean> {
  return (await request.get(`/api/v2/worksheets/${WS}`, { headers: AUTH })).status() === 200
}

async function loadJobs(page: Page, request: APIRequestContext): Promise<void> {
  const vocab = await ensureReplicaVocab(request)
  const rows = buildGoldenRows(vocab)
  const wsId = ((await (await request.post(`/api/v2/worksheets/${WS}/clone`, { headers: AUTH })).json()) as { new_worksheet_id: string }).new_worksheet_id
  await request.put(`/api/v2/worksheets/${wsId}`, { headers: AUTH, data: { rows } })
  await page.goto('/')
  const hasHook = await page.evaluate(() => !!(window as unknown as Record<string, unknown>).__ddmTest)
  test.skip(!hasHook, '需 dev server 暴露 __ddmTest')
  await page.evaluate((id) => {
    const t = (window as unknown as { __ddmTest: { workspace: { getState: () => { setActiveWs: (i: string) => void } } } }).__ddmTest
    t.workspace.getState().setActiveWs(id)
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'level' }))
  }, wsId)
  await page.locator('[data-testid^="job-card-"]').first().waitFor({ timeout: 10000 })
  // 等預覽落定（pill-ok 出現）才拍，避免拍到 gate 未開的 updating 狀態
  await page.getByTestId('pill-ok').waitFor({ timeout: 10000 })
  await page.waitForTimeout(400)
}

test('capture jobs flow + drawer + line (11-job golden)', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  await loadJobs(page, request)

  // flow
  await page.screenshot({ path: shot('level-jobs-flow.png'), fullPage: true })

  // drawer：點第一張作業卡
  await page.locator('[data-testid^="job-card-"]').first().click()
  await page.waitForTimeout(400)
  await page.screenshot({ path: shot('level-jobs-drawer.png'), fullPage: true })
  await page.keyboard.press('Escape').catch(() => {})

  // line
  await page.getByTestId('subview-line').click()
  await page.getByTestId('line-view').waitFor({ timeout: 5000 })
  await page.waitForTimeout(400)
  await page.screenshot({ path: shot('level-jobs-line.png'), fullPage: true })
  expect(true).toBe(true)
})

test('capture jobs flow (en locale)', async ({ page, request }) => {
  test.skip(!(await seeded(request)), 'demo worksheet 未種')
  await request.patch('/api/v2/me/locale', { headers: AUTH, data: { locale: 'en' } })
  await loadJobs(page, request)
  await page.screenshot({ path: shot('level-jobs-flow.en.png'), fullPage: true })
  await request.patch('/api/v2/me/locale', { headers: AUTH, data: { locale: 'zh-TW' } })
  expect(true).toBe(true)
})
