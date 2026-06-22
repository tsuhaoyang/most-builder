import { test, expect } from '@playwright/test'

test('workbench loads and shows WI tab', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: /WI 工時表/ })).toBeVisible()
})
