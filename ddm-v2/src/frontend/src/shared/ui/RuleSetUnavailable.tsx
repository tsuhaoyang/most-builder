/**
 * 啟用中 rule-set 或其選項載入失敗時的可行動錯誤態。
 *
 * 必須與「載入中」可區分：後端在無 active 版本時刻意回 500（`NoActiveRuleSet`，
 * ADR-023 §3.5 的預期行為，不靜默寫 NULL）。若兩者共用同一個 spinner，
 * 設定錯誤會表現成永遠轉圈，使用者無從得知該做什麼。
 */
export function RuleSetUnavailable({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error ?? '')
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 space-y-1">
      <p className="font-medium">無法載入 MOST 字典（rule-set），因此無法建模。</p>
      <p className="text-xs">{msg || '未知錯誤'}</p>
      <p className="text-xs text-red-700">
        可能原因：系統目前沒有「啟用中」的字典版本。請至「MOST 字典」頁確認有一個已發布版本被設為啟用中。
      </p>
    </div>
  )
}
