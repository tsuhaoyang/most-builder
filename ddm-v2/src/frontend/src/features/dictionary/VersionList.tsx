import { useMemo, useState, type ReactNode } from 'react'
import { ConfirmDialog } from './ConfirmDialog'
import { canEdit as canEditFn, canPublish as canPublishFn, useMe } from '../../shared/auth/useMe'
import { describeInUse, exportRuleSet, useRuleSetVersions, useVersionMutations, type RuleSetSummary } from './api'

/**
 * L1：字典版本清單（對照 v3 DictionariesPage 版本區）。
 *
 * 與 v3 的差異：v3 狀態只有「啟用/草稿」兩態，v2 是 `status`（draft/published/retired）
 * × `is_active` 兩維（ADR-023 §3.2），故狀態欄顯示 status 徽章，active 另加綠色「啟用中」。
 */

const STATUS_ZH: Record<string, string> = { draft: '草稿', published: '已發布', retired: '已封存' }
const STATUS_STYLE: Record<string, string> = {
  draft: 'bg-amber-100 text-amber-800',
  published: 'bg-sky-100 text-sky-800',
  retired: 'bg-slate-200 text-slate-600',
}
const PROVENANCE_ZH: Record<string, string> = {
  certified_import: '認證匯入',
  manual: '手動建立',
  cloned: '複製版本',
}

interface ConfirmState {
  label: string
  title: string
  body: ReactNode
  confirmLabel: string
  tone: 'warn' | 'danger'
  requireText?: string
  run: () => Promise<unknown>
  /** 把特定錯誤轉成人話（回 null＝沿用一般訊息）。 */
  describeError?: (err: unknown) => string | null
}

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString('zh-TW') : '—'

function StatusCell({ v }: { v: RuleSetSummary }) {
  return (
    <span className="flex flex-wrap items-center gap-1">
      <span className={`px-2 py-0.5 rounded text-xs ${STATUS_STYLE[v.status] ?? 'bg-slate-100'}`}>
        {STATUS_ZH[v.status] ?? v.status}
      </span>
      {v.is_active && (
        <span className="px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-800">啟用中</span>
      )}
    </span>
  )
}

const Btn = ({ tone = 'plain', ...p }: { tone?: 'plain' | 'ok' | 'warn' | 'danger' } & React.ButtonHTMLAttributes<HTMLButtonElement>) => {
  const tones = {
    plain: 'border-slate-300 text-slate-700 hover:bg-slate-50',
    ok: 'border-emerald-500 bg-emerald-500 text-white hover:bg-emerald-600',
    warn: 'border-amber-500 bg-amber-500 text-white hover:bg-amber-600',
    danger: 'border-red-300 text-red-600 hover:bg-red-50',
  }
  return (
    <button
      {...p}
      className={`px-2 py-1 rounded border text-xs disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]} ${p.className ?? ''}`}
    />
  )
}

