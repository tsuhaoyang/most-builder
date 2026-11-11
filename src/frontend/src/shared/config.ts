// 作用中的 worksheet 初始值（空字串；由 SOP tab 切換後才設定）
export const ACTIVE_WS = ''
export const TMU_SEC = 0.036
// 值權威 rule-set 不再寫死於前端（ADR-023 §3.5）：
// 改由 `GET /api/v2/rule-sets/active` ＋ `useActiveRuleSet()` 讀後端 is_active 旗標。
