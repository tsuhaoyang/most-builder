// ADR-034 §C2 — 錯誤訊息 catalog（en）。
//
// key 結構 = `errors.<CODE>` 或 `errors.<CODE>.<resource>`（ADR-034 D4 命名規範）。
// 英文語序自然（如 "Rule set not found: {{rule_set_code}}"），非機器直譯中文。
// 走 i18next 預設 {{param}} 插值。
//
// 型別 ErrorCatalog 強制涵蓋 registry.py 全部 code——缺一個 typecheck 就紅。
import type { ErrorCatalog } from '../errorCodes'

const errorsEn: ErrorCatalog = {
  // ── Resource not found (NOT_FOUND) ──────────────────────────────────────
  NOT_FOUND: {
    default: 'Resource not found',
    rule_set: 'Rule set not found: {{rule_set_code}}',
    option: 'Dictionary option not found: {{id}}',
    module: 'Motion module not found: {{module_id}}',
    module_version: 'Module version not found: {{id}}',
    module_row: 'Module row not found: {{id}}',
    worksheet: 'Worksheet not found: {{worksheet_id}}',
    project: 'Project not found: {{project_id}}',
    wi_set_item: 'WI project item not found: {{id}}',
    import: 'Import batch not found: {{import_id}}',
    parse_job: 'Parse job not found: {{job_id}}',
    parse_run: 'Parse run not found: {{run_id}}',
    synonym: 'Synonym not found: {{synonym_id}}',
    motion_template: 'Motion template not found: {{id}}',
    app_user: 'User not found: {{id}}',
    vocab: 'Work vocabulary not found: {{id}}',
  },
  // ── Permission (FORBIDDEN) ──────────────────────────────────────────────
  FORBIDDEN: {
    default: 'You do not have permission to perform this action',
    module: 'You do not have permission to {{action}} this motion module',
    worksheet: 'You do not have permission to {{action}} this worksheet',
    motion_template: 'You do not have permission to {{action}} this motion template',
  },
  UNAUTHORIZED: 'You are not signed in, or authentication failed',
  // ── Conflict (CONFLICT) ─────────────────────────────────────────────────
  CONFLICT: {
    default: 'Resource conflict; the operation could not be completed',
    rule_set: 'Rule set code already exists: {{rule_set_code}}',
    option: 'Dictionary option conflict: {{id}}',
    project: 'Project conflict: {{project_code}}',
  },
  VALIDATION_ERROR: 'Validation failed',
  BAD_REQUEST: 'The request is malformed',
  // ── Rule-set lifecycle / integrity ──────────────────────────────────────
  VERSION_PUBLISHED: 'This version is published and frozen; it can no longer be changed',
  TIME_SOURCE_IMMUTABLE: 'The time source is locked and cannot be changed',
  NO_ACTIVE_RULE_SET: 'There is no active rule set; activate a published version first',
  NO_DEFAULT_POLICY: 'No default policy is configured',
  RULE_SET_ACTIVATE_CONFLICT: 'A conflict occurred while activating the rule set; reload and try again',
  RULE_SET_INCOMPLETE: 'The rule set is incomplete and cannot be published',
  RULE_SET_NOT_RETIRED: 'This rule set is not archived, so this action is not allowed',
  RULE_SET_RETIRED: 'This rule set is archived, so this action is not allowed',
  RULE_SET_ACTIVE: 'This rule set is still active, so this action is not allowed',
  RULE_SET_NOT_DRAFT: 'This rule set is not a draft and cannot be edited',
  RULE_SET_FROZEN: 'This rule set is frozen (published/certified); create a draft version before editing',
  RULE_SET_IN_USE: 'This rule set is referenced by existing data and cannot be deleted',
  CERTIFIED_IMMUTABLE: 'A certified import cannot be edited directly; create a draft from its content',
  EN_LABEL_NOT_UNIQUE: 'The English label must be unique',
  EN_FIELD_NOT_WRITABLE: 'This English field is not writable right now',
  // ── Motion-module publish validation ────────────────────────────────────
  EMPTY_ROWS: 'At least one row is required; they cannot all be deleted',
  REORDER_INVALID: 'The reordering is invalid',
  // ── Synonyms / dictionary ───────────────────────────────────────────────
  SYNONYM_CONFLICT: 'Synonym conflict: this alias already exists',
  SYNONYM_PRIORITY_COLLISION: 'Synonym priority collision',
  OPTION_CODE_NOT_FOUND: 'Dictionary option code not found',
  // ── Level System validation ─────────────────────────────────────────────
  LEVEL_POLICY_MISMATCH: 'Level policy mismatch',
  LEVEL_VALIDATION_FAILED: 'Level System validation failed',
  LEVEL_VALIDATION_REQUIRED: 'Level System validation is required first',
  // ── WI context / worksheet ──────────────────────────────────────────────
  WI_CONTEXT_INVALID: 'The WI context is invalid',
  SIMO_PAIR_INVALID: 'The SIMO pairing is invalid',
  // ── WI-set project instantiation ────────────────────────────────────────
  PROJECT_NOT_FOUND: 'Project not found',
  EMPTY_PROJECT: 'The project has no WI items yet',
  MANUAL_ITEM_UNSUPPORTED: 'Manual items are not supported',
  WI_TEMPLATE_NOT_FOUND: 'WI template not found',
  INVALID_WI_TEMPLATE: 'The WI template is invalid',
  WI_TEMPLATE_UNPUBLISHED: 'The WI template is not published yet',
  WI_TEMPLATE_RETIRED: 'The WI template is archived',
  WI_TEMPLATE_VERSION_NOT_FOUND: 'WI template version not found',
  WORKSHEET_RULE_SET_NOT_FOUND: 'The rule set used by the worksheet was not found',
  VOCAB_REF_INVALID: 'The vocabulary reference is invalid',
  // ── i18n review workflow ────────────────────────────────────────────────
  I18N_UNKNOWN_SCOPE_KEY: 'Unknown i18n scope key',
  I18N_REVIEW_ROW_NOT_FOUND: 'Review item not found',
  I18N_REVIEW_TARGET_MISSING: 'The reviewed translation cannot be blank',
  // ── System level ────────────────────────────────────────────────────────
  RATE_LIMITED: 'Too many requests; please try again later',
  SERVICE_UNAVAILABLE: 'The service is temporarily unavailable; please try again later',
  PAYLOAD_TOO_LARGE: 'The uploaded content is too large',
  INTERNAL_ERROR: 'An internal error occurred; please try again later',
}

export default errorsEn
