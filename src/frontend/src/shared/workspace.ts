import { create } from 'zustand'
import { ACTIVE_WS } from './config'

// 案件情境（ADR-021 Phase 3）：進入「編輯工時表」時由分析案件頁寫入，
// wi tab 的 CaseContextBar 直接讀取渲染。
export interface ActiveCaseMeta {
  processName: string
  productName: string
  skuName: string
  versionNo: string
  status: string
}

// 作用中的 worksheet（由分析案件「編輯工時表／新建案件」進入時設定；
// MOST 工作台 Tab3、Level System、匯入精靈共用）
interface WorkspaceState {
  activeWs: string
  activeCaseMeta: ActiveCaseMeta | null
  setActiveWs: (id: string) => void
  /** 進入案件編輯情境：一併寫入 worksheet id 與案件 meta（ADR-021 Phase 3） */
  setActiveCase: (id: string, meta: ActiveCaseMeta) => void
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  activeWs: ACTIVE_WS,
  activeCaseMeta: null,
  setActiveWs: (id) => set({ activeWs: id }),
  setActiveCase: (id, meta) => set({ activeWs: id, activeCaseMeta: meta }),
}))
