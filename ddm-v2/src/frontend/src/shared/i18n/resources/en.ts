import zhTW from './zh-TW'

// English 外殼字串（ADR-032 Phase A：L1 UI 外殼，機械翻譯／工程端自譯）。
//
// 範圍＝本輪抽取的高頻外殼字串：側欄導航（7 主 + 2 admin）、頁首（標題／匯入按鈕／
// 側欄開關）、語言切換器本身、共用元件（ErrorBoundary／RuleSetUnavailable／
// WorksheetRequiredNotice／ComboBox）。不含任何業務資料標籤（rule-set label_en 等
// 屬 ADR-032 Phase B，不在此檔）。
//
// key 結構必須與 zh-TW.ts 逐一對稱——新增 key 時兩邊一起加，缺一邊會被 i18next
// 靜默 fallback 蓋過去（開發模式看不出來，只有肉眼比對才抓得到，CI 也不會紅；
// 複審 2026-08-18 指出「35/35 對稱」目前只是人工複驗過，沒有任何機制擋住下一次漏加）。
//
// 用型別把這件事從「肉眼複驗」升級成「typecheck 機械保證」：漏一個 key、多一個 key、
// 或把某個 leaf 從字串改成別的型別，tsc 都會直接紅，不必等到有人切成英文親眼看到
// 殘留的中文才發現。不能直接寫 `const en: typeof zhTW`——`zh-TW.ts` 用了 `as const`，
// `typeof zhTW` 的每個 leaf 都是該中文字串本身的字面型別（如 `'切換語言'`），
// 逐字要求英文譯文等於中文字面值沒有意義（也不可能通過）。`Widen<T>` 只保留
// 「鍵的形狀」與「leaf 必須是 string」，放行不同的字串內容。
type Widen<T> = T extends string
  ? string
  : T extends readonly (infer U)[]
    ? Widen<U>[]
    : { [K in keyof T]: Widen<T[K]> }

const en: Widen<typeof zhTW> = {
  header: {
    appTitle: 'MOST Workbench',
    toggleSidebarAria: 'Toggle sidebar',
    importExcel: 'Import Excel',
  },
  nav: {
    dashboard: 'Dashboard',
    workbenchV3: 'Workbench',
    wiProject: 'WI Project Builder',
    level: 'Level System',
    case: 'Case Analysis',
    dictionaries: 'Master Data',
    users: 'User Management',
    ruleset: 'MOST Dictionary',
  },
  navShort: {
    dashboard: 'D',
    workbenchV3: 'M',
    wiProject: 'W',
    level: 'L',
    case: 'C',
    dictionaries: 'MD',
    users: 'U',
    ruleset: 'Dic',
  },
  sidebar: {
    expandAria: 'Expand sidebar',
    collapseAria: 'Collapse sidebar',
  },
  locale: {
    switcherAriaLabel: 'Switch language',
    zhTW: '中文',
    en: 'EN',
    updateFailed: 'Failed to update language preference; reverted to the previous language ({{message}})',
  },
  errorBoundary: {
    title: 'This tab encountered an error',
    backToDashboard: 'Back to dashboard',
  },
  ruleSetUnavailable: {
    title: 'Failed to load the MOST dictionary (rule-set); modeling is unavailable.',
    unknownError: 'Unknown error',
    hint: 'Possible cause: there is currently no "active" dictionary version. Go to "MOST Dictionary" and confirm a published version is set active.',
  },
  worksheetRequired: {
    message: 'Please open a worksheet from Case Analysis first',
    goToCases: 'Go to Case Analysis',
  },
  comboBox: {
    searchPlaceholder: 'Search…',
    noMatch: 'No match',
    addNew: '+ Add "{{label}}"',
  },
  app: {
    tabInProgress: '{{tab}}: under development (to be ported from v3)',
  },
}

export default en
