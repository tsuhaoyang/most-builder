/**
 * WI 專案建立（F-04）— 「勾選 WI → 加入 WI Set」流程（真實 API + 真實 DB，經 preview_server）
 *
 * ⚠️ 本檔的前身是 `wi-add-live.spec.ts`，它直接撈「DB 裡既有的第一個 wi-set project
 *    ／第一個 category='wi-template' 模組」當輸入。那在 CI 是**結構上不可能過**的：
 *      - CI e2e job 的 seed 只有 dev_seed_v2 / dev_seed_templates / dev_seed_30rows，
 *        三支都不建 wi-set project，也不建 category='wi-template' 的 motion module
 *        （dev_seed_templates 種的是 motion_templates 範本表，不是 motion_modules）。
 *      - 唯一會建這兩種資料的是 scripts/migrate_v3_user_data.py，而它讀的是
 *        gitignored 的 ddm-v3/apps/api/minimost.db —— CI 拿不到。
 *    開發機之所以綠，只是因為有人跑過那支遷移。
 *
 * 所以本檔改成**自建 fixture**：測試自己經 API 建立它需要的最小資料（一個 WI 專案
 * ＋已發布的 wi-template 模組），跑完再刪掉。這樣它在乾淨 DB（CI）與已有資料的
 * 開發機上都成立，且失敗時一定是產品壞了，而不是環境沒種資料。
 * 與後端 test_delete_referenced_draft_returns_409_* 上一批的處置同一原則。
 */
import { test, expect, type APIRequestContext, type APIResponse, type Page } from '@playwright/test'

const AUTH = { 'X-Username': 'IEC141289' }

/**
 * 一組合法七格（GM A10 B0 G6 A16 B0 P6 A0）。
 * 這裡**不寫死 TMU 期望值**：TMU 一律由後端 most_engine 於 publish 時算出，
 * 測試從 publish 回應讀回來當作 UI 顯示的比對基準（DISC-02/07：前端不自算）。
 */
const GM_CYCLE = {
  seq: 'GM',
  rule_set_code: 'MINIMOST_FACTORY_V2',
  a0: { reach_cm: 30 },
  g2: { g_code: 'g_grasp' },
  a3: { reach_cm: 40 },
  p5: { p_base_code: 'p_place_none' },
  a6: { reach_cm: 0 },
}

interface WiTemplateFixture {
  id: string
  name: string
  /** 後端 publish 回傳的版本合計 TMU（UI 應原樣顯示） */
  totalTmu: number
  /** 該版本的動作列數（UI 的「動作數」欄） */
  actionCount: number
}

function uniq(): string {
  return `${Date.now()}${Math.random().toString(36).slice(2, 7)}`
}

/**
 * 本測試建出來、跑完必須刪掉的資源。
 *
 * ⚠️ 登記時機是重點：**資源一產生就登記**，不要等整個 fixture 函式回傳。
 *    原本 fixture 是在 `try` 外面建的，只要 POST 成功「之後」任何一步拋
 *    （publish 非 201、第二個 WI 建失敗），`finally` 就跑不到／看不到那筆，
 *    模組會永遠留在 DB —— 正是本檔重寫要關掉的那類漏洞。
 */
interface Trash {
  projects: string[]
  modules: string[]
}

/** 建立並發布一個 category='wi-template' 模組（WI 庫看得到、可加入 WI Set 的最小形狀）。 */
async function createPublishedWiTemplate(
  request: APIRequestContext,
  name: string,
  trash: Trash,
): Promise<WiTemplateFixture> {
  const created = await request.post('/api/v2/motion-modules', {
    headers: AUTH,
    data: { name_zh: name, category: 'wi-template', scope: 'personal' },
  })
  expect(created.status(), await created.text()).toBe(201)
  const id = ((await created.json()) as { id: string }).id
  trash.modules.push(id) // ← 緊接在「模組已存在於 DB」之後，publish 之前

  const published = await request.post(`/api/v2/motion-modules/${id}/publish`, {
    headers: AUTH,
    data: {
      rule_set_code: 'MINIMOST_FACTORY_V2',
      rows: [{ hand: 'RH', frequency: 1, vocab_refs: {}, cycle: GM_CYCLE }],
    },
  })
  expect(published.status(), await published.text()).toBe(201)
  const version = (await published.json()) as { total_tmu: number | string; rows: unknown[] }

  return { id, name, totalTmu: Number(version.total_tmu), actionCount: version.rows.length }
}

