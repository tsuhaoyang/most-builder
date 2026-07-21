import { test, expect } from '@playwright/test'
/** D8 真 API 動線：對真實 draft 看 diff；teardown 用 DELETE。 */
test('D8-real: clone → 檢視差異(真 diff) → 發布框含差異 → DELETE teardown', async ({ page, request }) => {
  const H = { 'X-Username': 'IEC141289' }
  // 建立測試草稿
  const clone = await (await request.post('/api/v2/rule-sets/MINIMOST_FACTORY_V2/clone-draft', {
    headers: H, data: {},
  })).json() as { code: string }
  const draft = clone.code

  try {
    await page.goto('/'); await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: /MOST 字典/ }).first().click()
    await page.waitForLoadState('networkidle')

    // 獨立檢視差異。剛 clone 的草稿：子表值全同，但 clone 會在 name_zh 後綴「 (草稿)」
    // → 後端回 identical:false、僅 header_changed=['name_zh']、區塊 0 筆。
    await page.getByTestId(`dict-version-${draft}`).getByRole('button', { name: '檢視差異' }).click()
    const panel = page.getByTestId('dict-diff-panel')
    await expect(panel).toBeVisible()
    const sum = panel.getByTestId('diff-summary')
    await expect(sum).toBeVisible()
    await expect(sum.getByText(/版本表頭：版本名稱/)).toBeVisible()
    // 值沒有變（新增/刪除/變更皆 0）
    await expect(sum.getByText('0').first()).toBeVisible()
    // 基準必須標明
    await expect(panel.getByText(/比較基準/)).toBeVisible()
    await expect(panel.getByText('MINIMOST_FACTORY_V2', { exact: true }).first()).toBeVisible()
    // 真後端有 clone 紀錄且 base 就是來源 → 不該出現血緣警示，也不該說「無法判斷」
    await expect(panel.getByTestId('diff-lineage-warning')).toHaveCount(0)
    await expect(panel.getByTestId('diff-lineage-unknown')).toHaveCount(0)
    await panel.getByRole('button', { name: '關閉' }).last().click()

    // 發布確認框內嵌真差異，且確認鈕可按（差異已取得）
    await page.getByTestId(`dict-version-${draft}`).getByRole('button', { name: '發布' }).click()
    const dlg = page.getByTestId('dict-confirm-dialog')
    await expect(dlg.getByText(/比較基準/)).toBeVisible()
    await expect(dlg.getByRole('button', { name: '確認發布' })).toBeEnabled()
    await dlg.getByRole('button', { name: '取消' }).click()
  } finally {
    // teardown：D3b 的 DELETE 端點
    const del = await request.delete(`/api/v2/rule-sets/${draft}`, { headers: H })
    expect(del.status()).toBe(200)
  }
})
