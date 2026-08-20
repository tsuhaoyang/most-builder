// zh-TW 外殼字串（ADR-032 Phase A：L1 UI 外殼）。
//
// 這是系統的原生語言與唯一真相——現有元件的中文字面值搬過來即可，不是翻譯產物。
// 抽取範圍見 en.ts 檔頭註解（兩份 key 結構必須逐一對稱，缺一邊會被 i18next
// 靜默 fallback 蓋過去，不會報錯，所以用這份當對照表逐把新增）。
const zhTW = {
  header: {
    appTitle: 'MOST Workbench',
    toggleSidebarAria: '開啟/關閉側欄',
    importExcel: '匯入 Excel',
  },
  nav: {
    dashboard: '儀表板',
    workbenchV3: 'MOST 工作台',
    wiProject: 'WI 專案建立',
    level: 'Level System',
    case: '分析案件',
    dictionaries: '主數據管理',
    users: '使用者管理',
    ruleset: 'MOST 字典',
  },
  navShort: {
    dashboard: '表',
    workbenchV3: 'M',
    wiProject: 'W',
    level: 'L',
    case: '案',
    dictionaries: '主',
    users: '人',
    ruleset: '字',
  },
  sidebar: {
    expandAria: '展開側欄',
    collapseAria: '折疊側欄',
  },
  locale: {
    switcherAriaLabel: '切換語言',
    zhTW: '中文',
    en: 'EN',
    updateFailed: '語言偏好更新失敗，已還原為原本語言（{{message}}）',
  },
  errorBoundary: {
    title: '此分頁發生錯誤',
    backToDashboard: '回儀表板',
  },
  ruleSetUnavailable: {
    title: '無法載入 MOST 字典（rule-set），因此無法建模。',
    unknownError: '未知錯誤',
    hint: '可能原因：系統目前沒有「啟用中」的字典版本。請至「MOST 字典」頁確認有一個已發布版本被設為啟用中。',
  },
  worksheetRequired: {
    message: '請先從分析案件開啟工時表',
    goToCases: '前往分析案件',
  },
  comboBox: {
    searchPlaceholder: '搜尋…',
    noMatch: '無相符',
    addNew: '＋ 新增「{{label}}」',
  },
  app: {
    tabInProgress: '{{tab}}：功能開發中（待移植自 v3）',
  },
  i18nReview: {
    tabLabel: '英文覆核',
    note: '逐條覆核：可就地修正英文譯文並標記已覆核，也可指派給人。刻意沒有「全部核准」——一次核准整批會讓覆核變成橡皮圖章（ADR-032 R1／I5：g_grasp 6 TMU 與 g_touch 3 TMU 若翻得無法區分，英文介面下選錯格就是工時差一倍）。',
    noteViewer: '本頁僅供檢視翻譯覆核進度與待審清單；修正譯文／標記已覆核／指派需要 analyst 以上角色。',
    loading: '載入英文覆核清單…',
    loadError: '載入失敗：{{message}}',
    summary: {
      overall: '整體英文覆核',
      progress: '{{reviewed}}/{{total}}',
    },
    filters: {
      searchPlaceholder: '搜尋中文來源／英文譯文…',
      entityTypeLabel: '物件類型',
      allEntityTypes: '全部類型',
      statusLabel: '狀態',
      allStatuses: '全部狀態',
      assignedToMe: '只看指派給我',
    },
    entityType: {
      rule_option: 'MOST 字典選項',
      vocab_item: '工作詞彙',
      motion_template: '動作模組範本',
    },
    field: {
      label: '下拉標籤',
      sentence: '敘事句面',
      name: '名稱',
    },
    status: {
      never_translated: '尚未翻譯',
      unreviewed: '未覆核',
      stale: '已過期',
    },
    reviewSource: {
      machine: '機器翻譯',
      human: '人工覆核',
      legacy_seed: '舊資料（來源不明）',
      untranslated: '尚無譯文（側表列只為記指派而存在）',
    },
    table: {
      entityType: '類型',
      sourceZh: '中文來源',
      targetEn: '英文譯文',
      status: '狀態',
      source: '來源',
      assignedTo: '指派給',
      empty: '無符合條件的項目',
      untranslated: '（尚未翻譯）',
      unassigned: '（未指派）',
      sourceChangedBadge: '來源已變更',
      sourceChangedHint: '這筆翻譯所依據的中文來源已經變了，譯文尚未依新來源重新確認——比單純「未覆核」更急',
      targetChangedBadge: '譯文已變更',
      targetChangedHint: '這一列的英文在上次覆核之後被人改過，需要重新確認——與「來源已變更」是兩件不同的事',
      openEditor: '覆核',
      closeEditor: '收合',
      copyRow: '複製',
      copyRowDone: '已複製',
      copyAll: '複製全部（TSV）',
      copyAllDone: '已複製 {{n}} 筆',
      copyFailed: '複製失敗，請手動選取文字複製',
    },
    editor: {
      scope: '{{scope}} · {{field}}',
      targetEn: '英文譯文',
      targetEnPlaceholder: '輸入或修正英文譯文…',
      charCount: '{{n}}/{{max}} 字元',
      markReviewed: '標記已覆核',
      marking: '送出中…',
      cancel: '取消',
      needTranslation: '這一列還沒有英文譯文——要標記已覆核就得先在上面填入譯文（空白覆核會被後端以 422 擋下）。',
      blankSentenceHint: '這一列的中文句面本身為空 —— 留空即「刻意不入句」（ADR-032 D7.6），送出時會顯式寫入空字串。',
      assignLabel: '指派',
      assignPlaceholder: '員工號',
      assign: '指派',
      assignToMe: '指派給我',
      unassign: '取消指派',
    },
  },
} as const

export default zhTW
