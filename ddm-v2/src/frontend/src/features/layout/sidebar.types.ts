/**
 * All navigable tab IDs in the sidebar (ADR-021 target IA: 7 + 2 admin items).
 *
 * 'wi' (WiWorkbench worksheet editor) is no longer a top-level nav item —
 * per ADR-021 it moves into the 分析案件 editing context (Phase 3). The tab id
 * remains valid in App.tsx so it can be reached programmatically until then.
 */
export type TabId =
  | 'dashboard'
  | 'workbench-v3'
  | 'wi-project'
  | 'level'
  | 'case'
  | 'dictionaries'
  | 'users'
  | 'ruleset'
  | 'wi'

/** A single item in the sidebar navigation. */
export interface NavItem {
  /** Unique route identifier — matches the tab state in App.tsx */
  id: TabId
  /** Full label shown when sidebar is expanded */
  label: string
  /** Short label (1–2 CJK chars or 1 Latin char) shown when sidebar is collapsed */
  shortLabel: string
  /** Minimum role required to see this item. 'analyst' = level ≥ 1; 'admin' = level ≥ 3 */
  minRole?: 'analyst' | 'admin'
}
