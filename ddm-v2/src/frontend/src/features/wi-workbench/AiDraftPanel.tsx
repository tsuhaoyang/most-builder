import { useNlDraft, usePostReviews } from './api'
import { useAiDraftStore } from './aiDraft.store'
import { useWiStore } from './store'
import { ActionCard } from './ActionCard'
import type { CycleState } from './cycle'
import type { NlDraftLegacySlot, NlDraftResponse } from './aiTypes'
import { ApiError } from '../../shared/api/client'

function legacyPatch(res: NlDraftResponse): Partial<CycleState> {
  const patch: Partial<CycleState> = {}
  if (res.suggested_seq === 'GM' || res.suggested_seq === 'CM') {
    patch.seq = res.suggested_seq
  }
  for (const slot of (res.slots ?? []) as NlDraftLegacySlot[]) {
    if (!slot.chosen) continue
    const code = slot.chosen.option_code
    switch (slot.field) {
      case 'g_code': patch.g = code; break
      case 'b_code': patch.b1 = code; break
      case 'b_code2': patch.b4 = code; break
      case 'p_base_code': patch.p_base = code; break
    }
  }
  return patch
}

const UI_VERSION = 'wi-workbench@l3-minimal'

export function AiDraftPanel({
  ruleSetCode,
  worksheetId,
  canWriteReviews,
  onAdoptCycle,
  onLegacyFill,
}: {
  ruleSetCode: string | undefined
  worksheetId: string | null | undefined
  canWriteReviews: boolean
  onAdoptCycle: (cycle: Record<string, unknown>) => void
  onLegacyFill: (patch: Partial<CycleState>) => void
}) {
  const text = useAiDraftStore((s) => s.text)
  const setText = useAiDraftStore((s) => s.setText)
  const lastResponse = useAiDraftStore((s) => s.lastResponse)
  const setResponse = useAiDraftStore((s) => s.setResponse)
  const markAdopted = useAiDraftStore((s) => s.markAdopted)
  const markStaleIfNeeded = useAiDraftStore((s) => s.markStaleIfNeeded)
  const adoptedActionId = useAiDraftStore((s) => s.adoptedActionId)
  const stale = useAiDraftStore((s) => s.stale)

  const nlDraft = useNlDraft()
  const postReviews = usePostReviews()

  const ai = lastResponse?.ai
  const drafts = ai?.drafts ?? []
  const actionsById = Object.fromEntries(
    (ai?.plan?.actions ?? []).map((a) => [a.action_id, a]),
  )

  async function runParse() {
    const t = text.trim()
    if (!t || !ruleSetCode) return
    markStaleIfNeeded()
    try {
      const res = await nlDraft.mutateAsync({
        text: t,
        rule_set_code: ruleSetCode,
        worksheet_id: worksheetId || null,
      })
      setResponse(res)
    } catch {
      // error shown via mutation
    }
  }

  function revisionStaleBlocked(): boolean {
    const srcRev = ai?.source_revision
    const curRev = useWiStore.getState().revisionNo
    if (
      worksheetId
      && srcRev != null
      && curRev != null
      && Number(srcRev) !== Number(curRev)
    ) {
      window.alert(
        `AI 草稿已過期（source rev ${srcRev} ≠ 目前 rev ${curRev}）。請重新解析後再採用。`,
      )
      return true
    }
    return false
  }

  async function adoptDraft(actionId: string) {
    const draft = drafts.find((d) => d.action_id === actionId)
    if (!draft?.cycle) return
    if (revisionStaleBlocked()) return
    onAdoptCycle(draft.cycle)
    markAdopted(actionId)
    if (canWriteReviews && ai?.run_id) {
      try {
        await postReviews.mutateAsync({
          runId: ai.run_id,
          body: {
            ui_version: UI_VERSION,
            events: [
              {
                event_type: 'accept_plan',
                target: { action_id: actionId },
                reason: '採用單一 draft 至編輯器',
              },
            ],
          },
        })
      } catch {
        // 採用編輯器已成功；review 失敗不阻斷
      }
    }
  }

  function applyLegacy() {
    if (!lastResponse) return
    if (revisionStaleBlocked()) return
    const patch = legacyPatch(lastResponse)
    if (Object.keys(patch).length) onLegacyFill(patch)
  }

  const errMsg = (() => {
    const e = nlDraft.error
    if (!e) return ''
    if (e instanceof ApiError) return e.humanMessage
    return (e as Error).message
  })()

  return (
    <div className="space-y-2 pb-2 border-b border-slate-100" data-testid="ai-draft-panel">
      <div className="flex flex-wrap items-start gap-2">
        <span className="text-xs font-semibold text-slate-500 mt-2 shrink-0">AI 草稿</span>
        <textarea
          rows={1}
          className="flex-1 min-w-0 border rounded px-2 py-1.5 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-blue-400"
          placeholder="輸入口語描述，解析成可審核的 MOST 草稿…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (!nlDraft.isPending) void runParse()
            }
          }}
          disabled={nlDraft.isPending || !ruleSetCode}
        />
        <button
          type="button"
          onClick={() => void runParse()}
          disabled={nlDraft.isPending || !text.trim() || !ruleSetCode}
          className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded disabled:opacity-40 shrink-0"
        >
          {nlDraft.isPending ? '解析中…' : '解析'}
        </button>
      </div>

      {errMsg && <p className="text-xs text-red-500">{errMsg}</p>}

      {stale && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          已重新解析：編輯器內容未自動覆寫（標為 stale）。請再按「採用」載入新草稿。
        </p>
      )}

      {lastResponse?.multi_action_warning && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          多個動作草稿 — 請逐筆採用，勿靜默只取第一筆。
        </p>
      )}

      {ai && (
        <div className="flex flex-wrap gap-2 text-xs text-slate-500">
          <span>routing: {ai.routing_status}</span>
          {ai.provenance?.planner && <span>planner: {String(ai.provenance.planner)}</span>}
          {ai.provenance?.fallback && <span className="text-amber-700">rule fallback</span>}
          {ai.routing_reasons?.length > 0 && (
            <span title={ai.routing_reasons.join(', ')}>
              reasons: {ai.routing_reasons.slice(0, 3).join(', ')}
              {ai.routing_reasons.length > 3 ? '…' : ''}
            </span>
          )}
        </div>
      )}

      {drafts.length > 0 ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {drafts.map((d) => (
            <ActionCard
              key={d.action_id}
              action={actionsById[d.action_id]}
              draft={d}
              adopted={adoptedActionId === d.action_id}
              onAdopt={() => void adoptDraft(d.action_id)}
            />
          ))}
        </div>
      ) : lastResponse ? (
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <span>無完整 AI draft（可能僅 rule 建議）</span>
          <button
            type="button"
            className="px-2 py-1 rounded border text-indigo-700 border-indigo-200 hover:bg-indigo-50"
            onClick={applyLegacy}
          >
            填入編輯器（相容）
          </button>
        </div>
      ) : null}
    </div>
  )
}
