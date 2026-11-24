// 單句輸入（ADR-038 D2 情境 2）：一句 WI → 解析 → 一組草稿進編輯區。不再有「採用到編輯器」捷徑（D3）。
// AI 開著且可用時走外部 ai_service；否則或失敗時用規則解析，結果一樣進編輯區（來源標 rule_based）。
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { resolveErrorMessage } from '../../../shared/i18n/errorMessage'
import { useFromSentence, useWiAiStatus } from './api'

const MAX_TEXT = 2000

export function SentenceInput({ worksheetId, handCode, wiGroup }: {
  worksheetId: string
  handCode: string
  wiGroup: string
}) {
  const { t, i18n } = useTranslation()
  const status = useWiAiStatus()
  const parse = useFromSentence(worksheetId)
  const [text, setText] = useState('')
  const [result, setResult] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null)

  const aiOn = !!status.data?.enabled && !!status.data?.available
  const aiNote = status.isLoading
    ? null
    : !status.data?.enabled
      ? t('workbench.drafts.sentence.aiOff')
      : !status.data?.available
        ? t('workbench.drafts.sentence.aiUnavailable')
        : t('workbench.drafts.sentence.aiOn')

  async function submit() {
    const body = text.trim()
    if (!body) return
    setResult(null)
    try {
      const out = await parse.mutateAsync({
        text: body,
        hand: ['RH', 'LH', 'BH'].includes(handCode) ? handCode : null,
        wi_group: wiGroup.trim() || null,
      })
      const n = out.items.length
      if (out.ai.status === 'degraded') {
        setResult({ kind: 'warn', text: t('workbench.drafts.sentence.degraded', { count: n }) })
      } else if (out.ai.status === 'rule_based') {
        setResult({ kind: 'ok', text: t('workbench.drafts.sentence.doneRule', { count: n }) })
      } else {
        setResult({ kind: 'ok', text: t('workbench.drafts.sentence.doneAi', { count: n }) })
      }
      setText('')
    } catch (e) {
      setResult({ kind: 'err', text: resolveErrorMessage(e, i18n) })
    }
  }

  return (
    <div className="space-y-2" data-testid="sentence-input">
      <div className="text-xs" data-testid="ai-status">
        <span className={`px-1.5 rounded ${aiOn ? 'bg-violet-100 text-violet-800' : 'bg-slate-100 text-slate-600'}`}>{aiNote}</span>
      </div>
      <textarea
        className="w-full border rounded p-2 text-sm"
        rows={2}
        maxLength={MAX_TEXT}
        value={text}
        placeholder={t('workbench.drafts.sentence.placeholder')}
        onChange={e => setText(e.target.value)}
        data-testid="sentence-text"
      />
      <div className="flex items-center gap-2">
        <button type="button" data-testid="sentence-submit"
          disabled={!text.trim() || parse.isPending}
          onClick={submit}
          className="px-3 py-1.5 bg-violet-600 text-white rounded-lg disabled:opacity-40 text-sm">
          {parse.isPending ? t('workbench.drafts.sentence.parsing') : t('workbench.drafts.sentence.submit')}
        </button>
        <span className="text-xs text-slate-500">{t('workbench.drafts.sentence.hint')}</span>
      </div>
      {result && (
        <div role="status" data-testid="sentence-result"
          className={`text-sm rounded px-2 py-1 ${result.kind === 'ok' ? 'bg-emerald-50 text-emerald-800' : result.kind === 'warn' ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-700'}`}>
          {result.text}
        </div>
      )}
    </div>
  )
}
