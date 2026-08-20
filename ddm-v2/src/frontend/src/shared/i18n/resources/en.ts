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
  i18nReview: {
    tabLabel: 'English Review',
    note: 'Review one row at a time: fix the English in place, mark it reviewed, or assign it to someone. There is deliberately no "approve all" — bulk approval turns review into a rubber stamp (ADR-032 R1/I5: if g_grasp (6 TMU) and g_touch (3 TMU) read the same in English, picking the wrong one doubles the time value).',
    noteViewer: 'This page only shows translation review progress and the pending list; editing translations, marking reviewed and assigning require the analyst role or above.',
    loading: 'Loading English review list…',
    loadError: 'Failed to load: {{message}}',
    summary: {
      overall: 'Overall English review',
      progress: '{{reviewed}}/{{total}}',
    },
    filters: {
      searchPlaceholder: 'Search Chinese source / English translation…',
      entityTypeLabel: 'Entity type',
      allEntityTypes: 'All types',
      statusLabel: 'Status',
      allStatuses: 'All statuses',
      assignedToMe: 'Assigned to me only',
    },
    entityType: {
      rule_option: 'MOST dictionary option',
      vocab_item: 'Work vocabulary',
      motion_template: 'Motion template',
    },
    field: {
      label: 'Dropdown label',
      sentence: 'Narrative phrase',
      name: 'Name',
    },
    status: {
      never_translated: 'Never translated',
      unreviewed: 'Unreviewed',
      stale: 'Stale',
    },
    reviewSource: {
      machine: 'Machine translation',
      human: 'Human reviewed',
      legacy_seed: 'Legacy data (source unknown)',
      untranslated: 'No translation yet (row exists only to record the assignment)',
    },
    table: {
      entityType: 'Type',
      sourceZh: 'Chinese source',
      targetEn: 'English translation',
      status: 'Status',
      source: 'Source',
      assignedTo: 'Assignee',
      empty: 'No items match the current filters',
      untranslated: '(not translated)',
      unassigned: '(unassigned)',
      sourceChangedBadge: 'Source changed',
      sourceChangedHint: 'The Chinese source this translation was based on has changed; the translation has not yet been re-confirmed against the new source — more urgent than plain "unreviewed"',
      targetChangedBadge: 'Translation changed',
      targetChangedHint: 'The English text was edited after the last review and needs re-confirmation — a different thing from "source changed"',
      openEditor: 'Review',
      closeEditor: 'Collapse',
      copyRow: 'Copy',
      copyRowDone: 'Copied',
      copyAll: 'Copy all (TSV)',
      copyAllDone: 'Copied {{n}} rows',
      copyFailed: 'Copy failed — please select and copy the text manually',
    },
    editor: {
      scope: '{{scope}} · {{field}}',
      targetEn: 'English translation',
      targetEnPlaceholder: 'Enter or correct the English translation…',
      charCount: '{{n}}/{{max}} characters',
      markReviewed: 'Mark reviewed',
      marking: 'Submitting…',
      cancel: 'Cancel',
      needTranslation: 'This row has no English translation yet — fill it in above before marking it reviewed (the backend rejects blank reviews with 422).',
      blankSentenceHint: 'The Chinese narrative phrase for this row is itself empty — leaving the English empty means "deliberately not part of the sentence" (ADR-032 D7.6); an explicit empty string is sent.',
      assignLabel: 'Assign',
      assignPlaceholder: 'Employee no.',
      assign: 'Assign',
      assignToMe: 'Assign to me',
      unassign: 'Unassign',
    },
  },
}

export default en
