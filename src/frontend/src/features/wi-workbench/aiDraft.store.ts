import { create } from 'zustand'
import type { AiParseBlock, NlDraftResponse } from './aiTypes'

interface AiDraftState {
  text: string
  lastResponse: NlDraftResponse | null
  /** 已採用進編輯器的 action_id；再解析時標 stale */
  adoptedActionId: string | null
  stale: boolean
  setText: (t: string) => void
  setResponse: (r: NlDraftResponse | null) => void
  markAdopted: (actionId: string) => void
  markStaleIfNeeded: () => void
  clear: () => void
}

export const useAiDraftStore = create<AiDraftState>((set, get) => ({
  text: '',
  lastResponse: null,
  adoptedActionId: null,
  stale: false,
  setText: (text) => set({ text }),
  setResponse: (lastResponse) =>
    set((state) => {
      // A1：再解析時若編輯器已採用過草稿 → 標 stale，不清空編輯器（由 UI 不呼叫 setCur）
      const keepStale = Boolean(state.adoptedActionId) || state.stale
      return {
        lastResponse,
        stale: keepStale,
        adoptedActionId: null,
      }
    }),
  markAdopted: (actionId) => set({ adoptedActionId: actionId, stale: false }),
  markStaleIfNeeded: () => {
    // retained for callers that want early flag before await; setResponse is authoritative
    if (get().adoptedActionId) set({ stale: true })
  },
  clear: () =>
    set({ text: '', lastResponse: null, adoptedActionId: null, stale: false }),
}))

export function selectAiBlock(s: AiDraftState): AiParseBlock | null {
  return s.lastResponse?.ai ?? null
}
