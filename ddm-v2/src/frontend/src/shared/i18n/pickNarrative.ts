import type { i18n as I18nType } from 'i18next'

/**
 * 依 locale 選敘述欄（ADR-032）。**不翻譯、不合併、不猜測**：
 *   - `en`：回 `narrative_en`（後端以該版本 pin 的 rule-set 即時產生，語言中立 API）。
 *     英文欄缺值（null/undefined/空白）→ 回 `fallback`（呼叫端多傳 `sub_activity`）或 `null`。
 *     **絕不把中文 `narrative_zh` 當英文顯示。**
 *   - `zh-TW`（及其他）：回 `narrative_zh`，缺值 → `fallback` 或 `null`。
 *
 * 判斷方式比照 `wi-workbench/useRowNarr.ts`：`resolvedLanguage === 'en' || language === 'en'`
 * （reactive；呼叫端須用 `useTranslation()` 取 i18n，不可直接讀 localStorage）。
 */
export function isEnglishLocale(i18n: Pick<I18nType, 'resolvedLanguage' | 'language'>): boolean {
  return i18n.resolvedLanguage === 'en' || i18n.language === 'en'
}

export function pickNarrative(
  i18n: Pick<I18nType, 'resolvedLanguage' | 'language'>,
  zh: string | null | undefined,
  en: string | null | undefined,
  fallback?: string | null,
): string | null {
  const picked = isEnglishLocale(i18n) ? en : zh
  if (picked != null && picked !== '') return picked
  return fallback != null && fallback !== '' ? fallback : null
}