async function createProject(
  request: APIRequestContext,
  tag: string,
  trash: Trash,
): Promise<string> {
  const res = await request.post('/api/v2/wi-set-projects', {
    headers: AUTH,
    data: {
      project_code: `PW-${tag}`,
      name: `PW WI Set ${tag}`,
      site: 'TAO',
      bu: 'BU1',
      process: 'L10_ASSY',
      family: 'E2E',
      model: 'ADD',
      description: 'Playwright WI set add flow',
    },
  })
  expect(res.status(), await res.text()).toBe(201)
  const id = ((await res.json()) as { id: string }).id
  trash.projects.push(id)
  return id
}

/**
 * 刪除必須成功，而且**要驗**。
 *
 * 今天 publish_version 留 `status='draft'`，所以 delete_module 回 204；哪天 publish 改成
 * 設 `status='standard'`，delete_module 就會擋成 409（ModuleIsStandard）——若這裡照舊
 * 忽略狀態碼，清理會**靜默失效**，每次 CI 都多漏一筆殘留資料而沒人看得見。
 *
 * 用 `expect.soft`：cleanup 跑在 `finally`，硬斷言一拋就會蓋掉測試本體真正的失敗原因；
 * soft 失敗一樣會讓測試紅，但不吃掉原始錯誤。
 */
function expectDeleted(res: APIResponse, what: string): void {
  expect
    .soft([204, 404], `清理未生效（${what}）：HTTP ${res.status()}`)
    .toContain(res.status())
}

async function cleanup(request: APIRequestContext, trash: Trash): Promise<void> {
  // 專案先刪（items 由 FK CASCADE 帶走），再刪模組。
  for (const id of trash.projects) {
    const res = await request.delete(`/api/v2/wi-set-projects/${id}`, { headers: AUTH })
    expectDeleted(res, `wi-set project ${id}`)
  }
  for (const id of trash.modules) {
    const res = await request.delete(`/api/v2/motion-modules/${id}`, { headers: AUTH })
    expectDeleted(res, `motion module ${id}`)
  }
}

/** 開到「WI 專案建立」頁並選定專案。 */
async function openProject(page: Page, projectId: string): Promise<void> {
  await page.goto('/')
  await page.getByRole('button', { name: /WI 專案建立/ }).click()
  await page.waitForLoadState('networkidle')
  await page.getByLabel('選擇現有專案').selectOption(projectId)
  await page.waitForLoadState('networkidle')
}

const poolSection = (page: Page) =>
  page.getByRole('heading', { name: 'B — WI 庫搜尋' }).locator('..')
const selectedSection = (page: Page) =>
  page.getByRole('heading', { name: 'C — 已選 WI 清單' }).locator('..')

/**
 * 在 B 區用唯一名稱搜出自己建的那一列並勾選。
 * 用搜尋而非 `tbody tr` 的第一列：後者在開發機（庫裡有既有 WI）會勾到別人的資料，
 * 在空庫時還會勾到「尚無 WI 模組」那一列的空狀態 <tr>。
 */
async function selectPoolRow(page: Page, wi: WiTemplateFixture) {
  const pool = poolSection(page)
  await pool.getByPlaceholder('輸入關鍵字搜尋 WI 名稱…').fill(wi.name)
  const row = pool.locator('tbody tr').filter({ hasText: wi.name })
  await expect(row).toHaveCount(1)
  // 庫列的 TMU/動作數來自後端摘要欄，UI 只負責顯示（DISC-02/07）
  await expect(row).toContainText(wi.totalTmu.toFixed(1))
  await row.locator('input[type="checkbox"]').check()
  return row
}

function waitForAddItem(page: Page) {
  return page.waitForResponse(
    (response) => {
      const url = new URL(response.url())
      return (
        response.request().method() === 'POST' &&
        /\/api\/v2\/wi-set-projects\/[^/]+\/items$/.test(url.pathname)
      )
    },
    { timeout: 15000 },
  )
}

interface WiSetItemOut {
  id: string
  project_id: string
  seq_no: number
  wi_template_id: string | null
  wi_name_snapshot: string
  action_count_snapshot: number
  total_tmu_snapshot: number
}

