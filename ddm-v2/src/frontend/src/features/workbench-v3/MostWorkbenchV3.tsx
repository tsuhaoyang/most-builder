// MOST 工作台 — v3 單頁版（ADR-022 批次 B：移除三 tab shell，修正 ADR-021 誤讀）
// v3 導覽的「MOST 工作台」是單頁 /most-workbench；三層 tab 版是實驗性隱藏頁、非驗證 UX。
// 單頁內容＝ActionModuleWorkspace（建立器 → 動作清單 → WI 大綱 → WiItemInspector）。
//
// 斷路備註：WIPoolWorkspace（WI 組成）已由 WI 大綱取代；ProcessWorkspace（製程途程）
// 的「WI 實體化進工時表」能力將於批次 E 搬入案件編輯情境後移除——兩檔保留但不掛載。
import { ActionModuleWorkspace } from './ActionModuleWorkspace'

export function MostWorkbenchV3() {
  return (
    <div className="h-full">
      <ActionModuleWorkspace />
    </div>
  )
}
