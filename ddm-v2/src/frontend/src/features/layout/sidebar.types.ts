/** All navigable tab IDs in the sidebar (includes placeholders not yet implemented). */
export type TabId =
  | 'dashboard'
  | 'wi'
  | 'workbench-v3'
  | 'wi-project'
  | 'level'
  | 'case'
  | 'catalog'
  | 'export'
  | 'ruleset'
  | 'users'
  | 'master'
  | 'sop'
  | 'dictionaries'

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
  /** Secondary items are shown below a divider (legacy v2 tabs kept for access) */
  secondary?: boolean
}