test('WI 專案建立：勾選 WI 後按加入 → POST items 201，伺服器快照寫回已選清單', async ({
  page,
  request,
}) => {
  const tag = uniq()
  const trash: Trash = { projects: [], modules: [] }

  try {
    const wi = await createPublishedWiTemplate(request, `PW-WI-${tag}`, trash)
    const projectId = await createProject(request, `ADD-${tag}`, trash)
    await openProject(page, projectId)
    await selectPoolRow(page, wi)

    const addButton = page.getByRole('button', { name: /加入 WI Set/ })
    await expect(addButton).toBeEnabled()

    const addItemResponse = waitForAddItem(page)
    await addButton.click()
    const response = await addItemResponse
    expect(response.status()).toBe(201)

    // 快照一律由伺服器從 motion module 解析回填（F-02a 值權威；前端不得自算快照）
    const item = (await response.json()) as WiSetItemOut
    expect(item.project_id).toBe(projectId)
    expect(item.wi_template_id).toBe(wi.id)
    expect(item.seq_no).toBe(1)
    expect(item.wi_name_snapshot).toBe(wi.name)
    expect(item.total_tmu_snapshot).toBe(wi.totalTmu)
    expect(item.action_count_snapshot).toBe(wi.actionCount)

    // flash 3 秒自動消失，先驗它再驗清單
    await expect(page.getByText(/已加入\s+1\s+筆 WI/)).toBeVisible()

    const selected = selectedSection(page)
    await expect(selected.getByText('已選 1 筆')).toBeVisible({ timeout: 15000 })
    const selectedRow = selected.locator('tbody tr').filter({ hasText: wi.name })
    await expect(selectedRow).toHaveCount(1)
    await expect(selectedRow).toContainText(wi.totalTmu.toFixed(1))
    // 「動作數」欄＝第 5 個 td（☑｜⠿#｜WI Code｜WI 名稱｜**動作數**｜TMU｜CT(秒)｜備註｜操作）。
    // 不能寫 `toContainText(String(wi.actionCount))`：actionCount 是 1，而列首渲染「⠿1」
    // 本來就含 '1' → 那是恆真斷言。要釘就釘那一格的完整文字。
    await expect(selectedRow.locator('td').nth(4)).toHaveText(String(wi.actionCount))
  } finally {
    await cleanup(request, trash)
  }
})

test('WI 專案建立：對已有條目的專案再加入 → 追加在後（seq_no 遞增、C 區維持順序）', async ({
  page,
  request,
}) => {
  const tag = uniq()
  const trash: Trash = { projects: [], modules: [] }

  try {
    // 兩個 WI 都在 try 內建：wiA 成功、wiB 失敗時，wiA 仍會被 finally 清掉
    const wiA = await createPublishedWiTemplate(request, `PW-WIA-${tag}`, trash)
    const wiB = await createPublishedWiTemplate(request, `PW-WIB-${tag}`, trash)
    const projectId = await createProject(request, `SEQ-${tag}`, trash)

    // 先經 API 放進第一筆，讓 UI 面對的是「已經有條目的既有專案」
    const first = await request.post(`/api/v2/wi-set-projects/${projectId}/items`, {
      headers: AUTH,
      data: { wi_template_id: wiA.id },
    })
    expect(first.status(), await first.text()).toBe(201)
    expect(((await first.json()) as WiSetItemOut).seq_no).toBe(1)

    await openProject(page, projectId)
    const selected = selectedSection(page)
    await expect(selected.getByText('已選 1 筆')).toBeVisible()

    await selectPoolRow(page, wiB)
    const addItemResponse = waitForAddItem(page)
    await page.getByRole('button', { name: /加入 WI Set/ }).click()
    const response = await addItemResponse
    expect(response.status()).toBe(201)

    // 後端 max(seq_no)+1 → 第二筆必須是 2，不能覆蓋或插隊
    const item = (await response.json()) as WiSetItemOut
    expect(item.seq_no).toBe(2)
    expect(item.wi_template_id).toBe(wiB.id)

    await expect(selected.getByText('已選 2 筆')).toBeVisible({ timeout: 15000 })
    const rows = selected.locator('tbody tr')
    await expect(rows).toHaveCount(2)
    // C 區依 seq_no 排序：先加入的在上
    await expect(rows.nth(0)).toContainText(wiA.name)
    await expect(rows.nth(1)).toContainText(wiB.name)
  } finally {
    await cleanup(request, trash)
  }
})
