/**
 * F8 / §8.3(6)：plainDiag 診斷碼覆蓋。驗證 levelSystem.plain 兩語系逐碼對稱（34 碼），
 * 且 plainDiag 對每碼都能產出使用者語言句（HIDDEN_W 5 碼刻意為空字串 → fall back message）。
 * 純 node（直接 import src/），不需伺服器。
 */
import { test, expect } from '@playwright/test'
import zhTW from '../src/shared/i18n/resources/zh-TW'
import en from '../src/shared/i18n/resources/en'
import { plainDiag, HIDDEN_W } from '../src/features/level-system/notices'
import type { LbReportDiag } from '../src/features/level-system/api'

type Plain = Record<string, string>
const zhPlain = (zhTW as unknown as { levelSystem: { plain: Plain } }).levelSystem.plain
const enPlain = (en as unknown as { levelSystem: { plain: Plain } }).levelSystem.plain

test('levelSystem.plain: zh-TW 與 en 逐碼對稱（含 34 碼）', () => {
  const zhKeys = Object.keys(zhPlain).sort()
  const enKeys = Object.keys(enPlain).sort()
  expect(zhKeys).toEqual(enKeys)
  expect(zhKeys.length).toBeGreaterThanOrEqual(34)
})

test('plainDiag: 每碼可產句；HIDDEN_W 5 碼為空 → fall back message', () => {
  // 用 zh-TW 的 plain 當 t()
  const t = (key: string, opts?: Record<string, unknown>): string => {
    const short = key.replace(/^levelSystem\.plain\./, '')
    let s = zhPlain[short]
    if (s === undefined) return key   // 缺 key → i18next 回 key 本身（plainDiag 會 fall back）
    // 極簡插值：{{step}} {{tool}} {{freq}} {{message}}
    for (const [k, v] of Object.entries(opts ?? {})) s = s.replace(new RegExp(`{{${k}}}`, 'g'), String(v))
    return s
  }
  const stepOf = (id: string) => `第 ${id} 步`

  for (const code of Object.keys(zhPlain)) {
    const d: LbReportDiag = { code, message: `原始訊息 ${code}`, wi_row_id: 'r1', params: { tool_id: 'electric_driver', freq: 8 } } as LbReportDiag
    const out = plainDiag(t, d, stepOf)
    expect(out, `code ${code} 應有非空輸出`).toBeTruthy()
    if ((HIDDEN_W as readonly string[]).includes(code)) {
      // HIDDEN_W：plain 為空字串 → plainDiag fall back 到 message
      expect(zhPlain[code], `${code} 應為空字串（隱藏）`).toBe('')
      expect(out).toBe(d.message)
    } else {
      // 非隱藏：應由 plain 模板產句，不等於 key 本身
      expect(out).not.toBe('levelSystem.plain.' + code)
    }
  }
})
