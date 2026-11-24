// 區域與距離（ADR-038 D5.2：前＝設定區域與同步、後＝物件歸區、算距離、確認套用）。
// MOST 只算公分；TMU 一律在套用（整份存檔）時由引擎重算。算出來的是建議，人確認後才寫進工時表。
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ApiError } from '../../../shared/api/client'
import { resolveErrorMessage } from '../../../shared/i18n/errorMessage'
import { useWiStore } from '../store'
import { useRowNarr } from '../useRowNarr'
import {
  useCategories, useDistanceMutations, useDistanceSettings, useDsxObjects, useSuggestions, useWorksheetObjects,
  keys, useZoneMutations, useZones, type Suggestion, type SyncResult,
} from './api'

type Msg = { kind: 'ok' | 'warn' | 'err'; text: string } | null
const MSG_CLS = { ok: 'bg-emerald-50 text-emerald-800', warn: 'bg-amber-50 text-amber-800', err: 'bg-red-50 text-red-700' }

function MsgLine({ msg, id }: { msg: Msg; id: string }) {
  if (!msg) return null
  return <div role="status" data-testid={id} className={`text-sm rounded px-2 py-1 ${MSG_CLS[msg.kind]}`}>{msg.text}</div>
}

/** 動態 i18n 鍵：值先過白名單格式、再確認鍵存在，否則退回 other（前端慣例）。 */
export function dynKey(i18n: { exists: (k: string) => boolean }, prefix: string, value: string | null | undefined): string {
  // 原因碼含數字（a6_over_threshold、m_over_75），所以白名單放寬到 a-z0-9_
  const v = value && /^[a-z0-9_]+$/.test(value) ? value : 'other'
  return i18n.exists(`${prefix}.${v}`) ? `${prefix}.${v}` : `${prefix}.other`
}

/** detail.rows／wi_row_ids 等結構化錯誤細節（ADR-034 信封的 error.detail）。 */
function errDetail(e: unknown): Record<string, unknown> {
  if (!(e instanceof ApiError)) return {}
  const d = (e.detail as { detail?: Record<string, unknown> } | null)?.detail
  return d && typeof d === 'object' ? d : {}
}

export function DistancePanel({ worksheetId, editable, admin, checkRequired }: {
  worksheetId: string; editable: boolean; admin: boolean; checkRequired: boolean
}) {
  const { t } = useTranslation()
  const unmarked = useWiStore(st => st.rows.filter(r => !r.distanceStatus).length)
  // 核准要做距離檢查的工時表預設展開；其餘（舊工時表）收起，需要時再打開
  const [open, setOpen] = useState(checkRequired)
  // 工時表資料晚到，或寫入後才開啟檢查：轉成 true 時自動展開一次
  useEffect(() => { if (checkRequired) setOpen(true) }, [checkRequired])
  const objects = useWorksheetObjects(worksheetId)
  const sku = objects.data?.sku_id
  // 工時表每次存檔／寫入／套用（revision 變了）後，物件清單與建議都可能跟著變 → 重新讀
  const rev = useWiStore(st => st.revisionNo)
  const qc = useQueryClient()
  const firstRev = useRef(true)
  useEffect(() => {
    if (firstRev.current) { firstRev.current = false; return }  // 第一次掛載時查詢本來就會讀
    void qc.invalidateQueries({ queryKey: keys.wsObjects(worksheetId) })
    void qc.invalidateQueries({ queryKey: keys.suggestions(worksheetId) })
  }, [rev, worksheetId, qc])
  return (
    <section className="bg-white rounded-xl border p-4 space-y-4" data-testid="distance-panel">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold">{t('workbench.distance.title')}</h2>
        <span className={`text-xs ${unmarked && checkRequired ? 'text-red-600' : 'text-slate-500'}`} data-testid="distance-unmarked">
          {t('workbench.distance.unmarked', { count: unmarked })}
          {checkRequired && ` ${t('workbench.distance.checkRequired')}`}
        </span>
        <button type="button" className="ml-auto text-xs px-2 py-1 border rounded" data-testid="distance-toggle" aria-expanded={open}
          onClick={() => setOpen(o => !o)}>
          {open ? t('workbench.distance.collapse') : t('workbench.distance.expand')}
        </button>
      </div>
      {open && <p className="text-xs text-slate-500">{t('workbench.distance.hint')}</p>}
      {open && <>
      {sku && <ZonesBlock sku={sku} ws={worksheetId} editable={editable} />}
      {sku && <ObjectsBlock sku={sku} ws={worksheetId} editable={editable} />}
      <SuggestionsBlock ws={worksheetId} editable={editable} />
      <SettingsBlock admin={admin} />
      </>}
    </section>
  )
}

