// 錯誤 catalog 對照層（ADR-034 §D5 階段 C / C1）。
//
// 單一入口：把後端 `{error:{code,message,detail}}` 信封轉成使用者語言的顯示句。
// 契約來源是 `code`（穩定、機器可讀，ADR-034 I3），顯示語言由前端 i18next locale
// 決定（ADR-034 D2：在地化發生在前端，後端 message 只是 fallback）。
//
// 查 key 的順序（ADR-034 D4 命名規範）：
//   1. `errors.<CODE>.<resource>`（detail 帶 resource 時；如 NOT_FOUND.rule_set）
//   2. `errors.<CODE>`（無 resource 時；如 CONFLICT / RATE_LIMITED）
//   3. graceful fallback → 後端 `error.message`（ADR-034 I4：可接受降級。
//      **絕不**在 en locale 把中文 message 當英文——fallback 就是顯示後端
//      預設語言 message 原文，不做偽翻譯）。
//
// 插值一律用 detail 的結構化參數（{{rule_set_code}} / {{id}} / {{action}} 等），
// 走 i18next 預設 {{param}} 插值（本專案未裝 ICU 外掛）。
//
// KI-034-1 收斂方向：本層**只讀 error 信封**（`d.error.code` / `d.error.detail`），
// 不依賴頂層 `d.detail`（那是選項 Y 保留的過渡相容欄位，前端不讀）。ApiError 的
// `detail` 欄位在 client.ts 已被 `toError` 正規化為 `d?.error ?? d?.detail`，即 error
// 物件 `{code, message, detail}`。**注意巢狀**：機器碼 `code` 在 error 頂層，但結構化
// 插值參數（resource / rule_set_code / action …）住在 `error.detail.*`（見 extractEnvelope）。

import type { i18n as I18nInstance, TFunction } from 'i18next'
import { ApiError } from '../api/client'
import i18nDefault from './i18n'

/** i18next 查得到 key 時回 true；查不到會回傳 key 本身（returnNull:false）。 */
function hasKey(i18n: I18nInstance, key: string): boolean {
  return i18n.exists(key)
}

/**
 * 從任意 error 取出 code（機器碼）與插值參數（結構化 detail）。
 *
 * 後端線上信封（error_handlers.py::_envelope）實際巢狀形狀：
 *   { error: { code, message, detail: { code, resource, rule_set_code, action, ... } },
 *     detail: "…（選項 Y 頂層相容字串）" }
 * client.ts::toError 把 `ApiError.detail = d?.error ?? d?.detail`，因此對 DomainError
 * 信封而言 `ApiError.detail` = 上面的 `error` 物件：`{ code, message, detail:{結構化參數} }`。
 *
 * 關鍵（見 review_stage_c 迴修）：**code 與 params 住在不同巢狀層**——
 *   - `code` 在 `error` 頂層（`o.code`）。
 *   - 結構化插值參數（resource / rule_set_code / run_id / worksheet_id / module_id /
 *     action / field / id 等）在 `error.detail.*`（`o.detail`），**不在** `error` 頂層。
 * 故 params 必須取 `o.detail`（若為物件）；否則退回扁平 `o`（相容舊式
 * `{code, resource, …}` 扁平信封或非標準結構）。
 */
function extractEnvelope(err: unknown): { code: string | null; detail: Record<string, unknown> } {
  if (err instanceof ApiError) {
    const d = err.detail
    if (d && typeof d === 'object') {
      const o = d as Record<string, unknown>
      const code = typeof o.code === 'string' ? o.code : null
      // params 來源：巢狀 `error.detail`（新信封結構化參數所在）；缺物件時退回扁平 o。
      const inner =
        o.detail && typeof o.detail === 'object'
          ? (o.detail as Record<string, unknown>)
          : o
      return { code, detail: inner }
    }
    return { code: null, detail: {} }
  }
  // 非 ApiError：無結構化 code，交給 fallback。
  return { code: null, detail: {} }
}

/** 後端預設語言 message（fallback 用）：不做翻譯，原文顯示（ADR-034 I4）。 */
function backendMessage(err: unknown): string {
  if (err instanceof ApiError) return err.humanMessage
  if (err instanceof Error) return err.message
  return String(err)
}

/**
 * 把 error 信封解析成當前 locale 的顯示訊息（ADR-034 §C1 單一入口）。
 *
 * @param err  ApiError 或任意 unknown（fetch 例外、Error 等）
 * @param i18nOrT  可傳 i18n 實例或 t 函式；省略時用預設 i18n 單例。
 *                 傳 useTranslation() 的 t（其 i18n 綁定當前 locale）可確保
 *                 locale-reactive（ADR-034 §C3：不直讀 localStorage）。
 */
export function resolveErrorMessage(err: unknown, i18nOrT?: I18nInstance | TFunction): string {
  // 取得 i18n 實例：傳入 t 函式時其上掛有 .i18n；傳 i18n 實例時直接用；否則預設單例。
  const i18n: I18nInstance = resolveI18n(i18nOrT)

  const { code, detail } = extractEnvelope(err)
  if (!code) return backendMessage(err)

  // detail 的結構化參數即插值來源（resource / 自然鍵 / action 等）。
  const params = detail as Record<string, unknown>
  const resource = typeof params.resource === 'string' ? params.resource : null

  // 1) errors.<CODE>.<resource>（如 NOT_FOUND.rule_set / FORBIDDEN.module）
  if (resource) {
    const scoped = `errors.${code}.${resource}`
    if (hasKey(i18n, scoped)) return i18n.t(scoped, params) as string
  }
  // 2a) errors.<CODE>.default（resource 缺漏或無對應 key，但該 code 是 resource-scoped 群組）
  const scopedDefault = `errors.${code}.default`
  if (hasKey(i18n, scopedDefault)) return i18n.t(scopedDefault, params) as string
  // 2b) errors.<CODE>（純字串 key，如 CONFLICT 以外的 RATE_LIMITED / SIMO_PAIR_INVALID 等）
  const bare = `errors.${code}`
  if (hasKey(i18n, bare)) {
    const val = i18n.t(bare, params)
    // 防呆：若該 key 其實是物件（resource 群組但無 default），t 會回傳非字串 →
    // 不可把 "[object Object]" 丟給使用者，改走 fallback。
    if (typeof val === 'string') return val
  }

  // 3) graceful fallback → 後端預設語言 message（不偽翻譯，ADR-034 I4）。
  return backendMessage(err)
}

function resolveI18n(i18nOrT?: I18nInstance | TFunction): I18nInstance {
  if (!i18nOrT) return i18nDefault
  // t 函式：react-i18next 的 t 上掛有 `.i18n`（綁定當前 locale）。
  const maybeT = i18nOrT as TFunction & { i18n?: I18nInstance }
  if (typeof maybeT === 'function' && maybeT.i18n) return maybeT.i18n
  // 已是 i18n 實例。
  return i18nOrT as I18nInstance
}

export default resolveErrorMessage
