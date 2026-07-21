import { useQuery } from '@tanstack/react-query'
import { apiGet } from './client'

/**
 * 目前啟用中的 rule-set（ADR-023 §3.5）。
 *
 * 取代前端寫死的 `ACTIVE_RULE_SET` 常數：值權威在後端 `is_active` 旗標，
 * 前端只讀不猜。**不提供預設 code** —— 拿不到 active 就是設定錯誤，
 * 呼叫端應顯示錯誤而非靜默用某個猜測版本計算（會算出錯誤工時）。
 */
export interface ActiveRuleSet { id: string; code: string; name_zh: string }

export function useActiveRuleSet() {
  return useQuery({
    queryKey: ['rule-set-active'],
    queryFn: () => apiGet<ActiveRuleSet>('/api/v2/rule-sets/active'),
    staleTime: Infinity,
  })
}

/** 便利型：只要 code。未載入完成時為 `undefined`（呼叫端須以此 gate 住計算）。 */
export function useActiveRuleSetCode(): string | undefined {
  return useActiveRuleSet().data?.code
}
