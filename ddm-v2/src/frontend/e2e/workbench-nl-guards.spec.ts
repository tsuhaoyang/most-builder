import { test, expect, type Page } from '@playwright/test'
import {
  installMocks, gotoWorkbench, gotoWorkbenchAndParse, parseNl, draftContentCalculated,
} from './support/workbenchNlMocks'

// ── MOST 工作台（workbench-v3）× NL 草稿守門（checkpoint 審查修正的釘子）─────────
// 對應修正：
//   G1) cycle.ts payloadToState：distance_cm=0 不得被 || 捏造成 30（No fake defaults）
//   G2) 單 action 但 LLM 權威草稿與 rule 相容欄位不一致 → 不得自動覆蓋成 rule 猜測
//   G3) review 事件依角色 gating（viewer 不送）＋失敗灰字提示不吞錯（No error bypass）
//   G4) 編輯器有內容時採用草稿需覆蓋確認（取消＝不動）
//   G5) 覆蓋/填空 modal 守門（test-engineer A5a：編輯器有內容才出現，兩鍵語意各驗）
//   G6) keepNl：無 cycle 的草稿（composite_unknown）不得讓 NL 面板永不自動收
// mock 與 fixtures 共用 ./support/workbenchNlMocks。

// 冷啟動（首次載入 dist bundle）可能超過預設 30s，錯誤會誤指到內容斷言
test.setTimeout(60_000)

/** 先把編輯器弄出內容：G 格位手動選「重物抓握」（g_heavy → mock 算 34 TMU） */
async function fillGHeavy(page: Page) {
  await page.getByTestId('flow-item-G').getByRole('button').first().click()
  const modal = page.locator('div.fixed.inset-0').filter({ hasText: 'G 取得' })
  await modal.locator('select').first().selectOption('g_heavy')
  await modal.getByRole('button', { name: '確認' }).click()
  // 後端（mock）算得 34 ＝ g_heavy 已入編輯器且試算完成
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('34')
}

// ── G2：LLM/rule 不一致（單 action）─────────────────────────────────────────────
test('G2 不一致單 action：不自動套用、不出 rule 壓平欄位，只出權威草稿卡', async ({ page }) => {
  const captured = await installMocks(page)
  await gotoWorkbenchAndParse(page, '不一致：推治具到位')

  // 明確警示 + 權威草稿卡（CM）呈現
  await expect(page.getByTestId('nl-consistency-warning')).toBeVisible()
  await expect(page.locator('[data-testid^="ai-action-card-"]')).toHaveCount(1)
  await expect(page.getByTestId('ai-action-card-act-cm0').getByText('CM', { exact: true })).toBeVisible()

  // 不得自動套用（含 calculate debounce 窗口）：無草稿內容試算、編輯器仍空白 GM
  await page.waitForTimeout(700)
  expect(draftContentCalculated(captured.calcBodies)).toBe(false)
  await expect(page.getByLabel('動作類型')).toHaveValue('GM')
  await expect(page.getByText('已覆蓋填入 AI 建議')).toHaveCount(0)

  // rule 的壓平相容欄位（badge 列 + 建議 seq）會誤導 → 隱藏
  await expect(page.getByText('明確')).toHaveCount(0)
  await expect(page.getByText(/建議：/)).toHaveCount(0)
})

// ── G1：distance_cm=0 不得捏造成 30 ────────────────────────────────────────────
test('G1 採用 distance_cm=0 的 CM 草稿：編輯器送算距離必須是 0（TMU=24，非 30cm 的 16）', async ({ page }) => {
  const captured = await installMocks(page)
  await gotoWorkbenchAndParse(page, '不一致：推治具到位（沒講距離）')

  const cmCalc = page.waitForResponse(r =>
    r.url().endsWith('/api/v2/minimost/calculate') && r.request().method() === 'POST'
    && (JSON.parse(r.request().postData() ?? '{}') as { seq?: string }).seq === 'CM')
  await page.getByTestId('ai-action-card-act-cm0').getByRole('button', { name: '採用到編輯器' }).click()
  await cmCalc

  // 送後端試算的 payload：距離必須原封不動是 0（|| 會把 0 換成前端寫死的 30）
  const cmBodies = captured.calcBodies.filter(b => b.seq === 'CM')
  expect(cmBodies.length).toBeGreaterThan(0)
  const m3 = cmBodies[cmBodies.length - 1].m3 as { m_components: Array<{ distance_cm: number }> }
  expect(m3.m_components[0].distance_cm).toBe(0)
  // mock 依距離給值（0→24、30→16、45→29）：斷言才有鑑別力
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('24')
})

