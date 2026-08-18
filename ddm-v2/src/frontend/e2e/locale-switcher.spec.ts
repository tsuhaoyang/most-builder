import { test, expect } from '@playwright/test'

// ADR-032 Phase A：語言切換 UI（D3.4，AppLayout 標頭右側）。
//
// 只攔截 PATCH /api/v2/me/locale——GET /me 打真實後端（回真實 IEC141289 使用者，
// locale 目前是 zh-TW，與其他既有 e2e 假設一致）。攔截 PATCH 是刻意的：這支測試
// 若真的把 PATCH 送進共用的開發 DB，會把 IEC141289 的 locale 永久改成 en，
// 讓所有「假設預設 zh-TW」的既有 e2e（11 個 spec 之一）在下一次執行時變成
// 語言狀態不可預期的紅燈——這正是 ADR-032 風險段點名的失效模式。
test('locale switcher toggles UI language and persists via PATCH /me/locale', async ({ page }) => {
  let patchedBody: unknown = null

  await page.route('**/api/v2/me/locale', route => {
    const body = JSON.parse(route.request().postData() ?? '{}') as { locale?: string }
    patchedBody = body
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ employee_no: 'IEC141289', roles: ['admin'], plant_code: null, level: 3, locale: body.locale }),
    })
  })

  await page.goto('/')

  // 預設 zh-TW（DEFAULT_LOCALE；localStorage 未快取，/me 尚未回來前也是這個值）
  await expect(page.getByRole('button', { name: '儀表板' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'MOST 工作台' })).toBeVisible()

  // 用 data-testid 而非 aria-label 定位：aria-label 本身也是 i18n key
  // （切換後會變成 "Switch language"），用會變的字串定位容器是自我矛盾。
  const switcher = page.getByTestId('locale-switcher')
  await expect(switcher).toBeVisible()
  const enButton = switcher.getByRole('button', { name: 'EN' })
  const zhButton = switcher.getByRole('button', { name: '中文' })
  await expect(zhButton).toHaveAttribute('aria-pressed', 'true')
  await expect(enButton).toHaveAttribute('aria-pressed', 'false')

  // 首屏 <html lang> 也是 zh-TW（複審修復項 2：全 repo 原本沒有任何地方寫這個屬性）
  await expect.poll(() => page.evaluate(() => document.documentElement.lang)).toBe('zh-TW')

  await enButton.click()

  // 外殼字串即時切換（不需等 PATCH 回應——client 端立即 i18n.changeLanguage）。
  // getByRole name 是子字串比對（同既有 spec 對「儀表板」的用法）：nav 按鈕的可及名稱
  // 是 shortLabel + label 的串接（如 "MWorkbench"），所以斷言子字串即可，不用 exact。
  await expect(page.getByRole('button', { name: 'Dashboard' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Workbench' })).toBeVisible()
  // 頭部品牌標題不隨語言變（沿用既有中文介面行為——MOST Workbench 是產品名，不是外殼字串）
  await expect(page.getByRole('heading', { name: 'MOST Workbench' })).toBeVisible()
  await expect(enButton).toHaveAttribute('aria-pressed', 'true')
  await expect(zhButton).toHaveAttribute('aria-pressed', 'false')

  // 送出的偏好真的是 en（PATCH /me/locale 契約）
  await expect.poll(() => patchedBody).toEqual({ locale: 'en' })

  // localStorage 快取寫回（D3.2 首屏快取）
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ddm_v2.locale'))).toBe('en')

  // <html lang> 跟著切換（複審修復項 2）
  await expect.poll(() => page.evaluate(() => document.documentElement.lang)).toBe('en')

  // 切回中文：外殼字串復原
  await zhButton.click()
  await expect(page.getByRole('button', { name: '儀表板' })).toBeVisible()
  await expect.poll(() => patchedBody).toEqual({ locale: 'zh-TW' })
  await expect.poll(() => page.evaluate(() => document.documentElement.lang)).toBe('zh-TW')
})

// 複審修復項 1：PATCH /me/locale 失敗必須回滾＋出聲，不能悄悄留在切換後的畫面，
// 也不能讓 localStorage 停在「伺服器沒有真的記住」的值（否則下次開頁 `/me` 回舊值時，
// `useLocaleSync` 會無聲把畫面與 localStorage 都改回去，使用者看不到任何線索）。
test('failed PATCH /me/locale rolls back the UI and shows a visible error', async ({ page }) => {
  await page.route('**/api/v2/me/locale', route =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'locale update failed (mock)' }),
    }),
  )

  await page.goto('/')
  await expect(page.getByRole('button', { name: '儀表板' })).toBeVisible()

  const switcher = page.getByTestId('locale-switcher')
  const enButton = switcher.getByRole('button', { name: 'EN' })
  const zhButton = switcher.getByRole('button', { name: '中文' })

  await enButton.click()

  // 失敗後必須回滾回中文——不是停在切換當下的英文
  await expect(page.getByRole('button', { name: '儀表板' })).toBeVisible()
  await expect(zhButton).toHaveAttribute('aria-pressed', 'true')
  await expect(enButton).toHaveAttribute('aria-pressed', 'false')

  // localStorage 與 <html lang> 都回滾，不留下「伺服器沒記住」的殘留值
  await expect.poll(() => page.evaluate(() => localStorage.getItem('ddm_v2.locale'))).toBe('zh-TW')
  await expect.poll(() => page.evaluate(() => document.documentElement.lang)).toBe('zh-TW')

  // 失敗必須可見（不是無聲）
  await expect(page.getByTestId('locale-switcher-error')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('語言偏好更新失敗')
})
