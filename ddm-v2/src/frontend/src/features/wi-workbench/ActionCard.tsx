import type { AiCycleDraft, AiPlannedAction } from './aiTypes'

const ACTION_LABEL: Record<string, string> = {
  acquire: '取得',
  move_place: '移動放置',
  controlled_move: '控制移動',
  process: '製程',
  inspect: '檢查',
  release_return: '放開／歸位',
  composite_unknown: '無法拆解',
}

export function ActionCard({
  action,
  draft,
  adopted,
  disabled,
  onAdopt,
}: {
  action: AiPlannedAction | undefined
  draft: AiCycleDraft
  adopted: boolean
  disabled?: boolean
  onAdopt: () => void
}) {
  const seq = (draft.cycle?.seq as string) || '—'
  const tmu = draft.engine_result?.total_tmu
  const typeLabel = ACTION_LABEL[action?.action_type || ''] || action?.action_type || draft.action_id
  const canAdopt = !!draft.cycle && draft.complete && !disabled
  // D3：完整 A6 信心檔位待後端對 chosen 輸出 band；minimal 不重算分數，僅顯示完整／待補
  const statusLabel = draft.complete && !draft.issues.some((i) => i.startsWith('engine_reject_'))
    ? '可採用'
    : '待審'

  return (
    <div
      className={`rounded-lg border p-3 space-y-2 ${adopted ? 'border-emerald-400 bg-emerald-50/40' : 'border-slate-200 bg-white'}`}
      data-testid={`ai-action-card-${draft.action_id}`}
    >
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium text-slate-800">{typeLabel}</span>
        <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{seq}</span>
        <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700">{statusLabel}</span>
        {draft.complete ? (
          <span className="text-xs text-emerald-700">完整</span>
        ) : (
          <span className="text-xs text-amber-700">待補</span>
        )}
        {tmu != null && (
          <span className="text-xs text-slate-500 ml-auto">{tmu} TMU</span>
        )}
      </div>
      {draft.narrative && (
        <p className="text-xs text-slate-600 line-clamp-2">{draft.narrative}</p>
      )}
      {draft.issues?.length > 0 && (
        <p className="text-xs text-amber-700">待審：{draft.issues.join('、')}</p>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!canAdopt}
          onClick={onAdopt}
          className="px-2.5 py-1 text-xs rounded bg-indigo-600 text-white disabled:opacity-40"
        >
          {adopted ? '已採用（再載入）' : '採用到編輯器'}
        </button>
      </div>
    </div>
  )
}
