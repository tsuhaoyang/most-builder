// DSX a3 距離查詢（MVP；契約草案 §3.1 `POST /api/v2/dsx/a3-distance`）
// 型別已改走 OpenAPI 產生的 `shared/types/api.d.ts`（`npm run gen:api` 產出）——不可手改該檔。
//
// ⚠️ `A3DistanceOut` 是**扁平 optional schema**，不是判別聯合型別：`available: boolean`
// 與其餘欄位（`distance_cm`／`provisional`／`measure_from_mode`／`warnings`／`queried_at`／
// `reason`）全部各自 optional，TypeScript **不會**因為 `available === true` 就自動窄化出
// `distance_cm` 一定非 null。呼叫端讀值前要自己判斷（見 `DsxA3Suggestion.tsx` 的
// `result.available && result.distance_cm != null` 寫法），不能只信 `available` 這個布林。
//
// I1（ADR-031）：DSX 只送公分數字，不算 TMU／band index——這裡的 distance_cm 是原始值，
// 不是 band 值；填入 a3.reach_cm／a3.foot_cm 前要先經過 cmToBandValue 落檔。
// D4：這是建議值，`provisional` 應為 true，前端不得自動寫入既有欄位，需使用者明確點選。
//
// `wi_row_id` 選填（契約草案 §3.1 掛載點更正）：掛載點在 `WiWorkbench.tsx` 的建立器
// 面板，多數查詢發生在列還沒存檔、沒有真實 wi_row_id 時；有帶才會補寫出處快照。
import { useMutation } from '@tanstack/react-query'
import { apiPost } from '../../shared/api/client'
import type { components } from '../../shared/types/api'

export type DsxA3DistanceRequest = components['schemas']['A3DistanceIn']
export type DsxA3DistanceResponse = components['schemas']['A3DistanceOut']
export type DsxA3DistanceUnavailableReason = NonNullable<DsxA3DistanceResponse['reason']>

export const useDsxA3Distance = () =>
  useMutation({
    mutationFn: (body: DsxA3DistanceRequest) =>
      apiPost<DsxA3DistanceResponse>('/api/v2/dsx/a3-distance', body),
  })
