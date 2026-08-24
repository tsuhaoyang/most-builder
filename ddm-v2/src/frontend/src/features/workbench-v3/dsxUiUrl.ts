// DSX 3D 擺放介面網址（內部／工程用；GET /api/v2/dsx/ui-url）
// 只回傳一個網址（未設定則 null）——前端不猜測、不寫死，入口是否可點完全依這個查詢結果。
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../../shared/api/client'
import type { components } from '../../shared/types/api'

export type DsxUiUrlResponse = components['schemas']['DsxUiUrlOut']

export const useDsxUiUrl = () =>
  useQuery({
    queryKey: ['dsx-ui-url'],
    queryFn: () => apiGet<DsxUiUrlResponse>('/api/v2/dsx/ui-url'),
    staleTime: 300_000,
  })
