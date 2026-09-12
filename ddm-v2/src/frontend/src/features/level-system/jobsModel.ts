// 作業模型型別（ADR-035 D10 §5 F2）。作業版 UI 的反投影結果；store 仍是唯一真相。
export interface Job {
  id: string                 // chainKey（穩定）
  name: string | null        // wi_group（顯示時 ?? rowNarr(firstStep)）
  steps: string[]            // 非通用成員 rowId（依 rows 序）
  generalSteps: string[]     // 附掛的通用步驟 rowId
  row: number                // 主排（lo）
  rowHi: number | null       // 最晚排（hi>lo 時）
  discrete: string | null    // 離散層級（'1/3'），不參與排編號
  sameStation: boolean       // 作業＝cub
  samePerson: boolean        // 全部同一 wcub 且該 wcub 成員 ⊆ steps
  offline: boolean           // 全部 offline
  pin: number | null         // 全部同一 station_pin
  cubLabel: string | null
  subLabel: string | null
  wcubLabel: string | null
}

export interface StepTag {
  cub?: string
  wcub?: string
  offline?: boolean
  pin?: number
  segment?: string
  generalRole?: string
  mergeLock?: boolean
  actionType?: string
  coefficient?: number
}

export interface JobModel {
  jobs: Job[]
  stepTags: Record<string, StepTag>
  layers: number[]           // 去重排序後的顯示排號（1..k）
}
