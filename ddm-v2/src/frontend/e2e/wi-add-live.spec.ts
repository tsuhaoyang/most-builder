import { test, expect } from '@playwright/test'

test('WI 專案建立：勾選 WI 後按加入會寫入已選清單（live）', async ({ page, request }) => {
  const authHeader = { 'X-Username': 'IEC141289' }
  const projectCode = `PW-ADD-${Date.now()}`
  const projectName = `PW Add Live ${Date.now()}`

  const createProject = await request.post('/api/v2/wi-set-projects', {
    headers: authHeader,
    data: {
      project_code: projectCode,
      name: projectName,
      site: 'TAO',
      bu: 'BU1',
      process: 'L10_ASSY',
      family: 'E2E',
      model: 'ADD',
      description: 'Playwright live add flow',
    },
  })
  expect(createProject.status()).toBe(201)
  const created = (await createProject.json()) as { id: string }
  const projectId = created.id

  try {
    await page.goto('/')
    await page.getByRole('button', { name: /WI 專案建立/ }).click()
    await page.waitForLoadState('networkidle')

    await page.locator('select').first().selectOption(projectId)
    await page.waitForLoadState('networkidle')

    const poolSection = page.getByRole('heading', { name: 'B — WI 庫搜尋' }).locator('..')
    const poolRows = poolSection.locator('tbody tr').filter({ has: page.locator('td') })
    await expect(poolRows.first()).toBeVisible()

    const firstRow = poolRows.first()
    const rowCheckbox = firstRow.locator('input[type="checkbox"]').first()
    await rowCheckbox.check()

    const addButton = page.getByRole('button', { name: /加入 WI Set/ })
    await expect(addButton).toBeEnabled()

    const addItemResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST'
        && /\/api\/v2\/wi-set-projects\/[^/]+\/items$/.test(url.pathname)
    }, { timeout: 15000 })

    await addButton.click()
    const response = await addItemResponse
    expect(response.status()).toBe(201)

    await expect(page.getByText(/已加入\s+1\s+筆 WI/)).toBeVisible({ timeout: 15000 })

    const selectedSection = page.getByRole('heading', { name: 'C — 已選 WI 清單' }).locator('..')
    const selectedRows = selectedSection.locator('tbody tr')
    await expect(selectedRows.first()).toBeVisible({ timeout: 15000 })
    await expect(selectedSection.getByText('已選 1 筆')).toBeVisible({ timeout: 15000 })
  } finally {
    await request.delete(`/api/v2/wi-set-projects/${projectId}`, { headers: authHeader })
  }
})

test('WI 專案建立：既有專案勾選 WI 後按加入會送出 API（live）', async ({ page, request }) => {
  const authHeader = { 'X-Username': 'IEC141289' }

  const projectsRes = await request.get('/api/v2/wi-set-projects', { headers: authHeader })
  expect(projectsRes.status()).toBe(200)
  const projects = (await projectsRes.json()) as Array<{ id: string }>
  expect(projects.length).toBeGreaterThan(0)
  const projectId = projects[0].id

  const templatesRes = await request.get('/api/v2/motion-modules?category=wi-template', { headers: authHeader })
  expect(templatesRes.status()).toBe(200)
  const templates = (await templatesRes.json()) as Array<{ id: string }>
  expect(templates.length).toBeGreaterThan(0)

  await page.goto('/')
  await page.getByRole('button', { name: /WI 專案建立/ }).click()
  await page.waitForLoadState('networkidle')

  await page.locator('select').first().selectOption(projectId)
  await page.waitForLoadState('networkidle')

  const poolSection = page.getByRole('heading', { name: 'B — WI 庫搜尋' }).locator('..')
  const firstRow = poolSection.locator('tbody tr').first()
  const rowCheckbox = firstRow.locator('input[type="checkbox"]').first()
  await rowCheckbox.check()

  const addButton = page.getByRole('button', { name: /加入 WI Set/ })
  await expect(addButton).toBeEnabled()

  const addItemResponse = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return response.request().method() === 'POST'
      && /\/api\/v2\/wi-set-projects\/[^/]+\/items$/.test(url.pathname)
  }, { timeout: 15000 })

  await addButton.click()
  const response = await addItemResponse
  expect(response.status()).toBe(201)

  const createdItem = (await response.json()) as { id: string; project_id: string }
  expect(createdItem.project_id).toBe(projectId)

  await request.delete(`/api/v2/wi-set-projects/${projectId}/items/${createdItem.id}`, {
    headers: authHeader,
  })
})