// ── G3a：viewer 不送 review 事件（403 必然）───────────────────────────────────
test('G3a viewer 採用草稿：不送 review 事件，採用本身不受影響', async ({ page }) => {
  const captured = await installMocks(page, { meLevel: 0 })
  await gotoWorkbenchAndParse(page, '從料架取得DIMM放至流水線，然後推治具到位')

  const gmCalc = page.waitForResponse(r =>
    r.url().endsWith('/api/v2/minimost/calculate') && r.request().method() === 'POST'
    && (JSON.parse(r.request().postData() ?? '{}') as { g2?: { g_code?: string } }).g2?.g_code === 'g_simple')
  await page.getByTestId('ai-action-card-act-1').getByRole('button', { name: '採用到編輯器' }).click()
  await gmCalc
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('28')
  await expect(page.getByTestId('ai-action-card-act-1').getByText('已採用（再載入）')).toBeVisible()

  // 角色 gating：viewer（level 0）完全不該打 reviews（打了就是必 403 的學習迴圈噪音）
  await page.waitForTimeout(400)
  expect(captured.reviewBodies.length).toBe(0)
})

// ── G3b：review 失敗 → 灰字提示，不吞錯、不阻斷 ────────────────────────────────
test('G3b review 事件 403：面板灰字提示學習迴圈缺漏，採用不受影響', async ({ page }) => {
  const captured = await installMocks(page, { reviewStatus: 403 })
  await gotoWorkbenchAndParse(page, '從料架取得DIMM放至流水線，然後推治具到位')

  await page.getByTestId('ai-action-card-act-1').getByRole('button', { name: '採用到編輯器' }).click()
  // 採用成功（非阻斷）
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('28')
  // 有送出（IE 身分）、且失敗不得靜默——面板灰字提示
  await expect.poll(() => captured.reviewBodies.length).toBe(1)
  await expect(page.getByTestId('nl-review-warning')).toBeVisible()
  await expect(page.getByTestId('nl-review-warning')).toContainText('review 事件記錄失敗')
})

// ── G4：編輯器有內容 → 採用草稿需覆蓋確認 ─────────────────────────────────────
test('G4 採用草稿覆蓋確認：取消＝編輯器不動，確認＝載入草稿', async ({ page }) => {
  const captured = await installMocks(page)
  await gotoWorkbenchAndParse(page, '從料架取得DIMM放至流水線，然後推治具到位')

  // 先採用第 1 筆（編輯器空白 → 不需確認）
  const gmCalc = page.waitForResponse(r =>
    r.url().endsWith('/api/v2/minimost/calculate') && r.request().method() === 'POST'
    && (JSON.parse(r.request().postData() ?? '{}') as { g2?: { g_code?: string } }).g2?.g_code === 'g_simple')
  await page.getByTestId('ai-action-card-act-1').getByRole('button', { name: '採用到編輯器' }).click()
  await gmCalc
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('28')

  // 編輯器已有內容 → 誤點卡 2：確認框「取消」→ 內容必須原封不動
  const dialogs: string[] = []
  page.once('dialog', d => { dialogs.push(d.message()); void d.dismiss() })
  await page.getByTestId('ai-action-card-act-2').getByRole('button', { name: '採用到編輯器' }).click()
  await page.waitForTimeout(700)   // 超過 calculate debounce，確定沒有 CM 試算發生
  expect(dialogs.length).toBe(1)
  expect(dialogs[0]).toContain('覆蓋')
  expect(captured.calcBodies.some(b => b.seq === 'CM')).toBe(false)
  await expect(page.getByLabel('動作類型')).toHaveValue('GM')
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('28')
  await expect(page.getByTestId('ai-action-card-act-2').getByText('已採用（再載入）')).toHaveCount(0)

  // 確認框「確定」→ 才覆蓋成 CM 草稿
  const cmCalc = page.waitForResponse(r =>
    r.url().endsWith('/api/v2/minimost/calculate') && r.request().method() === 'POST'
    && (JSON.parse(r.request().postData() ?? '{}') as { seq?: string }).seq === 'CM')
  page.once('dialog', d => { void d.accept() })
  await page.getByTestId('ai-action-card-act-2').getByRole('button', { name: '採用到編輯器' }).click()
  await cmCalc
  await expect(page.getByLabel('動作類型')).toHaveValue('CM')
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('29')
})

