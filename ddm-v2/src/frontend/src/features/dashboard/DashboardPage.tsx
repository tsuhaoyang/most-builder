// Dashboard — ADR-021 Phase 1 minimal parity with v3 DashboardPage.
// 三張卡：Rule-set 總覽 / 案件狀態統計 / 近期案件。
// 一切數據來自後端 API（前端只聚合渲染，不計算 TMU、不寫死預設值）。
import type { ReactNode } from 'react'
import { useRuleSetList } from '../rule-set/api'
import { useCases, type CaseOut } from '../cases/api'

// ─── Shared bits ──────────────────────────────────────────────────────────────

const STATUS_ZH: Record<string, string> = {
  draft: '草稿',
  approved: '已核准',
  retired: '已退役',
  published: '已發布',
}

const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  retired: 'bg-slate-200 text-slate-600',
  published: 'bg-emerald-100 text-emerald-800',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {STATUS_ZH[status] ?? status}
    </span>
  )
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="bg-white rounded-xl border p-4 flex flex-col gap-3 min-h-[140px]">
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      {children}
    </div>
  )
}

const Loading = () => <p className="text-sm text-slate-400">載入中…</p>
const LoadError = ({ error }: { error: unknown }) => (
  <p className="text-sm text-red-600">載入失敗：{(error as Error).message}</p>
)

// ─── Card 1: Rule-set 總覽 ────────────────────────────────────────────────────
// 後端無單一「啟用」旗標（V1/V2 可同為 published），故不宣稱單一啟用，列出全部。
// MINIMOST_FACTORY_V2 為新工序表預設（dev_seed_v2.py 語意；值權威 ADR-014）。

const DEFAULT_RULE_SET_CODE = 'MINIMOST_FACTORY_V2'

function RuleSetCard() {
  const { data, isLoading, error } = useRuleSetList()

  return (
    <Card title="Rule-set 總覽">
      {isLoading ? (
        <Loading />
      ) : error ? (
        <LoadError error={error} />
      ) : !data?.length ? (
        <p className="text-sm text-slate-400">尚無 rule-set</p>
      ) : (
        <ul className="divide-y">
          {data.map((rs) => (
            <li key={rs.code} className="flex items-center gap-2 py-2">
              <div className="flex-1 min-w-0">
                <span className="block font-mono text-sm font-semibold text-sky-700 truncate">
                  {rs.code}
                </span>
                <span className="block text-xs text-slate-500 truncate">{rs.name_zh}</span>
              </div>
              {rs.code === DEFAULT_RULE_SET_CODE && (
                <span className="px-2 py-0.5 rounded text-xs font-medium bg-sky-100 text-sky-700 whitespace-nowrap">
                  新工序表預設
                </span>
              )}
              <StatusBadge status={rs.status} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

// ─── Card 2: 案件狀態統計 ─────────────────────────────────────────────────────

const COUNT_STYLES: { status: string; label: string; color: string }[] = [
  { status: 'draft',    label: '草稿',   color: 'text-amber-600' },
  { status: 'approved', label: '已核准', color: 'text-emerald-600' },
  { status: 'retired',  label: '已退役', color: 'text-slate-500' },
]

/**
 * P1-C 語意檢查：`/api/v2/cases` 自 P1-A 起已是**案件級聚合**（一筆＝一案件，
 * status＝代表版狀態），故此卡計的是「案件數」而非「版本數」——標題「案件狀態統計」正確，
 * 只在副標把口徑寫明（依代表版＝最新版狀態），避免與版本鏈混淆。
 */
function CaseStatsCard({ items, total, isLoading, error }: {
  items: CaseOut[] | undefined
  /** P1-A 契約的權威案件數（items 受後端 limit 截斷，不可用 items.length 代替） */
  total: number | undefined
  isLoading: boolean
  error: unknown
}) {
  return (
    <Card title="案件狀態統計">
      {isLoading ? (
        <Loading />
      ) : error ? (
        <LoadError error={error} />
      ) : !items?.length ? (
        <p className="text-sm text-slate-400">目前沒有案件</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 flex-1">
            {COUNT_STYLES.map(({ status, label, color }) => (
              <div key={status} className="flex flex-col items-center justify-center bg-slate-50 rounded-lg py-3">
                <span className={`text-2xl font-bold ${color}`}>
                  {items.filter((i) => i.status === status).length}
                </span>
                <span className="text-xs text-slate-500 mt-1">{label}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400">共 {total ?? items.length} 件案件（狀態依最新版）</p>
        </>
      )}
    </Card>
  )
}

// ─── Card 3: 近期案件 ─────────────────────────────────────────────────────────

/** 更新時間 = 最近一次狀態變化（核准時間優先，否則建立時間） */
const updatedAt = (c: CaseOut) => c.approved_at ?? c.created_at

function RecentCasesCard({ items, isLoading, error }: {
  items: CaseOut[] | undefined
  isLoading: boolean
  error: unknown
}) {
  const goCases = () =>
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'case' }))

  return (
    <Card title="近期案件">
      {isLoading ? (
        <Loading />
      ) : error ? (
        <LoadError error={error} />
      ) : !items?.length ? (
        <p className="text-sm text-slate-400">目前沒有案件</p>
      ) : (
        <ul className="divide-y">
          {items.slice(0, 5).map((c) => (
            <li key={c.worksheet_id}>
              <button
                onClick={goCases}
                className="w-full flex items-center gap-2 py-2 text-left hover:bg-slate-50 transition-colors rounded px-1"
              >
                <span className="flex-1 text-sm text-slate-700 truncate">
                  {c.process_name}
                  {c.model_label && <span className="text-slate-500"> · {c.model_label}</span>}
                </span>
                {c.version_count > 1 && (
                  <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 text-xs whitespace-nowrap">
                    {c.version_count} 版
                  </span>
                )}
                <StatusBadge status={c.status} />
                <span className="text-xs text-slate-400 whitespace-nowrap">
                  {new Date(updatedAt(c)).toLocaleDateString('zh-TW')}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const cases = useCases()

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">儀表板</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <RuleSetCard />
        <CaseStatsCard items={cases.data?.items} total={cases.data?.total} isLoading={cases.isLoading} error={cases.error} />
        <RecentCasesCard items={cases.data?.items} isLoading={cases.isLoading} error={cases.error} />
      </div>
    </div>
  )
}
