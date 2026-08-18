import { useTranslation } from 'react-i18next'

/**
 * 啟用中 rule-set 或其選項載入失敗時的可行動錯誤態。
 *
 * 必須與「載入中」可區分：後端在無 active 版本時刻意回 500（`NoActiveRuleSet`，
 * ADR-023 §3.5 的預期行為，不靜默寫 NULL）。若兩者共用同一個 spinner，
 * 設定錯誤會表現成永遠轉圈，使用者無從得知該做什麼。
 */
export function RuleSetUnavailable({ error }: { error: unknown }) {
  const { t } = useTranslation()
  const msg = error instanceof Error ? error.message : String(error ?? '')
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 space-y-1">
      <p className="font-medium">{t('ruleSetUnavailable.title')}</p>
      <p className="text-xs">{msg || t('ruleSetUnavailable.unknownError')}</p>
      <p className="text-xs text-red-700">
        {t('ruleSetUnavailable.hint')}
      </p>
    </div>
  )
}