// ── 區域與同步 ────────────────────────────────────────────────────────────────

function ZonesBlock({ sku, ws, editable }: { sku: string; ws: string; editable: boolean }) {
  const { t, i18n } = useTranslation()
  const zones = useZones(sku)
  const cats = useCategories()
  const [open, setOpen] = useState(false)
  const dsx = useDsxObjects(open && editable)
  const m = useZoneMutations(sku, ws)
  const [name, setName] = useState('')
  const [cat, setCat] = useState('')
  const [obj, setObj] = useState('')
  const [msg, setMsg] = useState<Msg>(null)
  const catName = (id: string) => {
    const c = cats.data?.find(x => x.id === id)
    return c ? (i18n.resolvedLanguage === 'en' ? c.name_en : c.name_zh) : id
  }
  const list = useMemo(() => zones.data?.zones ?? [], [zones.data])
  const snap = zones.data?.last_snapshot
  // 同一個 DSX 物件被多個區域綁定：提示（不擋）
  const dupObjects = useMemo(() => {
    const seen = new Map<string, number>()
    for (const z of list) if (z.dsx_object_id) seen.set(z.dsx_object_id, (seen.get(z.dsx_object_id) ?? 0) + 1)
    return [...seen.entries()].filter(([, n]) => n > 1)
      .map(([id]) => `${id}（${list.filter(z => z.dsx_object_id === id).map(z => z.name).join('、')}）`)
  }, [list])

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setMsg(null)
    try { await fn(); if (ok) setMsg({ kind: 'ok', text: ok }) } catch (e) { setMsg({ kind: 'err', text: resolveErrorMessage(e, i18n) }) }
  }
  async function sync() {
    setMsg(null)
    try {
      const r: SyncResult = await m.sync.mutateAsync(undefined)
      const parts = [t('workbench.distance.zones.synced', { revision: r.snapshot.placement_revision, count: r.snapshot.placement_count })]
      const prev = r.previous_snapshot
      if (prev && prev.dsx_station_id !== r.snapshot.dsx_station_id) parts.push(t('workbench.distance.zones.stationChanged', { from: prev.dsx_station_id, to: r.snapshot.dsx_station_id }))
      if (prev && prev.placement_revision !== r.snapshot.placement_revision) parts.push(t('workbench.distance.zones.revisionChanged', { from: prev.placement_revision, to: r.snapshot.placement_revision }))
      if (r.missing_zone_ids.length) parts.push(t('workbench.distance.zones.missing', { count: r.missing_zone_ids.length }))
      if (r.unbound_zone_ids.length) parts.push(t('workbench.distance.zones.unbound', { count: r.unbound_zone_ids.length }))
      const warn = (prev && prev.dsx_station_id !== r.snapshot.dsx_station_id) || r.missing_zone_ids.length > 0
      setMsg({ kind: warn ? 'warn' : 'ok', text: parts.join(' ') })
    } catch (e) {
      setMsg({ kind: 'err', text: resolveErrorMessage(e, i18n) })
    }
  }

  return (
    <div className="space-y-2" data-testid="zones-block">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium text-sm">{t('workbench.distance.zones.title')}</h3>
        <span className="text-xs text-slate-500" data-testid="zones-snapshot">
          {snap ? t('workbench.distance.zones.lastSync', { at: new Date(snap.synced_at).toLocaleString(), by: snap.synced_by }) : t('workbench.distance.zones.neverSynced')}
        </span>
        {editable && (
          <>
            <button type="button" className="ml-auto text-xs px-2 py-1 border rounded" onClick={() => setOpen(o => !o)} data-testid="zones-edit-toggle">
              {open ? t('workbench.distance.zones.closeEdit') : t('workbench.distance.zones.edit')}
            </button>
            <button type="button" className="text-xs px-2 py-1 bg-sky-600 text-white rounded disabled:opacity-40"
              disabled={m.sync.isPending || list.length === 0} onClick={sync} data-testid="zones-sync">
              {m.sync.isPending ? t('workbench.distance.zones.syncing') : t('workbench.distance.zones.sync')}
            </button>
          </>
        )}
      </div>
      <p className="text-xs text-slate-500">{t('workbench.distance.zones.syncHint')}</p>
      <MsgLine msg={msg} id="zones-msg" />
      {dupObjects.length > 0 && <p className="text-xs text-amber-700 break-all" data-testid="zones-dup">{t('workbench.distance.zones.duplicate', { list: dupObjects.join(', ') })}</p>}
      <table className="text-sm w-full">
        <thead><tr className="text-left text-xs text-slate-500"><th>{t('workbench.distance.zones.name')}</th><th>{t('workbench.distance.zones.category')}</th><th>{t('workbench.distance.zones.dsxObject')}</th><th>{t('workbench.distance.zones.center')}</th><th /></tr></thead>
        <tbody>
          {list.map(z => (
            <tr key={z.id} className="border-t" data-testid="zone-row">
              <td>{z.name}</td>
              <td>{catName(z.category_id)}</td>
              <td className="font-mono text-xs break-all">{z.dsx_object_id ?? '—'}</td>
              <td className="text-xs">{z.center ? `(${z.center.x}, ${z.center.y}, ${z.center.z}) cm` : <span className="text-amber-700">{t('workbench.distance.zones.noCenter')}</span>}</td>
              <td className="text-right">
                {editable && open && (
                  <button type="button" className="text-xs text-red-600 underline"
                    onClick={() => { if (window.confirm(t('workbench.distance.zones.deleteConfirm'))) void run(() => m.remove.mutateAsync(z.id)) }}>
                    {t('workbench.distance.zones.delete')}
                  </button>
                )}
              </td>
            </tr>
          ))}
          {list.length === 0 && <tr><td colSpan={5} className="text-xs text-slate-400 py-1">{t('workbench.distance.zones.empty')}</td></tr>}
        </tbody>
      </table>
      {editable && open && (
        <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="zone-add">
          <select className="border rounded px-1 py-1" value={cat} onChange={e => setCat(e.target.value)} data-testid="zone-add-category">
            <option value="">{t('workbench.distance.zones.pickCategory')}</option>
            {cats.data?.map(c => <option key={c.id} value={c.id}>{i18n.resolvedLanguage === 'en' ? c.name_en : c.name_zh}</option>)}
          </select>
          <input className="border rounded px-2 py-1" maxLength={100} placeholder={t('workbench.distance.zones.namePlaceholder')}
            value={name} onChange={e => setName(e.target.value)} data-testid="zone-add-name" />
          {dsx.data && !dsx.data.available ? (
            <span className="text-xs text-amber-700" data-testid="dsx-unavailable">{t(dynKey(i18n, 'workbench.distance.zones.dsx', dsx.data.reason))}</span>
          ) : (
            <select className="border rounded px-1 py-1" value={obj} onChange={e => setObj(e.target.value)} data-testid="zone-add-object">
              <option value="">{t('workbench.distance.zones.pickObject')}</option>
              {/* DSX 只給中文標籤（DsxObjectOut 沒有 label_en），兩種語系都顯示原文 */}
              {dsx.data?.objects?.map(o => <option key={o.id} value={o.id}>{o.label_zh} ({o.id})</option>)}
            </select>
          )}
          <button type="button" className="px-2 py-1 bg-blue-600 text-white rounded disabled:opacity-40" data-testid="zone-add-submit"
            disabled={!name.trim() || !cat || m.create.isPending}
            onClick={() => void run(async () => {
              await m.create.mutateAsync({ category_id: cat, name: name.trim(), dsx_object_id: obj || null })
              setName(''); setObj('')
            })}>
            {t('workbench.distance.zones.add')}
          </button>
        </div>
      )}
    </div>
  )
}

