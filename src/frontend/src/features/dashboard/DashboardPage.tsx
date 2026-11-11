// Dashboard — ADR-021 Phase 1 minimal parity with v3 DashboardPage.
// 三張卡：Rule-set 總覽 / 案件狀態統計 / 近期案件。
// 一切數據來自後端 API（前端只聚合渲染，不計算 TMU、不寫死預設值）。
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useRuleSetVersions } from '../dictionary/api'
import { useCases, type CaseOut } from '../cases/api'
import { useStatusLabel } from '../cases/status'

// ─── Shared bits ──────────────────────────────────────────────────────────────
// 狀態文字共用 `cases/status` 的 `useStatusLabel`（ADR-032 Phase A 第 4 批）；
// 這裡只留本卡自己的配色（多一個 `published`，案件那邊沒有這個狀態）。

const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  retired: 'bg-slate-200 text-slate-600',
  published: 'bg-emerald-100 text-emerald-800',
}

function StatusBadge({ status }: { status: string }) {
  const statusLabel = useStatusLabel()
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {statusLabel(status)}
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

const Loading = () => {
  const { t } = useTranslation()
  return <p className="text-sm text-slate-400">{t('dashboard.loading')}</p>
}
const LoadError = ({ error }: { error: unknown }) => {
  const { t } = useTranslation()
  return <p className="text-sm text-red-600">{t('dashboard.loadFailed', { message: (error as Error).message })}</p>
}

// ─── Card 1: MOST 字典總覽 ────────────────────────────────────────────────────
// 「新工序表預設」＝後端 is_active 旗標（ADR-023 §3.5），不再由前端寫死版本 code。

function RuleSetCard() {
  const { t } = useTranslation()
  const { data, isLoading, error } = useRuleSetVersions()

  return (
    <Card title={t('dashboard.ruleSetCard')}>
      {isLoading ? (
        <Loading />
      ) : error ? (
        <LoadError error={error} />
      ) : !data?.length ? (
        <p className="text-sm text-slate-400">{t('dashboard.noRuleSet')}</p>
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
              {rs.is_active && (
                <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-800 whitespace-nowrap">
                  {t('dashboard.ruleSetActive')}
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

// 標籤走共用的 `status.*`（見檔頭），這裡只列出要統計的狀態與其顏色。
const COUNT_STYLES: { status: string; color: string }[] = [
  { status: 'draft',    color: 'text-amber-600' },
  { status: 'approved', color: 'text-emerald-600' },
  { status: 'retired',  color: 'text-slate-500' },
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
  const { t } = useTranslation()
  const statusLabel = useStatusLabel()
  return (
    <Card title={t('dashboard.caseStatsCard')}>
      {isLoading ? (
        <Loading />
      ) : error ? (
        <LoadError error={error} />
      ) : !items?.length ? (
        <p className="text-sm text-slate-400">{t('dashboard.noCases')}</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 flex-1">
            {COUNT_STYLES.map(({ status, color }) => (
              <div key={status} className="flex flex-col items-center justify-center bg-slate-50 rounded-lg py-3">
                <span className={`text-2xl font-bold ${color}`}>
                  {items.filter((i) => i.status === status).length}
                </span>
                <span className="text-xs text-slate-500 mt-1">{statusLabel(status)}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-slate-400">{t('dashboard.caseTotal', { count: total ?? items.length })}</p>
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
  const { t, i18n } = useTranslation()
  const goCases = () =>
    window.dispatchEvent(new CustomEvent('ddm:switch-tab', { detail: 'case' }))

  return (
    <Card title={t('dashboard.recentCasesCard')}>
      {isLoading ? (
        <Loading />
      ) : error ? (
        <LoadError error={error} />
      ) : !items?.length ? (
        <p className="text-sm text-slate-400">{t('dashboard.noCases')}</p>
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
                    {t('dashboard.versionCount', { count: c.version_count })}
                  </span>
                )}
                <StatusBadge status={c.status} />
                <span className="text-xs text-slate-400 whitespace-nowrap">
                  {new Date(updatedAt(c)).toLocaleDateString(i18n.language)}
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
  const { t } = useTranslation()
  const cases = useCases()

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">{t('dashboard.heading')}</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <RuleSetCard />
        <CaseStatsCard items={cases.data?.items} total={cases.data?.total} isLoading={cases.isLoading} error={cases.error} />
        <RecentCasesCard items={cases.data?.items} isLoading={cases.isLoading} error={cases.error} />
      </div>
    </div>
  )
}
