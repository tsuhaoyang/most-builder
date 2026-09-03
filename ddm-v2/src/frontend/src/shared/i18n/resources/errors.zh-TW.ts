// ADR-034 §C2 — 錯誤訊息 catalog（zh-TW）。
//
// key 結構 = `errors.<CODE>` 或 `errors.<CODE>.<resource>`（ADR-034 D4 命名規範）。
// 插值參數來自後端 error.detail 的結構化鍵（rule_set_code / id / action …），
// 走 i18next 預設 {{param}} 插值。
//
// I2（中文語意不得退化）：這裡的中文與後端既有 message 語意等價（後端 message
// 仍是 fallback，但正常路徑改由此 catalog 顯示）。
//
// 型別 ErrorCatalog 強制涵蓋 registry.py 全部 code——缺一個 typecheck 就紅。
import type { ErrorCatalog } from '../errorCodes'

const errorsZh: ErrorCatalog = {
  // ── 資源不存在（NOT_FOUND）：依 resource 分 key，插值用各自然鍵 ──────────
  NOT_FOUND: {
    // 通用：無 resource 時的最後手段
    default: '找不到資源',
    rule_set: '找不到規則版本：{{rule_set_code}}',
    option: '找不到字典選項：{{id}}',
    module: '找不到動作模組：{{module_id}}',
    module_version: '找不到模組版本：{{id}}',
    module_row: '找不到模組列：{{id}}',
    worksheet: '找不到工序表：{{worksheet_id}}',
    project: '找不到專案：{{project_id}}',
    wi_set_item: '找不到 WI 專案項目：{{id}}',
    import: '找不到匯入批次：{{import_id}}',
    parse_job: '找不到解析作業：{{job_id}}',
    parse_run: '找不到解析紀錄：{{run_id}}',
    synonym: '找不到同義詞：{{synonym_id}}',
    motion_template: '找不到動作範本：{{id}}',
    app_user: '找不到使用者：{{id}}',
    vocab: '找不到工作詞彙：{{id}}',
  },
  // ── 權限（FORBIDDEN）：依 resource + action ────────────────────────────
  FORBIDDEN: {
    default: '權限不足，無法執行此操作',
    module: '權限不足，無法對動作模組執行「{{action}}」',
    worksheet: '權限不足，無法對工序表執行「{{action}}」',
    motion_template: '權限不足，無法對動作範本執行「{{action}}」',
  },
  UNAUTHORIZED: '尚未登入或身分驗證失敗',
  // ── 資源衝突（CONFLICT） ───────────────────────────────────────────────
  CONFLICT: {
    default: '資源衝突，操作無法完成',
    rule_set: '規則版本代碼已存在：{{rule_set_code}}',
    option: '字典選項衝突：{{id}}',
    project: '專案衝突：{{project_code}}',
  },
  VALIDATION_ERROR: '資料驗證失敗',
  BAD_REQUEST: '請求格式不正確',
  // ── 規則版本生命週期 / 完整性 ──────────────────────────────────────────
  VERSION_PUBLISHED: '此版本已發布，內容已凍結，無法再修改',
  TIME_SOURCE_IMMUTABLE: '時間來源已鎖定，無法變更',
  NO_ACTIVE_RULE_SET: '目前沒有啟用中的規則版本，請先啟用一個已發布版本',
  NO_DEFAULT_POLICY: '找不到預設政策設定',
  RULE_SET_ACTIVATE_CONFLICT: '啟用規則版本時發生衝突，請重新載入後再試',
  RULE_SET_INCOMPLETE: '規則版本內容不完整，無法發布',
  RULE_SET_NOT_RETIRED: '此規則版本尚未封存，無法執行此操作',
  RULE_SET_RETIRED: '此規則版本已封存，無法執行此操作',
  RULE_SET_ACTIVE: '此規則版本仍在啟用中，無法執行此操作',
  RULE_SET_NOT_DRAFT: '此規則版本非草稿狀態，無法編輯',
  RULE_SET_FROZEN: '此規則版本已凍結（已發布／認證），請先建立草稿版本再編輯',
  RULE_SET_IN_USE: '此規則版本已被既有資料引用，無法刪除',
  CERTIFIED_IMMUTABLE: '認證匯入版本不可直接修改，請以其內容建立草稿版本',
  EN_LABEL_NOT_UNIQUE: '英文標籤不可重複',
  EN_FIELD_NOT_WRITABLE: '此英文欄位目前不可寫入',
  // ── 動作模組發布驗證 ───────────────────────────────────────────────────
  EMPTY_ROWS: '至少需要一列動作，不可全部刪除',
  REORDER_INVALID: '重新排序的內容不正確',
  // ── 同義詞 / 字典 ──────────────────────────────────────────────────────
  SYNONYM_CONFLICT: '同義詞衝突：此別名已存在',
  SYNONYM_PRIORITY_COLLISION: '同義詞優先序衝突',
  OPTION_CODE_NOT_FOUND: '找不到字典選項代碼',
  // ── Level System 驗證 ──────────────────────────────────────────────────
  LEVEL_POLICY_MISMATCH: 'Level 政策不一致',
  LEVEL_VALIDATION_FAILED: 'Level System 驗證未通過',
  LEVEL_VALIDATION_REQUIRED: '需先通過 Level System 驗證',
  // ── WI context / 工序表 ────────────────────────────────────────────────
  WI_CONTEXT_INVALID: 'WI 情境設定不正確',
  SIMO_PAIR_INVALID: 'SIMO 同動配對不正確',
  // ── WI-set 專案實例化 ──────────────────────────────────────────────────
  PROJECT_NOT_FOUND: '找不到專案',
  EMPTY_PROJECT: '專案內尚無任何 WI 項目',
  MANUAL_ITEM_UNSUPPORTED: '目前不支援手動項目',
  WI_TEMPLATE_NOT_FOUND: '找不到 WI 範本',
  INVALID_WI_TEMPLATE: 'WI 範本內容不正確',
  WI_TEMPLATE_UNPUBLISHED: 'WI 範本尚未發布',
  WI_TEMPLATE_RETIRED: 'WI 範本已封存',
  WI_TEMPLATE_VERSION_NOT_FOUND: '找不到 WI 範本版本',
  WORKSHEET_RULE_SET_NOT_FOUND: '找不到工序表使用的規則版本',
  VOCAB_REF_INVALID: '詞彙引用不正確',
  // ── i18n 覆核流程 ──────────────────────────────────────────────────────
  I18N_UNKNOWN_SCOPE_KEY: '未知的 i18n scope key',
  I18N_REVIEW_ROW_NOT_FOUND: '找不到覆核項目',
  I18N_REVIEW_TARGET_MISSING: '覆核譯文不可為空',
  // ── 系統層級 ───────────────────────────────────────────────────────────
  RATE_LIMITED: '操作過於頻繁，請稍後再試',
  SERVICE_UNAVAILABLE: '服務暫時無法使用，請稍後再試',
  PAYLOAD_TOO_LARGE: '上傳內容過大',
  INTERNAL_ERROR: '系統內部錯誤，請稍後再試',
}

export default errorsZh
