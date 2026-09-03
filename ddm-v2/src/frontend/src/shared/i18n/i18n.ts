// i18next 初始化（ADR-032 Phase A：D3.2 首屏語言決定）。
//
// 刻意不用 i18next-browser-languagedetector：ADR-032 §4.1 選項 C（瀏覽器
// Accept-Language 自動偵測）已被 User 明確否決——語言來源是「使用者個人設定」
// （選項 A），不是瀏覽器/環境。這裡只做「/me 回來之前」的首屏暫時值：
// 讀 localStorage 記住的上次選擇，沒有就用 DEFAULT_LOCALE。伺服器值到達後由
// `useLocaleSync`（見同目錄）改寫成權威值，並回寫 localStorage（D3.2）。
import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './resources/en'
import zhTW from './resources/zh-TW'
// ADR-034 §C2：錯誤 catalog（errors.<CODE>[.<resource>]）。刻意與 en/zh-TW 的
// Widen 對稱機制分開維護——errors 的 key 一致性由 errorCodes.ts 的 ErrorCatalog
// 型別保證（涵蓋 registry.py 全部 code），不套用 Widen 的字面值對稱規則
// （NOT_FOUND 等含 resource 子物件，語序中英本就不同）。這裡把 errors 併入
// 各語系的 translation 命名空間，讓 t('errors.NOT_FOUND.rule_set') 可直接查得到。
import errorsEn from './resources/errors.en'
import errorsZhTW from './resources/errors.zh-TW'

// 語系碼與資源鍵的對照唯一定義處（ADR-032 I6：zh-TW ↔ _zh、en ↔ _en）。
// 後端對照見 src/ddm_v2/locale.py——兩邊各自維護一份是因為前後端是不同執行環境，
// 但**值域必須逐字相同**，改一邊必須改另一邊。
export const SUPPORTED_LOCALES = ['zh-TW', 'en'] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]
export const DEFAULT_LOCALE: SupportedLocale = 'zh-TW'

export const LOCALE_STORAGE_KEY = 'ddm_v2.locale'

export function isSupportedLocale(v: unknown): v is SupportedLocale {
  return typeof v === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(v)
}

/** 首屏暫時值：localStorage 的上次選擇，沒有／不合法就回退預設（D3.2）。 */
export function readCachedLocale(): SupportedLocale {
  try {
    const cached = localStorage.getItem(LOCALE_STORAGE_KEY)
    if (isSupportedLocale(cached)) return cached
  } catch {
    // localStorage 不可用（隱私模式等）：忽略，用預設值
  }
  return DEFAULT_LOCALE
}

// `<html lang>` 必須跟著使用者語言變（a11y／SEO／瀏覽器拼字檢查等都吃這個屬性；
// 複審實測：改動前 index.html 是寫死的 zh-TW，全 repo 沒有任何地方寫入
// `document.documentElement.lang`，切到英文後這個屬性仍卡在 zh-TW）。
// 監聽器要在 `init()` 之前掛，才不會漏掉「初始化當下」可能觸發的第一次事件；
// 但不同版本的 i18next 對「init 時是否同步觸發 languageChanged」沒有保證，
// 所以初始化後再顯式設一次（用 `initialLocale` 而非讀 `i18next.language`，
// 避免依賴 init() 的內部狀態何時就緒）。
i18next.on('languageChanged', (lng) => {
  document.documentElement.lang = lng
})

const initialLocale = readCachedLocale()

void i18next.use(initReactI18next).init({
  resources: {
    'zh-TW': { translation: { ...zhTW, errors: errorsZhTW } },
    en: { translation: { ...en, errors: errorsEn } },
  },
  lng: initialLocale,
  fallbackLng: DEFAULT_LOCALE,
  interpolation: { escapeValue: false }, // React 已跳脫，避免雙重轉義
  returnNull: false,
})

// 首屏立即設一次，不等第一次 languageChanged 事件。
document.documentElement.lang = initialLocale

export default i18next
