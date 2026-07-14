// WiItemInspector — WI 大綱子列右抽屜（ADR-022 批次 B-4；對照 v3 WiItemInspector.vue）
// 點 WI 大綱展開子列 → 右側固定抽屜（w-[520px] overlay）：
//   內嵌 SlotBuilder（受控，載入該列 cycle → payloadToState）＋手/頻率/SIMO 顯示
//   「重算並儲存」→ PUT /motion-modules/{id}/rows/{row_index} → 後端重算發新版
//   前端不算 TMU（DISC-02）：預覽 TMU 走後端 calculate（debounce 400ms）。
import { useEffect, useMemo, useState } from 'react'
import { useRuleSetOptions, useVocab, useCalculate } from '../wi-workbench/api'
import { useCreateVocab } from '../master-data/api'
import type { VocabIn } from '../master-data/api'
import { buildPayload, payloadToState, type CycleState } from '../wi-workbench/cycle'
import { TMU_SEC, ACTIVE_RULE_SET } from '../../shared/config'
import { SlotBuilder } from './SlotBuilder'
import { useUpdateModuleRow, type MotionModuleRow } from './api'

const HAND_NAME: Record<string, string> = { RH: '右手', LH: '左手', BH: '雙手' }

export interface WiItemInspectorProps {
  /** WI（category='wi-template'）模組 id 與名稱 */
  moduleId: string
  moduleName: string
  /** 目標子列（0-based；對應版本 rows 索引） */
  rowIndex: number
  /** 該列目前內容（來自 detail 的 current_version_detail.rows[rowIndex]） */
  row: MotionModuleRow
  onClose: () => void
  /** 儲存成功後回呼（父層 toast；查詢已由 mutation invalidate） */
  onSaved?: (newTotalTmu: number) => void
}

