import { create } from 'zustand'
import type { MotionModuleSummary } from './api'

// ── Cross-tab workbench state ─────────────────────────────────────────────────
//
// Tab 1 (動作模組) → Tab 2 (WI 組成): pendingModules
// Tab 2 (WI 組成) → Tab 3 (製程途程): pendingWiIds

interface WorkbenchV3Store {
  activeTab: 'tab1' | 'tab2' | 'tab3'
  setActiveTab: (tab: 'tab1' | 'tab2' | 'tab3') => void

  // Tab 1 → Tab 2 cross-tab send (F-03 跨層傳送)
  pendingModules: MotionModuleSummary[]
  setPendingModules: (modules: MotionModuleSummary[]) => void
  clearPendingModules: () => void

  // Tab 2 → Tab 3 cross-tab send
  pendingWiIds: string[]
  setPendingWiIds: (ids: string[]) => void
  clearPendingWiIds: () => void
}

export const useWorkbenchV3Store = create<WorkbenchV3Store>((set) => ({
  activeTab: 'tab1',
  setActiveTab: (tab) => set({ activeTab: tab }),

  pendingModules: [],
  setPendingModules: (modules) => set({ pendingModules: modules }),
  clearPendingModules: () => set({ pendingModules: [] }),

  pendingWiIds: [],
  setPendingWiIds: (ids) => set({ pendingWiIds: ids }),
  clearPendingWiIds: () => set({ pendingWiIds: [] }),
}))
