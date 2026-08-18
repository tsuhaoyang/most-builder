import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import type { Me } from '../auth/useMe'
import { LOCALE_STORAGE_KEY, isSupportedLocale } from './i18n'

/**
 * 伺服器 locale 到達後成為權威值（ADR-032 D3.2：「伺服器是權威，localStorage
 * 只是首屏快取」）。首屏（`/me` 回來之前）已由 `readCachedLocale()`（i18n.ts）
 * 決定暫時語言；這個 hook 只處理「伺服器值到達後」的單向同步：
 * 若與目前 i18next 語言不同就切換，並回寫 localStorage。
 *
 * 使用者主動切換（點語言切換器）不經這裡——那條路徑在 LocaleSwitcher 自己
 * 立即呼叫 i18n.changeLanguage + 送 PATCH，反應要快，不必等這個 effect。
 *
 * 防呆：`me.locale` 不合法（缺漏／未知值）時**不動作**，維持目前語言不變。
 * 這不只是型別防禦——現行 e2e 有多處手工 mock `/api/v2/me`（未帶 `locale`
 * 欄位，早於本 ADR），若這裡對 `undefined` 也呼叫 `changeLanguage`，
 * 会把語言切成 undefined，讓既有中文文字斷言變成不可預期的紅燈
 * （ADR-032 風險段：「e2e 語言必須釘死 zh-TW」）。真正的後端 `/me` 一律回傳
 * 合法值（`MeOut.locale` 是必填 `Literal['zh-TW','en']`），所以這個防呆
 * 只在缺欄位的舊 mock 情境生效，不影響正式行為。
 */
export function useLocaleSync(me: Me | undefined): void {
  const { i18n } = useTranslation()

  useEffect(() => {
    if (!me || !isSupportedLocale(me.locale)) return
    if (i18n.language !== me.locale) {
      void i18n.changeLanguage(me.locale)
    }
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, me.locale)
    } catch {
      // localStorage 不可用（隱私模式等）：忽略，不影響本次渲染的語言
    }
    // 刻意只依賴 me?.locale：這裡是「伺服器值變了才動作」的單向同步，
    // 不需要在 i18n instance 變動時重跑（同一個 i18next 單例，不會變）。
  }, [me?.locale])
}
