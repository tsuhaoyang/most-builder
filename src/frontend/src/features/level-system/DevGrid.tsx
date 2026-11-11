// ADR-035 D10 F5：開發者網格（dev grid）。只在勾「開發者」時顯示；把 report.tasks[]（include_tasks=1
// 才有）原封不動列成 24 欄表格。純顯示，不寫回。表頭順序＝後端 emit.COLUMNS（前端硬編，後端才是權威）。
import type { LbReport } from './api'

// 後端 emit.COLUMNS 的 24 欄（順序凍結，ADR-035 契約）。
const COLUMNS = [
  'task_id', 'action', 'part_id', 'group', 'atomic_group', 'duration', 'predecessors',
  'station_name', 'action_type', 'complexity_level', 'adjustable', 'fixed_station',
  'offline_flag', 'tool_id', 'tool_action', 'divisible', 'p2', 'quantity', 'segment',
  'qty_scope', 'duration_basis', 'source_wi_row_id', 'role_type', 'general_role',
] as const

interface Props {
  report: LbReport | null
}

export function DevGrid({ report }: Props) {
  const tasks = report?.tasks ?? []
  return (
    <div className="overflow-x-auto border border-slate-200 rounded-lg" data-testid="dev-grid">
      <table className="text-[11px] border-collapse w-max">
        <thead>
          <tr className="bg-slate-100 text-slate-600">
            {COLUMNS.map(c => (
              <th key={c} className="border border-slate-200 px-1.5 py-0.5 text-left whitespace-nowrap font-mono">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tasks.map((row, i) => (
            <tr key={i} className="odd:bg-white even:bg-slate-50">
              {COLUMNS.map(c => (
                <td key={c} className="border border-slate-200 px-1.5 py-0.5 whitespace-nowrap font-mono">
                  {String((row as Record<string, unknown>)[c] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