// ── 物件歸區 ──────────────────────────────────────────────────────────────────

function ObjectsBlock({ sku, ws, editable }: { sku: string; ws: string; editable: boolean }) {
  const { t, i18n } = useTranslation()
  const objects = useWorksheetObjects(ws)
  const zones = useZones(sku)
  const m = useZoneMutations(sku, ws)
  const [msg, setMsg] = useState<Msg>(null)
  const list = objects.data?.objects ?? []
  const unassigned = list.filter(o => !o.zone_id).length
  return (
    <div className="space-y-2" data-testid="objects-block">
      <div className="flex items-center gap-2">
        <h3 className="font-medium text-sm">{t('workbench.distance.objects.title')}</h3>
        <span className="text-xs text-slate-500">{t('workbench.distance.objects.counts', { total: list.length, unassigned })}</span>
      </div>
      <p className="text-xs text-slate-500">{t('workbench.distance.objects.hint')}</p>
      <MsgLine msg={msg} id="objects-msg" />
      <ul className="text-sm divide-y border rounded">
        {list.map(o => (
          <li key={o.vocab_item_id} className="px-2 py-1 flex items-center gap-2" data-testid="object-row">
            <span className="flex-1">{i18n.resolvedLanguage === 'en' && o.name_en ? o.name_en : o.name_zh}</span>
            <span className="text-xs text-slate-400">{t('workbench.distance.objects.usage', { roles: o.roles.join('/'), count: o.row_count })}</span>
            <select className="border rounded px-1 py-0.5 text-sm" disabled={!editable || m.assign.isPending} value={o.zone_id ?? ''}
              data-testid="object-zone"
              onChange={async e => {
                setMsg(null)
                try { await m.assign.mutateAsync([{ vocab_item_id: o.vocab_item_id, zone_id: e.target.value || null }]) }
                catch (err) { setMsg({ kind: 'err', text: resolveErrorMessage(err, i18n) }) }
              }}>
              <option value="">{t('workbench.distance.objects.noZone')}</option>
              {zones.data?.zones?.map(z => <option key={z.id} value={z.id}>{z.name}</option>)}
            </select>
          </li>
        ))}
        {list.length === 0 && <li className="px-2 py-1 text-xs text-slate-400">{t('workbench.distance.objects.empty')}</li>}
      </ul>
    </div>
  )
}