export function WiItemInspector({
  moduleId, moduleName, rowIndex, row, onClose, onSaved,
}: WiItemInspectorProps) {
  // ADR-014 值權威：row 重算/發版一律用 V2（與工作台一致；WI rows 為 V2 選項碼快照）
  const { data: opts } = useRuleSetOptions(ACTIVE_RULE_SET)
  const { data: vocab = [] } = useVocab()
  const calc = useCalculate()
  const createVocab = useCreateVocab()
  const updateRow = useUpdateModuleRow()

  // ── 本地編輯狀態（copy-on-write：只在按「重算並儲存」時寫回） ─────────────────
  const [cur, setCur] = useState<CycleState>(() => initState(row))
  const [showHandInMi, setShowHandInMi] = useState(true)
  const [tmu, setTmu] = useState<number | null>(null)   // 後端 calculate 即時預覽
  const [tech, setTech] = useState('')
  const [errMsg, setErrMsg] = useState<string | null>(null)
  const [savedComputed, setSavedComputed] = useState<{ total_tmu: number; eff_tmu: number } | null>(null)

  // 換列（moduleId/rowIndex 變）→ 重新初始化；不因 detail 刷新覆蓋編輯中內容
  useEffect(() => {
    setCur(initState(row))
    setErrMsg(null)
    setSavedComputed(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleId, rowIndex])

  function initState(r: MotionModuleRow): CycleState {
    const next = payloadToState(r.cycle)
    const refs = (r.vocab_refs ?? {}) as Record<string, unknown>
    const vid = (k: string) => (typeof refs[k] === 'string' ? refs[k] as string : '')
    return {
      ...next,
      handCode: r.hand,
      freq: r.frequency,
      nv: { ...next.nv, obj: vid('object_vocab_id'), from: vid('from_vocab_id'), to: vid('to_vocab_id') },
    }
  }

  // ── Debounced backend calculate（400ms；前端不算 TMU） ────────────────────────
  const payload = useMemo(
    () => (opts ? buildPayload(cur, opts.code) : null),
    [cur, opts],
  )
  useEffect(() => {
    if (!payload) { setTmu(null); setTech(''); return }
    const id = setTimeout(() => {
      calc.mutate(payload, {
        onSuccess: r => { setTmu(r.total_tmu); setTech(r.tech_line) },
        onError: () => { setTmu(null); setTech('') },
      })
    }, 400)
    return () => clearTimeout(id)
  }, [JSON.stringify(payload)]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (patch: Partial<CycleState>) => setCur(c => ({ ...c, ...patch }))

  const isSimo = row.simo_pair_index != null
  // 顯示用算術（非 TMU 規則計算）：eff = tmu × freq
  const effTmu = tmu != null ? Math.round(tmu * (cur.freq || 1) * 1000) / 1000 : null
  const ctSec = effTmu != null ? (effTmu * TMU_SEC).toFixed(3) : null

  // ── 重算並儲存：PUT rows/{index} → 後端引擎重算 → 發新版本 ────────────────────
  async function handleSave() {
    if (!opts) return
    setErrMsg(null)
    // vocab_refs：保留原有其他鍵（如 tool_vocab_id），object/from/to 以編輯結果覆寫（空→移除）
    const refs: Record<string, unknown> = { ...(row.vocab_refs ?? {}) }
    const setRef = (k: string, v: string) => { if (v) refs[k] = v; else delete refs[k] }
    setRef('object_vocab_id', cur.nv.obj)
    setRef('from_vocab_id', cur.nv.from)
    setRef('to_vocab_id', cur.nv.to)

    const body: MotionModuleRow = {
      sub_activity: row.sub_activity ?? null,
      hand: cur.handCode,
      frequency: cur.freq,
      simo_pair_index: row.simo_pair_index ?? null,  // SIMO 配對保留不動（Inspector 僅顯示）
      vocab_refs: refs,
      cycle: buildPayload(cur, opts.code),
    }
    try {
      const detail = await updateRow.mutateAsync({ id: moduleId, rowIndex, row: body })
      const newRow = detail.rows[rowIndex] as MotionModuleRow | undefined
      const comp = newRow?.computed ?? null
      if (comp) setSavedComputed({ total_tmu: comp.total_tmu, eff_tmu: comp.eff_tmu })
      onSaved?.(detail.total_tmu)
    } catch (err) {
      // 422 detail（EMPTY_ROWS / SIMO_PAIR_INVALID / Sequence 驗證）原樣顯示
      setErrMsg((err as Error).message)
    }
  }

  const saving = updateRow.isPending

  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="wi-item-inspector">
      {/* overlay */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      {/* drawer */}
      <div className="relative w-[520px] max-w-full h-full bg-white shadow-2xl border-l flex flex-col">
        {/* header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="min-w-0">
            <h3 className="font-semibold text-base">動作模組詳情</h3>
            <p className="text-xs text-slate-400 truncate" title={moduleName}>
              {moduleName} · 第 {rowIndex + 1} 列
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 text-xl leading-none px-1"
            aria-label="關閉"
          >✕</button>
        </div>

        {/* body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!opts && <p className="text-sm text-slate-500">載入 rule-set…</p>}
          {opts && (
            <>
              {/* 列摘要：句子＋SIMO 標記 */}
              <div className="rounded-lg border px-3 py-2 bg-slate-50 space-y-1">
                <p className="text-sm text-slate-700">
                  {row.narrative_zh ?? row.sub_activity ?? '（無敘述）'}
                </p>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  <span>{cur.seq === 'GM' ? '一般移動' : '控制移動'}</span>
                  <span>{HAND_NAME[cur.handCode] ?? cur.handCode}</span>
                  {isSimo && (
                    <span className="text-orange-600 font-medium">
                      SIMO 從屬（主列 #{(row.simo_pair_index ?? 0) + 1}，貢獻 0）
                    </span>
                  )}
                </div>
              </div>

              {/* 手 / 頻率 */}
              <div className="flex items-center gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <span className="text-slate-500">使用手</span>
                  <select
                    className="border rounded px-2 py-1 text-sm"
                    value={cur.handCode}
                    onChange={e => set({ handCode: e.target.value })}
                  >
                    <option value="RH">右手</option>
                    <option value="LH">左手</option>
                    <option value="BH">雙手</option>
                  </select>
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <span className="text-slate-500">頻率</span>
                  <input
                    type="number" min={1}
                    className="border rounded w-20 px-2 py-1 text-sm"
                    value={cur.freq}
                    onChange={e => set({ freq: parseInt(e.target.value) || 1 })}
                    data-testid="inspector-freq"
                  />
                </label>
              </div>

              {/* 內嵌 SlotBuilder（受控） */}
              <div className="rounded-lg border bg-slate-50/50 p-2">
                <SlotBuilder
                  value={cur}
                  onChange={set}
                  opts={opts}
                  vocab={vocab}
                  onCreateVocab={(kind, name, assign) =>
                    createVocab.mutate({ kind, name_zh: name } as VocabIn, {
                      onSuccess: v => assign(v.id),
                    })
                  }
                  showHandInMi={showHandInMi}
                  onShowHandInMiChange={setShowHandInMi}
                  tmu={tmu}
                  tech={tech}
                />
              </div>

              {/* 後端試算預覽（權威值＝儲存後版本 rows.computed） */}
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border px-3 py-2 text-sm"
                style={{ background: 'linear-gradient(135deg,#f8fbff 0%,#f0f7ff 100%)', borderColor: '#d4e5f7' }}>
                <span>
                  <span className="text-slate-400 text-xs mr-1">基礎 TMU</span>
                  <b style={{ color: '#1a73e8' }}>{tmu ?? '—'}</b>
                </span>
                <span>
                  <span className="text-slate-400 text-xs mr-1">有效 TMU</span>
                  <b className="text-red-600">{effTmu ?? '—'}</b>
                </span>
                <span>
                  <span className="text-slate-400 text-xs mr-1">CT(秒)</span>
                  {ctSec ?? '—'}
                </span>
                {tech && <span className="font-mono text-xs text-slate-400">{tech}</span>}
              </div>

              {/* 儲存結果（後端新版本的權威 computed） */}
              {savedComputed && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700"
                  data-testid="inspector-saved">
                  已重算並發布新版本：本列 Base <b>{savedComputed.total_tmu}</b> TMU · Eff{' '}
                  <b>{savedComputed.eff_tmu}</b> TMU
                </div>
              )}

              {/* 錯誤（422 EMPTY_ROWS / SIMO 等原樣顯示） */}
              {errMsg && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 break-all"
                  data-testid="inspector-error">
                  儲存失敗：{errMsg}
                </div>
              )}

              <p className="text-xs text-slate-400">
                此微調僅套用於目前 WI（快照複本），不會變更動作清單中的原始動作；儲存後 WI 發布新版本並標記「已微調」。
              </p>
            </>
          )}
        </div>

        {/* footer */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t">
          <button
            onClick={onClose}
            className="px-4 py-1.5 border rounded-lg text-sm text-slate-600 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !opts}
            className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium disabled:opacity-40"
          >
            {saving ? '重算中…' : '重算並儲存'}
          </button>
        </div>
      </div>
    </div>
  )
}