// ── G5：覆蓋/填空 modal 守門（test-engineer A5a）───────────────────────────────
test('G5a 編輯器有內容 → AI 預填出 modal；「只填空白」不覆蓋既有格位', async ({ page }) => {
  await installMocks(page)
  await gotoWorkbench(page)
  await fillGHeavy(page)   // 編輯器先有內容：G=重物抓握（34 TMU）

  await parseNl(page, '單動作：取得DIMM放至流水線')
  // 守門：編輯器有內容必須先問，不得直接覆蓋
  await expect(page.getByText('目前編輯區已有內容，AI 預填將如何處理？')).toBeVisible()
  await expect(page.getByText('已覆蓋填入 AI 建議')).toHaveCount(0)

  await page.getByRole('button', { name: '只填空白欄位' }).click()
  await expect(page.getByText('已填入空白欄位')).toBeVisible()
  // 既有 G（重物抓握）不得被 AI 的 g_simple 蓋掉；空白的 P 才被填入
  // （「簡單抓握」只允許出現在 NL 面板的建議列，不得進 G 格位）
  await expect(page.getByTestId('flow-item-G').locator('.font-bold')).toHaveText('重物抓握')
  await expect(page.getByTestId('flow-item-P').locator('.font-bold')).toHaveText('放置')
  await expect(page.getByTestId('flow-item-G').getByText('簡單抓握')).toHaveCount(0)
  // TMU 仍是 g_heavy 的 34（mock 依 g_code 鑑別）
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('34')
})

test('G5b 編輯器有內容 → modal 選「覆蓋」才覆蓋既有格位', async ({ page }) => {
  await installMocks(page)
  await gotoWorkbench(page)
  await fillGHeavy(page)

  await parseNl(page, '單動作：取得DIMM放至流水線')
  await expect(page.getByText('目前編輯區已有內容，AI 預填將如何處理？')).toBeVisible()

  await page.getByRole('button', { name: '覆蓋目前欄位' }).click()
  await expect(page.getByText('已覆蓋填入 AI 建議')).toBeVisible()
  await expect(page.getByTestId('flow-item-G').locator('.font-bold')).toHaveText('簡單抓握')
  await expect(page.getByTestId('summary-base-tmu')).toHaveText('28')
})

// ── G6：keepNl 不因無 cycle 草稿而讓面板永不收 ─────────────────────────────────
test('G6 多 action 含無 cycle 草稿：可採用的都入庫後，存檔即收 NL 面板', async ({ page }) => {
  await installMocks(page)
  await gotoWorkbenchAndParse(page, '含無法拆解：取得DIMM放至流水線＋一段拆不開的描述')

  await expect(page.locator('[data-testid^="ai-action-card-"]')).toHaveCount(2)
  // 無 cycle 的草稿不可採用（按鈕 disabled）
  await expect(page.getByTestId('ai-action-card-act-2').getByRole('button', { name: '採用到編輯器' })).toBeDisabled()

  // 採用唯一可採用的 act-1 → 存檔
  const gmCalc = page.waitForResponse(r =>
    r.url().endsWith('/api/v2/minimost/calculate') && r.request().method() === 'POST'
    && (JSON.parse(r.request().postData() ?? '{}') as { g2?: { g_code?: string } }).g2?.g_code === 'g_simple')
  await page.getByTestId('ai-action-card-act-1').getByRole('button', { name: '採用到編輯器' }).click()
  await gmCalc
  const published = page.waitForResponse(r =>
    /\/motion-modules\/[^/]+\/publish$/.test(new URL(r.url()).pathname) && r.status() === 201)
  await page.getByRole('button', { name: '新增動作' }).click()
  await published
  await expect(page.getByText(/已新增動作：/)).toBeVisible()

  // 剩下的只有「永遠採用不了」的草稿 → 面板必須自動收（否則永不收）
  await expect(page.getByTestId('nl-result-panel')).toHaveCount(0)
})