export function VersionList({ onOpen }: { onOpen: (code: string) => void }) {
  const { data: versions = [], isLoading, error } = useRuleSetVersions()
  const { data: me } = useMe()
  const canEdit = canEditFn(me)
  const canPublish = canPublishFn(me)
  const { publish, activate, retire, unretire, remove } = useVersionMutations()
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const [busy, setBusy] = useState(false)
  const [cErr, setCErr] = useState<string | null>(null)

  const active = useMemo(() => versions.find(v => v.is_active) ?? null, [versions])

  const run = async (label: string, fn: () => Promise<unknown>) => {
    try {
      await fn()
      setMsg({ tone: 'ok', text: `${label}成功` })
    } catch (e) {
      setMsg({ tone: 'err', text: `${label}失敗：${(e as Error).message}` })
    }
  }

  const runConfirmed = async () => {
    if (!confirm) return
    setBusy(true); setCErr(null)
    try {
      await confirm.run()
      setMsg({ tone: 'ok', text: `${confirm.label}成功` })
      setConfirm(null)
    } catch (e) {
      setCErr(confirm.describeError?.(e) ?? (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  /**
   * activate 的確認文案必須說明「不回溯」：`activate` 只 UPDATE `rule_sets.is_active`，
   * 不碰任何 module/cycle；而 publish 已把 `computed.total_tmu` 寫進 rows JSON 並凍結
   * `rule_set_id`。故誤按後切回去不會修正期間內已落盤的值。
   */
  const askActivate = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: '啟用',
      title: '啟用此字典版本？',
      tone: 'warn',
      confirmLabel: '確認啟用',
      run: () => activate.mutateAsync(v.code),
      body: (
        <>
          <p>將把 <span className="font-mono">{v.code}</span> 設為唯一啟用版本{active ? <>，並停用目前的 <span className="font-mono">{active.code}</span></> : null}。</p>
          <p className="text-amber-800">
            此後<b>新建模將以本版持久化計算值</b>；切回不會回溯修正已建立的資料——
            期間內建立/發布的內容需人工找出並重發。
          </p>
        </>
      ),
    })
  }

  /** 封存可逆（D3b 起有 unretire）→ 一般確認即可，不要求打字。 */
  const askRetire = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: '封存',
      title: '封存此字典版本？',
      tone: 'warn',
      confirmLabel: '確認封存',
      run: () => retire.mutateAsync(v.code),
      body: (
        <>
          <p>將把 <span className="font-mono">{v.code}</span> 標記為已封存，之後不再可被選用。</p>
          <p>封存後<b>可再解除封存</b>回到「已發布」狀態。</p>
          <p className="text-xs text-slate-500">
            （已引用本版的既有資料仍可正常載入重算，回放不受影響。）
          </p>
        </>
      ),
    })
  }

  /** 解除封存：retired → published，**is_active 維持 false**（解封 ≠ 啟用）。 */
  const askUnretire = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: '解除封存',
      title: '解除封存此字典版本？',
      tone: 'warn',
      confirmLabel: '確認解除封存',
      run: () => unretire.mutateAsync(v.code),
      body: (
        <>
          <p>將把 <span className="font-mono">{v.code}</span> 從「已封存」改回「已發布」。</p>
          <p className="text-amber-800">
            解除封存後<b>仍不是啟用中版本</b>；若要讓新建模改用本版，需另外按「啟用」。
          </p>
        </>
      ),
    })
  }

  /** 刪除是本頁唯一真正不可逆的操作（實體刪除＋13 張子表級聯）→ 強制打字確認。 */
  const askDelete = (v: RuleSetSummary) => {
    setCErr(null)
    setConfirm({
      label: '刪除',
      title: '刪除此草稿版本？',
      tone: 'danger',
      confirmLabel: '確認刪除',
      requireText: v.code,
      run: () => remove.mutateAsync(v.code),
      // 被引用時後端回 RULE_SET_IN_USE，把各表引用筆數說成人話
      describeError: describeInUse,
      body: (
        <>
          <p>將<b>永久刪除</b>草稿 <span className="font-mono">{v.code}</span> 及其所有規則資料。</p>
          <p className="text-red-700"><b>此操作不可逆</b>，且無法復原已刪除的內容。</p>
          <p className="text-xs text-slate-500">
            （若本草稿已被工時表或動作模組引用，系統會擋下刪除並告知引用筆數。）
          </p>
        </>
      ),
    })
  }

  const doExport = async (code: string) => {
    try {
      const data = await exportRuleSet(code)
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
      )
      const a = document.createElement('a')
      a.href = url
      a.download = `${code}.json`
      a.click()
      URL.revokeObjectURL(url)
      setMsg({ tone: 'ok', text: `已匯出 ${code}.json` })
    } catch (e) {
      setMsg({ tone: 'err', text: `匯出失敗：${(e as Error).message}` })
    }
  }

  if (isLoading) return <div className="bg-white rounded-xl border p-6 text-slate-500">載入字典版本…</div>
  if (error) return <div className="bg-white rounded-xl border p-6 text-red-600">載入失敗：{(error as Error).message}</div>

  return (
    <div className="space-y-4" data-testid="dict-version-list">
      <h2 className="text-lg font-semibold">字典版本管理</h2>

      {msg && (
        <div className={`rounded-lg border px-3 py-2 text-sm ${msg.tone === 'ok' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {msg.text}
        </div>
      )}

      {/* 啟用中版本卡片（v3 active-card） */}
      {active && (
        <div className="bg-white rounded-xl border" data-testid="dict-active-card">
          <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b">
            <span className="px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-800">啟用中</span>
            <span className="font-medium">{active.name_zh}</span>
            <span className="font-mono text-xs text-slate-400">{active.code}</span>
            <div className="ml-auto flex gap-2">
              <Btn onClick={() => onOpen(active.code)}>編輯字典</Btn>
              <Btn onClick={() => void doExport(active.code)}>匯出 JSON</Btn>
            </div>
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-1 px-4 py-2 text-xs text-slate-500">
            <span>來源：{active.provenance ? PROVENANCE_ZH[active.provenance] ?? active.provenance : '—'}</span>
            <span>建立：{fmtDate(active.created_at)}</span>
            <span>備註：{active.notes || '—'}</span>
          </div>
        </div>
      )}

      {/* 版本表格 */}
      <div className="bg-white rounded-xl border overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-100 text-left">
              <th className="p-2 font-medium">版本名稱</th>
              <th className="p-2 font-medium">狀態</th>
              <th className="p-2 font-medium">來源</th>
              <th className="p-2 font-medium">建立時間</th>
              <th className="p-2 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {versions.map(v => (
              <tr key={v.code} className="border-t align-top" data-testid={`dict-version-${v.code}`}>
                <td className="p-2">
                  <span className="block">{v.name_zh}</span>
                  <span className="block font-mono text-xs text-slate-400">{v.code}</span>
                </td>
                <td className="p-2"><StatusCell v={v} /></td>
                <td className="p-2 text-slate-600">
                  {v.provenance ? PROVENANCE_ZH[v.provenance] ?? v.provenance : '—'}
                </td>
                <td className="p-2 text-slate-600 whitespace-nowrap">{fmtDate(v.created_at)}</td>
                <td className="p-2">
                  <div className="flex flex-wrap gap-1">
                    {v.status === 'retired' ? (
                      <>
                        <Btn onClick={() => onOpen(v.code)}>檢視</Btn>
                        <Btn tone="ok" disabled={!canPublish} onClick={() => askUnretire(v)}>解除封存</Btn>
                      </>
                    ) : (
                      <Btn
                        onClick={() => onOpen(v.code)}
                        disabled={!canEdit}
                        title={
                          v.provenance === 'certified_import'
                            ? '認證匯入版本不可直接編輯，將建立草稿'
                            : v.status !== 'draft'
                              ? '此版本已發布，編輯時會先建立草稿'
                              : undefined
                        }
                      >
                        編輯
                      </Btn>
                    )}

                    {v.status === 'draft' && (
                      <Btn tone="ok" disabled={!canPublish} onClick={() => void run('發布', () => publish.mutateAsync(v.code))}>
                        發布
                      </Btn>
                    )}

                    {v.status === 'published' && !v.is_active && (
                      <Btn tone="ok" disabled={!canPublish} onClick={() => askActivate(v)}>
                        啟用
                      </Btn>
                    )}

                    {v.status === 'published' && !v.is_active && (
                      <Btn tone="warn" disabled={!canPublish} onClick={() => askRetire(v)}>
                        封存
                      </Btn>
                    )}

                    {/* 僅 draft 可刪（D3b）；本頁唯一不可逆操作 → type-to-confirm */}
                    {v.status === 'draft' && (
                      <Btn tone="danger" disabled={!canEdit} onClick={() => askDelete(v)}>
                        刪除
                      </Btn>
                    )}

                    {/* 匯出為唯讀操作，viewer 亦可用 */}
                    <Btn onClick={() => void doExport(v.code)}>匯出</Btn>
                  </div>
                </td>
              </tr>
            ))}
            {versions.length === 0 && (
              <tr><td colSpan={5} className="p-4 text-slate-400">尚無字典版本</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          body={confirm.body}
          confirmLabel={confirm.confirmLabel}
          tone={confirm.tone}
          requireText={confirm.requireText}
          busy={busy}
          error={cErr}
          onCancel={() => { setConfirm(null); setCErr(null) }}
          onConfirm={() => void runConfirmed()}
        />
      )}
    </div>
  )
}
