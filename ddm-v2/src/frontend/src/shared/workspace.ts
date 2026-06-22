import { create } from 'zustand'
import { ACTIVE_WS } from './config'

// 作用中的 worksheet（由 ⑤ SOP 版本切換；WI/匯出/SOP 共用）
interface WorkspaceState {
  activeWs: string
  setActiveWs: (id: string) => void
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  activeWs: ACTIVE_WS,
  setActiveWs: (id) => set({ activeWs: id }),
}))