// ── 距離建議、套用、逐列標示 ────────────────────────────────────────────────

const SLOT_ORDER = ['a0', 'a3', 'm3', 'a6']

function SuggestionCell({ s }: { s: Suggestion | undefined }) {
  const { t, i18n } = useTranslation()
  if (!s) return <td className="text-xs text-slate-300">—</td>
  const cls = s.status === 'suggested' ? 'text-slate-800' : s.status === 'needs_ie' ? 'text-amber-700' : 'text-slate-400'
  const src = (s.endpoints as { to?: { source?: string } })?.to?.source
  return (
    <td className={`text-xs ${cls}`} data-testid={`suggestion-${s.slot}`} data-status={s.status}>
      {s.distance_cm != null ? `${s.distance_cm} cm` : '—'}
      {s.status === 'suggested' && s.field && <span className="ml-1 text-slate-500">{t(dynKey(i18n, 'workbench.distance.field', s.field))}</span>}
      {s.status !== 'suggested' && <div>{t(dynKey(i18n, 'workbench.distance.reason', s.reason ?? s.status))}</div>}
      {src && s.status === 'suggested' && <div className="text-[10px] text-slate-400">{t(dynKey(i18n, 'workbench.distance.source', src))}</div>}
    </td>
  )
}

function SuggestionsBlock({ ws, editable }: { ws: string; editable: boolean }) {
  const { t, i18n } = useTranslation()
  const sug = useSuggestions(ws)
  const m = useDistanceMutations(ws)
  const rows = useWiStore(s => s.rows)
  const updateRows = useWiStore(s => s.updateRows)
  const rowNarr = useRowNarr()
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [msg, setMsg] = useState<Msg>(null)
  const [flags, setFlags] = useState<Record<string, string>>({})

  const byRow = useMemo(() => {
    const out = new Map<string, Map<string, Suggestion>>()
    for (const s of sug.data?.items ?? []) {
      if (!out.has(s.wi_row_id)) out.set(s.wi_row_id, new Map())
      out.get(s.wi_row_id)!.set(s.slot, s)
    }
    return out
  }, [sug.data])
  // 一次 compute 的所有建議共用同一個 computed_at（後端在同一交易寫入），套用時拿它比對「看到的那一次」
  const computedAt = sug.data?.items?.[0]?.computed_at
  // 工時表 revision 變了（存檔、寫入、套用）：之前勾的列不一定還能套用，清掉
  const rev = useWiStore(s => s.revisionNo)
  useEffect(() => { setPicked(new Set()) }, [rev])
  const applicable = (id: string) => {
    const m2 = byRow.get(id)
    return !!m2 && [...m2.values()].every(s => s.status === 'suggested')
  }

  async function compute() {
    setMsg(null); setFlags({})
    try { await m.compute.mutateAsync(); setPicked(new Set()) } catch (e) { setMsg({ kind: 'err', text: resolveErrorMessage(e, i18n) }) }
  }
  async function apply() {
    const { revisionNo, hasUnsaved } = useWiStore.getState()
    if (hasUnsaved()) { setMsg({ kind: 'warn', text: t('workbench.drafts.saveFirst') }); return }
    if (revisionNo == null || !computedAt) { setMsg({ kind: 'warn', text: t('workbench.distance.suggest.recompute') }); return }
    setMsg(null); setFlags({})
    try {
      const out = await m.apply.mutateAsync({ base_revision: revisionNo, computed_at: computedAt, wi_row_ids: [...picked] })
      setMsg({ kind: 'ok', text: t('workbench.distance.applied', { count: picked.size, rev: out.revision_no ?? '?' }) })
      setPicked(new Set())
    } catch (e) {
      const code = e instanceof ApiError ? e.code : null
      const d = errDetail(e)
      if (code === 'DISTANCE_NOT_APPLICABLE' && Array.isArray(d.rows)) {
        const f: Record<string, string> = {}
        for (const r of d.rows as Array<{ wi_row_id: string; reason: string }>) f[r.wi_row_id] = r.reason
        setFlags(f)
      } else if (code === 'DISTANCE_SUGGESTION_CHANGED' && Array.isArray(d.wi_row_ids)) {
        setFlags(Object.fromEntries((d.wi_row_ids as string[]).map(id => [id, 'suggestion_changed'])))
      }
      setMsg({ kind: 'err', text: resolveErrorMessage(e, i18n) })
    }
  }
  function mark(id: string, status: 'manual' | 'not_applicable' | null) {
    // 只在表上改，按「儲存」才寫回（W4：存檔只帶改過的列的距離狀態）
    updateRows(r => (r.id === id ? { ...r, distanceStatus: status, distanceStatusChanged: true } : r))
  }

  return (
    <div className="space-y-2" data-testid="suggestions-block">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium text-sm">{t('workbench.distance.suggest.title')}</h3>
        {computedAt && <span className="text-xs text-slate-500">{t('workbench.distance.suggest.computedAt', { at: new Date(computedAt).toLocaleString() })}</span>}
        {editable && (
          <>
            <button type="button" className="ml-auto text-xs px-2 py-1 border rounded disabled:opacity-40" data-testid="distance-compute"
              disabled={m.compute.isPending} onClick={compute}>
              {m.compute.isPending ? t('workbench.distance.suggest.computing') : t('workbench.distance.suggest.compute')}
            </button>
            <button type="button" className="text-xs px-2 py-1 bg-emerald-600 text-white rounded disabled:opacity-40" data-testid="distance-apply"
              disabled={picked.size === 0 || m.apply.isPending} onClick={apply}>
              {t('workbench.distance.suggest.apply', { count: picked.size })}
            </button>
          </>
        )}
      </div>
      <p className="text-xs text-slate-500">{t('workbench.distance.suggest.hint')}</p>
      <MsgLine msg={msg} id="distance-msg" />
      <table className="text-sm w-full">
        <thead>
          <tr className="text-left text-xs text-slate-500">
            <th />{/* 勾選 */}<th>{t('workbench.distance.suggest.seq')}</th><th>{t('workbench.distance.suggest.row')}</th>
            {SLOT_ORDER.map(s => <th key={s}>{s.toUpperCase()}</th>)}
            <th>{t('workbench.distance.suggest.status')}</th><th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const sm = byRow.get(r.id)
            const ok = applicable(r.id)
            return (
              <tr key={r.id} className={`border-t ${flags[r.id] ? 'bg-red-50' : ''}`} data-testid="distance-row" data-flag={flags[r.id]}>
                <td>
                  {editable && ok && r.distanceStatus !== 'not_applicable' && (
                    <input type="checkbox" checked={picked.has(r.id)} data-testid="distance-pick"
                      onChange={() => setPicked(p => { const n = new Set(p); if (n.has(r.id)) n.delete(r.id); else n.add(r.id); return n })} />
                  )}
                </td>
                {/* 存檔時 seq_no＝畫面順序 i+1（savePayload），所以與核准錯誤列出的 #seq_no 一致 */}
                <td className="text-xs text-slate-400">{i + 1}</td>
                <td className="text-xs max-w-[16rem] truncate">{rowNarr(r)}</td>
                {SLOT_ORDER.map(s => <SuggestionCell key={s} s={sm?.get(s)} />)}
                <td className="text-xs" data-testid="distance-status">
                  {r.distanceStatus ? t(`workbench.distance.status.${r.distanceStatus}`) : <span className="text-red-600">{t('workbench.distance.status.none')}</span>}
                  {r.distanceStatusChanged && <span className="ml-1 text-amber-700">{t('workbench.distance.status.unsaved')}</span>}
                  {flags[r.id] && <div className="text-red-600">{t(dynKey(i18n, 'workbench.distance.reason', flags[r.id]))}</div>}
                </td>
                <td className="text-right whitespace-nowrap">
                  {editable && (
                    <>
                      <button type="button" className="text-xs px-1.5 border rounded mr-1" data-testid="distance-mark-na"
                        onClick={() => mark(r.id, 'not_applicable')}>{t('workbench.distance.mark.notApplicable')}</button>
                      <button type="button" className="text-xs px-1.5 border rounded" data-testid="distance-mark-manual"
                        onClick={() => mark(r.id, 'manual')}>{t('workbench.distance.mark.manual')}</button>
                    </>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── 距離設定（建模政策） ─────────────────────────────────────────────────────

function SettingsBlock({ admin }: { admin: boolean }) {
  const { t, i18n } = useTranslation()
  const s = useDistanceSettings()
  const m = useDistanceMutations('')
  const [threshold, setThreshold] = useState('')
  const [z, setZ] = useState('')
  const [msg, setMsg] = useState<Msg>(null)
  // 形狀不對（例：舊環境沒有這個端點）就不顯示，不讓整個工作區壞掉
  if (!s.data || !Array.isArray(s.data.person_offset_cm)) return null
  return (
    <div className="text-xs text-slate-600 space-y-1" data-testid="distance-settings">
      <div>
        {t('workbench.distance.settings.current', {
          threshold: s.data.reach_foot_threshold_cm, offset: s.data.person_offset_cm.join(', '), version: s.data.version_no,
        })}
      </div>
      {admin && (
        <div className="flex flex-wrap items-center gap-2">
          <span>{t('workbench.distance.settings.publishLabel')}</span>
          <input className="border rounded px-1 w-20" type="number" step="0.1" min="0.1" max="300" placeholder={String(s.data.reach_foot_threshold_cm)}
            value={threshold} onChange={e => setThreshold(e.target.value)} data-testid="settings-threshold" />
          <input className="border rounded px-1 w-20" type="number" step="0.1" placeholder={String(s.data.person_offset_cm[2])}
            value={z} onChange={e => setZ(e.target.value)} data-testid="settings-offset-z" />
          <button type="button" className="px-2 py-0.5 border rounded disabled:opacity-40" data-testid="settings-publish"
            disabled={m.publishSettings.isPending || (!threshold && !z)}
            onClick={async () => {
              if (!window.confirm(t('workbench.distance.settings.confirm'))) return
              setMsg(null)
              try {
                const off = [...s.data!.person_offset_cm]
                if (z) off[2] = Number(z)
                await m.publishSettings.mutateAsync({
                  reach_foot_threshold_cm: threshold ? Number(threshold) : s.data!.reach_foot_threshold_cm, person_offset_cm: off,
                })
                setThreshold(''); setZ('')
                setMsg({ kind: 'ok', text: t('workbench.distance.settings.published') })
              } catch (e) { setMsg({ kind: 'err', text: resolveErrorMessage(e, i18n) }) }
            }}>
            {t('workbench.distance.settings.publish')}
          </button>
          <span className="text-slate-400">{t('workbench.distance.settings.onlyNew')}</span>
        </div>
      )}
      <MsgLine msg={msg} id="settings-msg" />
    </div>
  )
}
