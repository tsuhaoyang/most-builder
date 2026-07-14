// 作用中的 worksheet 初始值（空字串；由 SOP tab 切換後才設定）
export const ACTIVE_WS = ''
export const TMU_SEC = 0.036
// 值權威 rule-set（ADR-014）：v3 字典匯入版。工作台建模/發布一律用此版；
// V1 僅供既存 worksheet 重播隔離（CI gate 5），新內容不得再用 V1 發布。
export const ACTIVE_RULE_SET = 'MINIMOST_FACTORY_V2'
