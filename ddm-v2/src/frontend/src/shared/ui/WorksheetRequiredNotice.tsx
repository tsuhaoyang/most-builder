// ADR-021 Phase 3：無 activeWs 時的統一空狀態提示。
// 工序表情境只能從「分析案件」進入（編輯工時表／新建案件），
// 所以提示一律導向分析案件 tab（dispatch ddm:switch-tab → 'case'）。

export function goToCases() {
  window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'case' }))
}

/** 前往分析案件的跳轉按鈕（供各空狀態重用） */
export function GoToCasesButton() {
  return (
    <button
      onClick={goToCases}
      className="px-3 py-1.5 bg-sky-600 text-white rounded text-sm hover:bg-sky-700 transition-colors"
    >
      前往分析案件
    </button>
  )
}

/** 整頁卡片版空狀態（Level System、wi tab 直接落地時使用） */
export function WorksheetRequiredNotice() {
  return (
    <div className="bg-white rounded-xl border p-10 flex flex-col items-center gap-3">
      <span className="text-2xl" aria-hidden>📋</span>
      <p className="text-sm text-slate-500">請先從分析案件開啟工時表</p>
      <GoToCasesButton />
    </div>
  )
}
