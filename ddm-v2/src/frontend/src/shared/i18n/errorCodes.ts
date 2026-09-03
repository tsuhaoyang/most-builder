// ADR-034 §C2 — 錯誤碼列舉與 catalog 完整性機械保證。
//
// 此檔列出後端 registry.py 的**全部 ErrorCode**。TypeScript 型別約束確保
// en.ts / zh-TW.ts 的 `errors` key 與此列舉一致。缺 key 會讓 typecheck 紅，
// 多餘 key 也會（excess property check）。
//
// 新增後端錯誤碼時，必須在此新增成員，否則 typecheck 失敗。
// 這就是 ADR-034 §D6「前端 catalog key 與後端 registry 一致」的機械保證。

/** 後端 ErrorCode 列舉值（mirror of registry.py）。 */
export const ERROR_CODES = [
  // Core envelope codes
  'NOT_FOUND',
  'VALIDATION_ERROR',
  'CONFLICT',
  'VERSION_PUBLISHED',
  'TIME_SOURCE_IMMUTABLE',
  'FORBIDDEN',
  'UNAUTHORIZED',
  'NO_ACTIVE_RULE_SET',
  'NO_DEFAULT_POLICY',
  'RULE_SET_ACTIVATE_CONFLICT',
  'INTERNAL_ERROR',
  // Non-family HTTP status codes
  'RATE_LIMITED',
  'SERVICE_UNAVAILABLE',
  'PAYLOAD_TOO_LARGE',
  'BAD_REQUEST',
  // Rule-set lifecycle
  'RULE_SET_INCOMPLETE',
  'RULE_SET_NOT_RETIRED',
  'RULE_SET_RETIRED',
  'RULE_SET_ACTIVE',
  'RULE_SET_NOT_DRAFT',
  'RULE_SET_FROZEN',
  'RULE_SET_IN_USE',
  'CERTIFIED_IMMUTABLE',
  'EN_LABEL_NOT_UNIQUE',
  'EN_FIELD_NOT_WRITABLE',
  // Motion-module publish validation
  'EMPTY_ROWS',
  'REORDER_INVALID',
  // Synonyms / dictionary
  'SYNONYM_CONFLICT',
  'SYNONYM_PRIORITY_COLLISION',
  'OPTION_CODE_NOT_FOUND',
  // Level System
  'LEVEL_POLICY_MISMATCH',
  'LEVEL_VALIDATION_FAILED',
  'LEVEL_VALIDATION_REQUIRED',
  // WI context / worksheet
  'WI_CONTEXT_INVALID',
  'SIMO_PAIR_INVALID',
  // WI-set project instantiation
  'PROJECT_NOT_FOUND',
  'EMPTY_PROJECT',
  'MANUAL_ITEM_UNSUPPORTED',
  'WI_TEMPLATE_NOT_FOUND',
  'INVALID_WI_TEMPLATE',
  'WI_TEMPLATE_UNPUBLISHED',
  'WI_TEMPLATE_RETIRED',
  'WI_TEMPLATE_VERSION_NOT_FOUND',
  'WORKSHEET_RULE_SET_NOT_FOUND',
  'VOCAB_REF_INVALID',
  // i18n review
  'I18N_UNKNOWN_SCOPE_KEY',
  'I18N_REVIEW_ROW_NOT_FOUND',
  'I18N_REVIEW_TARGET_MISSING',
] as const

export type ErrorCode = (typeof ERROR_CODES)[number]

/**
 * 型別工具：確保 errors catalog 涵蓋所有 ErrorCode。
 *
 * - 每個 ErrorCode 都必須有對應的 key（值 = string 或 Record 都可以）。
 * - 不允許多餘 key。
 *
 * 使用方式：在 zh-TW.ts / en.ts 的 errors 區塊聲明為此型別，
 * 缺 key 或多 key 會讓 tsc 報錯。
 */
export type ErrorCatalog = {
  [K in ErrorCode]: string | Record<string, string>
}
