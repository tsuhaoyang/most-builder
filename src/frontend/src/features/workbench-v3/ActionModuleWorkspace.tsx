// MOST 工作台單頁 — v3 MostWorkbenchPage 對等（ADR-022 批次 B；修正 ADR-021 誤讀）
// 由上而下：AI 快速建模列 → 摘要列（九欄） → 交錯句型列 → WI 語句
//          → 動作清單（category='action'，個別動作各自 TMU）
//          → WI 大綱（category='wi-template'；勾動作建 WI；子列開 WiItemInspector）
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { useRuleSetOptions, useVocab, useCalculate } from '../wi-workbench/api'
import { useCreateVocab } from '../master-data/api'
import type { VocabIn } from '../master-data/api'
import { defaultCycle, buildPayload, migrateSeqState, payloadToState, shortNarr, type CycleState } from '../wi-workbench/cycle'
import { ActionCard } from '../wi-workbench/ActionCard'
import type { AiCycleDraft, AiPlannedAction, ReviewBatchOut } from '../wi-workbench/aiTypes'
import { TMU_SEC } from '../../shared/config'
import i18n from '../../shared/i18n/i18n'
import { useActiveRuleSet } from '../../shared/api/useActiveRuleSet'
import { RuleSetUnavailable } from '../../shared/ui/RuleSetUnavailable'
import { apiGet, apiPost } from '../../shared/api/client'
import { useMe, canEdit } from '../../shared/auth/useMe'
import { SlotBuilder, aIsFilled } from './SlotBuilder'
import {
  compatMatchesDraft, nlDraftPatch, nlDraftPatchFillEmpty, sourceBadge,
  type NlDraftRes,
} from './nlDraft'
import { MiCompositionTable } from './MiCompositionTable'
import {
  useMotionModules,
  useCreateModule,
  useUpdateModule,
  useDeleteModule,
  useCloneModule,
  usePublishModule,
  useCreateWiTemplate,
  useUpdateModuleRow,
  apiErrorMessage,
  MODULE_QUERY_KEY,
  type MotionModuleSummary,
  type MotionModuleRow,
} from './api'
import { WiOutlineSection } from './WiOutline'
import { WiItemInspector } from './WiItemInspector'

const HAND_CODES = ['RH', 'LH', 'BH'] as const

/** hand code → 顯示名（未知 code 原樣顯示，與其他清單一致） */
function handName(code: string): string {
  return (HAND_CODES as readonly string[]).includes(code) ? i18n.t(`workbench.hand.${code}`) : code
}

// ── 格位是否有內容（不含情境欄；存檔擋空與 NL 判斷共用） ───────────────────────
function hasSlotContent(c: CycleState): boolean {
  return aIsFilled(c.a0) || aIsFilled(c.a3) || aIsFilled(c.a6)
    || !!c.b1 || !!c.b4 || !!c.g || !!c.p_base || c.p_addons.length > 0
    || !!c.m.verb || c.x !== 'x_none' || c.i !== 'i_none'
}

// ── 編輯器是否有內容（NL 覆蓋/填空判斷，audit §1.13） ─────────────────────────
function hasEditorContent(c: CycleState): boolean {
  return hasSlotContent(c) || Object.values(c.nv).some(v => !!v)
}

// ── 建立/發布後可見性等待（backend 已知 race：回應先於 commit 可見 ~0.5s）────────
// 根因在後端（session commit 於回應後才對其他請求可見），已回報協調者轉 ddm-backend；
// 此處僅做有界輪詢（≤10×300ms），逾時即拋錯，不吞任何非 404 錯誤。
// minVersion>0 時同時等待 current_version 達標（publish commit 可見）。
async function waitModuleVisible(id: string, minVersion = 0): Promise<void> {
  for (let i = 0; i < 10; i++) {
    try {
      const m = await apiGet<MotionModuleSummary>(`/api/v2/motion-modules/${id}`)
      if ((m.current_version ?? 0) >= minVersion) return
    } catch (e) {
      if (!(e as Error).message.startsWith('404')) throw e
    }
    await new Promise(r => setTimeout(r, 300))
  }
  throw new Error(i18n.t('workbench.error.moduleNotVisible', { id }))
}

// ── Simple Toast ──────────────────────────────────────────────────────────────
interface ToastState { msg: string; type: 'ok' | 'err' }

function Toast({ toast }: { toast: ToastState | null }) {
  if (!toast) return null
  return (
    <div className={`fixed bottom-6 right-6 z-50 px-4 py-2 rounded shadow-lg text-white text-sm transition-all ${
      toast.type === 'ok' ? 'bg-emerald-600' : 'bg-red-600'
    }`}>
      {toast.msg}
    </div>
  )
}

// ── ActionModuleWorkspace ─────────────────────────────────────────────────────
export function ActionModuleWorkspace() {
  const { t } = useTranslation()
  // ADR-014 值權威：工作台建模/發布一律用 V2（29 個搬遷動作即以 V2 字典發布，
  // 複本 rows 含 V2 選項碼；用 V1 發布會 422 X_UNKNOWN 等）
  const activeRs = useActiveRuleSet()
  const { data: opts, error: optsErr } = useRuleSetOptions(activeRs.data?.code)
  const ruleSetErr = activeRs.error ?? optsErr
  const { data: vocab = [] } = useVocab()
  const calc = useCalculate()
  const createVocab = useCreateVocab()
  // review 事件（學習迴圈）需 IE 以上；viewer 送必 403 → 依角色直接略過（同 AiDraftPanel）
  const { data: me } = useMe()
  const canWriteReviews = canEdit(me)

  // Builder state
  const [cur, setCur] = useState<CycleState>(defaultCycle())
  const [wiSentence, setWiSentence] = useState('')       // WI 語句人工覆寫（audit §1.6）
  const [showHandInMi, setShowHandInMi] = useState(true) // 顯示於MI checkbox
  const [tmu, setTmu] = useState<number | null>(null)
  const [tech, setTech] = useState('')
  const [calcErrMsg, setCalcErrMsg] = useState<string | null>(null)
  const [editingModuleId, setEditingModuleId] = useState<string | null>(null)
  const [source, setSource] = useState<'manual' | 'ai' | 'copied'>('manual')

  // NL Draft state（F-05）
  const [nlText, setNlText] = useState('')
  const [nlLoading, setNlLoading] = useState(false)
  const [nlResult, setNlResult] = useState<NlDraftRes | null>(null)
  const [nlAskOpen, setNlAskOpen] = useState(false)      // 覆蓋/填空兩鍵 modal
  // §18.3 多 action：已逐筆採用的 draft action_id（採用→存檔→採用下一筆的迴圈標記）
  const [adoptedDraftIds, setAdoptedDraftIds] = useState<Set<string>>(new Set())
  // review 事件（學習迴圈）失敗提示：非阻斷，但不可靜默（No error bypass）
  const [reviewWarn, setReviewWarn] = useState<string | null>(null)

  // ai.drafts 是權威草稿（wi_ai_service：頂層 slots 只是舊前端相容的壓平欄位）
  const nlDrafts: AiCycleDraft[] = nlResult?.ai?.drafts ?? []
  const nlMulti = nlDrafts.length > 1
  // 單 action 但相容欄位（rule_based）與權威草稿（可能來自 LLM）不一致 → 與多 action
  // 同待遇：不自動套用、隱藏會誤導的壓平欄位列，只出權威草稿卡
  const nlDraftMismatch = !!nlResult && nlDrafts.length === 1 && !compatMatchesDraft(nlResult, nlDrafts[0])
  const nlCompatHidden = nlMulti || nlDraftMismatch
  const nlActionsById: Record<string, AiPlannedAction> = Object.fromEntries(
    (nlResult?.ai?.plan?.actions ?? []).map(a => [a.action_id, a]),
  )

  // Toast
  const [toast, setToast] = useState<ToastState | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  function showToast(msg: string, type: 'ok' | 'err' = 'ok') {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ msg, type })
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }

  // Pool state
  const [searchQ, setSearchQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [selectedSimoPairs, setSelectedSimoPairs] = useState<Record<string, string>>({})
  const [orderedIds, setOrderedIds] = useState<string[]>([])
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [loadingModuleId, setLoadingModuleId] = useState<string | null>(null)
  // 行內頻率（B-1）：草稿字串（輸入中）／儲存中的列／per-row debounce timer
  const [freqDraft, setFreqDraft] = useState<Record<string, string>>({})
  const [freqSavingIds, setFreqSavingIds] = useState<Set<string>>(new Set())
  const freqTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})
  // 最後一次送出/落地的頻率（M3：commit 比較基準取此，非 render closure 快照）
  const freqRequested = useRef<Record<string, number>>({})
  // per-row 送出序列（保序，避免回應亂序覆蓋較新值）
  const freqChain = useRef<Record<string, Promise<void>>>({})
  useEffect(() => () => { Object.values(freqTimers.current).forEach(clearTimeout) }, [])

  // Debounce searchQ → debouncedQ (300ms), then let API do the filtering
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(searchQ.trim()), 300)
    return () => clearTimeout(timer)
  }, [searchQ])

  // ── 全部／我的 篩選（P1-B B-2；守則 §4「清單語意」） ─────────────────────────
  // v3 的動作清單是「我的動作」（per-user 素材），v2 兩層模型下清單同時承載共享
  // 認證庫 → 折衷：提供切換，**預設「全部」**（搬遷的 29 條為 global scope，
  // 預設「我的」會是空清單）。「我的」＝ scope=personal（後端自動加 owner=當前使用者）。
  const [ownerFilter, setOwnerFilter] = useState<'all' | 'mine'>('all')

  // API hooks
  // 動作清單只列「個別動作」（category='action'，ADR-022）；不帶 scope → 後端回
  // 「所有可見」（global/site＋自己的 personal），含共享標準動作（v3-import 認證庫）
  const baseFilters = debouncedQ ? { category: 'action', q: debouncedQ } : { category: 'action' }
  // 兩個查詢並存：切換即時（已快取）＋ segmented 上兩邊筆數都要顯示
  const allQuery = useMotionModules(baseFilters)
  const mineQuery = useMotionModules({ ...baseFilters, scope: 'personal' })
  const activeQuery = ownerFilter === 'mine' ? mineQuery : allQuery
  const modules = activeQuery.data ?? []
  const modulesLoading = activeQuery.isLoading
  const updateModuleRow = useUpdateModuleRow()
  const createModule = useCreateModule()
  const updateModule = useUpdateModule()
  const deleteModule = useDeleteModule()
  const cloneModule = useCloneModule()
  const publishModule = usePublishModule()
  const createWiTemplate = useCreateWiTemplate()
  const qc = useQueryClient()

  // 動作列表本地持序（後端 reorder 目前為 stub），保留本次工作排序。
  useEffect(() => {
    setOrderedIds(prev => {
      const ids = modules.map(m => m.id)
      const known = prev.filter(id => ids.includes(id))
      const appended = ids.filter(id => !known.includes(id))
      return [...known, ...appended]
    })
  }, [modules])

  const orderedModules = useMemo(() => {
    if (modules.length === 0) return [] as MotionModuleSummary[]
    const byId = new Map(modules.map(m => [m.id, m] as const))
    const ordered: MotionModuleSummary[] = []
    orderedIds.forEach(id => {
      const mod = byId.get(id)
      if (mod) ordered.push(mod)
    })
    return ordered
  }, [modules, orderedIds])

  // ADR-022 E-3：每列 Base/頻率改讀 list 摘要欄（base_tmu / frequency，後端 E-2
  // 從 current version rows[0] 回填）——不再逐筆撈 detail（N+1 已移除）。

  // WI 建立列（浮動）＋ WiItemInspector 狀態
  const [wiName, setWiName] = useState('')
  const [creatingWi, setCreatingWi] = useState(false)
  const [inspector, setInspector] = useState<{
    wi: MotionModuleSummary; rowIndex: number; row: MotionModuleRow
  } | null>(null)

  // ── Debounced backend calculate (400ms)：前端不算 TMU（DISC-02） ─────────────
  const payload = useMemo(
    () => (opts ? buildPayload(cur, opts.code) : null),
    [cur, opts],
  )
  useEffect(() => {
    if (!payload) { setTmu(null); setTech(''); setCalcErrMsg(null); return }
    const id = setTimeout(() => {
      setCalcErrMsg(null)
      calc.mutate(payload, {
        onSuccess: r => {
          setTmu(r.total_tmu)
          setTech(r.tech_line)
          setCalcErrMsg(null)
        },
        onError: (err) => {
          setTmu(null)
          setTech('')
          setCalcErrMsg(apiErrorMessage(err))
        },
      })
    }, 400)
    return () => clearTimeout(id)
  }, [JSON.stringify(payload)]) // eslint-disable-line react-hooks/exhaustive-deps

  // 錯誤態必須與載入態可分（否則無 active 版本時會永遠停在 spinner）
  if (ruleSetErr) return (
    <div className="bg-white rounded-xl border p-6"><RuleSetUnavailable error={ruleSetErr} /></div>
  )
  if (!opts) return (
    <div className="bg-white rounded-xl border p-6 text-slate-500">{t('workbench.loadingRuleSet')}</div>
  )

  // ── helpers ───────────────────────────────────────────────────────────────
  const set = (patch: Partial<CycleState>) => setCur(c => ({ ...c, ...patch }))
  const gm = cur.seq === 'GM'

  const vname = (_kind: string, id: string) => vocab.find(v => v.id === id)?.name_zh ?? ''
  const label = (kind: string, code: string) => {
    const m: Record<string, { code: string; label: string }[]> = { g: opts.g, p_base: opts.p_bases, m_verb: opts.m_verbs }
    return m[kind]?.find(o => o.code === code)?.label ?? ''
  }

  // MI 語句：即時 shortNarr（顯示預覽；權威敘述由後端 narrative 產）
  const miSentence = shortNarr(cur, label, vname, showHandInMi)

  // 摘要列數值（eff = tmu × freq 為顯示用算術，非 TMU 規則計算）
  const effTmu = tmu != null ? Math.round(tmu * (cur.freq || 1) * 1000) / 1000 : null
  const ctSec = effTmu != null ? (effTmu * TMU_SEC).toFixed(3) : null
  const isSimo = (cur.simoGroup || '').trim() !== ''

  // NL 結果面板：option code → label
  function nlOptionLabel(field: string, code: string): string {
    if (field === 'g_code') return opts!.g.find(o => o.code === code)?.label ?? code
    if (field === 'b_code' || field === 'b_code2') return opts!.b.find(o => o.code === code)?.label ?? code
    if (field === 'p_base_code') return opts!.p_bases.find(o => o.code === code)?.label ?? code
    return code
  }

  // ── NL Draft（F-05：覆蓋/填空 + 結果面板，audit §1.13） ──────────────────────
  async function runNlDraft() {
    const text = nlText.trim()
    if (!text || !opts) return
    setNlLoading(true)
    try {
      const res = await apiPost<NlDraftRes>('/api/v2/worksheets/nl-draft', {
        text, rule_set_code: opts.code,
      })
      setNlResult(res)
      setAdoptedDraftIds(new Set())
      setReviewWarn(null)
      const drafts = res.ai?.drafts ?? []
      if (drafts.length > 1) {
        // §18.3：多 action 不得自動套用（相容 slots 只壓平首個 action，
        // 自動套用＝靜默丟棄其餘 action）→ 逐筆呈現、逐筆採用
        showToast(t('workbench.toast.multiDraft', { n: drafts.length }), 'ok')
      } else if (drafts.length === 1 && !compatMatchesDraft(res, drafts[0])) {
        // 相容欄位（永遠 rule_based）與權威草稿（可能 LLM）不一致：自動套用會把
        // 編輯器覆蓋成 rule 的猜測、卡片卻顯示另一結果 → 只出卡片（與多 action 同待遇）
        showToast(t('workbench.toast.draftMismatch'), 'ok')
      } else if (hasEditorContent(cur)) {
        setNlAskOpen(true)               // 編輯器有內容 → 詢問覆蓋/填空
      } else {
        applyNlDraft(res, 'overwrite')
      }
    } catch (err) {
      const e = err as Error
      if (e.message.startsWith('404') || e.message.startsWith('501')) {
        showToast(t('workbench.toast.nlDisabled'), 'err')
      } else {
        showToast(t('workbench.toast.nlFailed', { message: e.message }), 'err')
      }
    } finally {
      setNlLoading(false)
    }
  }

  function applyNlDraft(res: NlDraftRes, mode: 'overwrite' | 'fill-empty') {
    const patch = mode === 'overwrite' ? nlDraftPatch(res) : nlDraftPatchFillEmpty(res, cur)
    if (Object.keys(patch).length > 0) {
      set(patch)
      setSource('ai')
      showToast(mode === 'overwrite' ? t('workbench.toast.appliedOverwrite') : t('workbench.toast.appliedFillEmpty'), 'ok')
    } else {
      showToast(t('workbench.toast.appliedNone'), 'err')
    }
    setNlAskOpen(false)
  }

  // ── 採用單一 AI draft（§18.3 多 action 逐筆迴圈；沿用 AiDraftPanel 慣例） ──────
  function adoptNlDraft(draft: AiCycleDraft) {
    if (!draft.cycle) return
    // 編輯器已有內容（如：採用草稿 1 後手調、或手動建模到一半）→ 覆蓋前確認。
    // 「填空」對整卡載入無意義（草稿是完整 cycle），一個覆蓋確認即可（與 NL 預填
    // 的覆蓋/填空 modal 語意對稱）。
    if (hasEditorContent(cur) && !window.confirm(t('workbench.confirm.adoptOverwrite'))) return
    const next = payloadToState(draft.cycle)
    // 保留手別／語彙情境（與 wi-workbench onAdoptCycle 同款），其餘整組載入草稿
    setCur(c => ({ ...next, handCode: c.handCode || next.handCode, nv: { ...c.nv } }))
    setWiSentence('')                 // 名稱回到自動命名（草稿內容已換）
    setEditingModuleId(null)          // 草稿＝新動作；不得靜默覆寫編輯中的模組
    setSource('ai')
    setAdoptedDraftIds(prev => new Set(prev).add(draft.action_id))
    showToast(t('workbench.toast.draftAdopted', { name: draft.narrative ?? draft.action_id }), 'ok')
    // review event（學習迴圈）：採用已成功，記錄失敗不阻斷；但失敗不可靜默吞掉
    // （No error bypass）——console.warn＋面板灰字提示。viewer（level 0）送必 403，
    // 依角色直接略過（同 AiDraftPanel 的 canWriteReviews gating）。
    const runId = nlResult?.ai?.run_id
    if (runId && canWriteReviews) {
      apiPost<ReviewBatchOut>(`/api/v2/nl-drafts/${runId}/reviews`, {
        ui_version: 'workbench-v3@nl-multi',
        events: [{
          event_type: 'accept_plan',
          target: { action_id: draft.action_id },
          // i18n-exempt: 送後端的 review 事件 payload 欄位，不是 UI 文案；跟著介面語言變會讓學習迴圈的紀錄依操作者語言分裂成兩群
          reason: '採用單一 draft 至編輯器',
        }],
      }).catch(err => {
        // i18n-exempt: 開發者 console 訊息，不是使用者介面文字（面板上的提示走 setReviewWarn，那條有 i18n）
        console.warn('[nl-review] review 事件記錄失敗（非阻斷）：', err)
        setReviewWarn(apiErrorMessage(err))
      })
    }
  }

  // ── Reset builder ─────────────────────────────────────────────────────────
  // keepNl：多 action 迴圈中存檔後保留 NL 面板（否則其餘草稿隨 reset 消失＝變相丟棄）
  // 參數用解構命名，避免遮蔽外層 rule-set `opts`（曾因同名遮蔽埋過雷）
  function resetBuilder({ keepNl = false }: { keepNl?: boolean } = {}) {
    setCur(defaultCycle())
    setWiSentence('')
    setTmu(null)
    setTech('')
    setEditingModuleId(null)
    setSource('manual')
    if (!keepNl) {
      setNlText('')
      setNlResult(null)
      setNlAskOpen(false)
      setAdoptedDraftIds(new Set())
      setReviewWarn(null)
    }
  }

  // ── Save / update module（名稱＝WI 語句覆寫；空則自動命名） ────────────────────
  async function handleSave() {
    // 全空擋下：無 WI 語句且格位全空 → 沒有可命名/可計算的內容（reviewer #3）
    if (!wiSentence.trim() && !hasSlotContent(cur)) {
      showToast(t('workbench.toast.needSlotOrSentence'), 'err'); return
    }
    if (!tmu || tmu <= 0) { showToast(t('workbench.toast.needPositiveTmu'), 'err'); return }
    if (!opts) return
    // 自動命名：情境欄有值 → 系統句；情境欄全空 → tech line 壓縮尾綴（去 0 值格，
    // 如「GM A6 G6 A10 P6」），避免佔位符（［自］［物］…）進名稱（reviewer #3）
    const contextFilled = !!(cur.nv.obj || cur.nv.from || cur.nv.to)
    const compactTech = tech.split(/\s+/).filter(t => t && !/^[A-Z]+0$/.test(t)).join(' ')
    const autoName = contextFilled || !compactTech ? miSentence : `${cur.seq} ${compactTech}`
    const name = wiSentence.trim() || autoName

    const row = {
      hand: cur.handCode,
      frequency: cur.freq,
      cycle: buildPayload(cur, opts.code),
      sub_activity: name,
      // 後端 ModuleRowIn.vocab_refs 合約鍵：object/from/to(/tool)_vocab_id；
      // component/where 無對應鍵不送（僅前端敘述/顯示用）— reviewer #1
      vocab_refs: {
        object_vocab_id: cur.nv.obj || null,
        from_vocab_id: cur.nv.from || null,
        to_vocab_id: cur.nv.to || null,
      },
    }

    try {
      if (editingModuleId) {
        // 後端 MotionModuleUpdate 無 rows/source 欄位；列內容變更走 publish（發新版本）
        await updateModule.mutateAsync({
          id: editingModuleId,
          body: { name_zh: name },
        })
        await publishModule.mutateAsync({
          id: editingModuleId,
          body: { rows: [row], rule_set_code: opts.code },
        })
        showToast(t('workbench.toast.moduleUpdated', { name }), 'ok')
      } else {
        const created = await createModule.mutateAsync({
          name_zh: name,
          category: 'action',      // ADR-022：新動作明送 category='action'
          scope: 'personal',
          keywords: [],
        })
        await waitModuleVisible(created.id)   // 後端 commit 可見性 race（見 helper 註解）
        await publishModule.mutateAsync({
          id: created.id,
          body: { rows: [row], rule_set_code: opts.code },
        })
        showToast(t('workbench.toast.actionAdded', { name }), 'ok')
      }
      // 多 action 迴圈：還有「可採用」的未採用草稿 → 保留 NL 面板供採用下一筆（§18.3）。
      // 無 cycle 的草稿（如 composite_unknown）永遠採用不了，不能讓面板永不自動收。
      const keepNl = nlMulti && nlDrafts.some(d => d.cycle != null && !adoptedDraftIds.has(d.action_id))
      resetBuilder({ keepNl })
    } catch (err) {
      showToast(t('workbench.toast.saveFailed', { message: (err as Error).message }), 'err')
    }
  }

  // ── Load module into builder（列編輯迴路，audit §1.7） ────────────────────────
  async function loadModule(mod: MotionModuleSummary, mode: 'edit' | 'rework' = 'edit') {
    setLoadingModuleId(mod.id)
    try {
      const detail = await apiGet<MotionModuleSummary>(`/api/v2/motion-modules/${mod.id}`)
      const row = detail.current_version_detail?.rows?.[0]
      if (!row) {
        showToast(t('workbench.toast.noPublishedVersion'), 'err')
        return
      }
      const next = payloadToState(row.cycle)
      // vocab_refs 還原進情境欄（與存檔時的鍵對稱）— reviewer #1
      const refs = (row.vocab_refs ?? {}) as Record<string, unknown>
      const vid = (k: string) => (typeof refs[k] === 'string' ? refs[k] as string : '')
      setCur({
        ...next, handCode: row.hand, freq: row.frequency,
        nv: { ...next.nv, obj: vid('object_vocab_id'), from: vid('from_vocab_id'), to: vid('to_vocab_id') },
      })
      setWiSentence(mod.name_zh)
      setEditingModuleId(mode === 'edit' ? mod.id : null)
      setSource(mode === 'rework' ? 'copied' : ((detail.source as 'manual' | 'ai' | 'copied') ?? 'manual'))
      showToast(mode === 'rework'
        ? t('workbench.toast.loadedAsNew', { name: mod.name_zh })
        : t('workbench.toast.loadedForEdit', { name: mod.name_zh }), 'ok')
    } catch (err) {
      showToast(t('workbench.toast.loadFailed', { message: (err as Error).message }), 'err')
    } finally {
      setLoadingModuleId(null)
    }
  }

  // ── Delete module（確認後刪除，audit §1.9） ──────────────────────────────────
  async function handleDelete(id: string, name: string) {
    if (!window.confirm(t('workbench.confirm.deleteModule', { name }))) return
    try {
      await deleteModule.mutateAsync(id)
      if (editingModuleId === id) resetBuilder()
      setSelectedIds(s => { const next = new Set(s); next.delete(id); return next })
      setSelectedSimoPairs(prev => {
        const next: Record<string, string> = {}
        for (const [followerId, leaderId] of Object.entries(prev)) {
          if (followerId !== id && leaderId !== id) next[followerId] = leaderId
        }
        return next
      })
      showToast(t('workbench.toast.deleted', { name }), 'ok')
    } catch (err) {
      showToast(t('workbench.toast.deleteFailed', { message: (err as Error).message }), 'err')
    }
  }

  // ── Clone module ──────────────────────────────────────────────────────────
  async function handleClone(id: string, name: string) {
    try {
      await cloneModule.mutateAsync(id)
      showToast(t('workbench.toast.cloned', { name }), 'ok')
    } catch (err) {
      showToast(t('workbench.toast.cloneFailed', { message: (err as Error).message }), 'err')
    }
  }

  // ── 行內頻率編輯（P1-B B-1；對齊 v3 清單 input-number 即時後端重算持久化）────────
  // 鐵則：前端**不**自乘出 Eff/CT 當權威值——debounce 500ms 後 PUT rows/0，
  // 落值一律採後端回傳的 computed（applyVersionToCaches 直寫清單快取）。
  // 儲存中該列 Eff/CT 顯示「計算中…」；失敗 toast＋丟棄草稿（回復後端原值）。

  /**
   * 該列目前的「權威頻率」——review M3：不可用 render closure 的 `mod.frequency`
   * 快照。優先讀最後一次成功送出的值（freqRequested，涵蓋 PUT 在途、快取尚未更新
   * 的時間窗），否則讀 list 快取（applyVersionToCaches 直寫的後端值）。
   */
  function latestFreq(id: string): number | null {
    const requested = freqRequested.current[id]
    if (requested != null) return requested
    for (const [, data] of qc.getQueriesData<MotionModuleSummary[]>({ queryKey: [MODULE_QUERY_KEY] })) {
      if (Array.isArray(data)) {
        const hit = data.find(m => m.id === id)
        if (hit?.frequency != null) return hit.frequency
      }
    }
    return null
  }

  async function commitFreq(id: string, name: string, next: number) {
    const prev = latestFreq(id)
    if (prev != null && next === prev) {
      // 與權威值相同 → 無需往返；草稿可清（顯示值不變，如 "01" → "1"）
      setFreqDraft(d => { const n = { ...d }; delete n[id]; return n })
      return
    }
    freqRequested.current[id] = next      // 在途值：後續 commit 以此為 prev 比較（M3）
    setFreqSavingIds(s => new Set(s).add(id))
    try {
      // 行內只換 frequency：其餘欄位（hand/cycle/sub_activity/vocab_refs/SIMO）
      // 取目前已發布版本 rows[0] 原值回送，避免後端把未帶欄位當清空。
      const detail = await apiGet<MotionModuleSummary>(`/api/v2/motion-modules/${id}`)
      const src = detail.current_version_detail?.rows?.[0]
      if (!src) throw new Error(t('workbench.error.freqNoPublishedVersion'))
      const ver = await updateModuleRow.mutateAsync({
        id,
        rowIndex: 0,                     // action＝單列模組（ADR-022）→ 恆 row_index=0
        row: {
          sub_activity: src.sub_activity ?? null,
          hand: src.hand,
          frequency: next,
          simo_pair_index: src.simo_pair_index ?? null,
          vocab_refs: src.vocab_refs ?? {},
          cycle: src.cycle,
        },
      })
      // 後端權威落值（理論上＝next；以回應為準，不假設）
      freqRequested.current[id] = ver.rows[0]?.frequency ?? next
      setFreqDraft(d => { const n = { ...d }; delete n[id]; return n })  // 改讀後端權威
      showToast(t('workbench.toast.freqUpdated', { name, n: next }), 'ok')
    } catch (err) {
      delete freqRequested.current[id]   // 後端值未變 → 回落 list 快取
      setFreqDraft(d => { const n = { ...d }; delete n[id]; return n })  // 回復原值
      showToast(t('workbench.toast.freqFailed', { message: apiErrorMessage(err) }), 'err')
    } finally {
      setFreqSavingIds(s => { const n = new Set(s); n.delete(id); return n })
    }
  }

  function onFreqInput(mod: MotionModuleSummary, raw: string) {
    setFreqDraft(d => ({ ...d, [mod.id]: raw }))
    const t = freqTimers.current[mod.id]
    if (t) clearTimeout(t)
    const next = parseInt(raw, 10)
    // review M2：輸入無效（刪空／NaN／<1）只是「不 commit」，**不得丟棄草稿**——
    // 否則使用者全選刪除後欄位會跳回舊值，接著鍵入的數字被接在舊值後（1 → "12"）。
    if (!Number.isFinite(next) || next < 1) return
    freqTimers.current[mod.id] = setTimeout(() => {
      // 同列序列化：輸入框在儲存中仍可繼續編輯（不鎖），但 PUT 依送出順序執行，
      // 避免回應亂序讓舊版本後寫入快取而覆蓋較新的值。
      const prev = freqChain.current[mod.id] ?? Promise.resolve()
      freqChain.current[mod.id] = prev
        .then(() => commitFreq(mod.id, mod.name_zh, next))
        .catch(() => { /* commitFreq 內已 toast；鏈不可中斷 */ })
    }, 500)
  }

  // ── Multi-select ──────────────────────────────────────────────────────────
  function toggleSelect(id: string) {
    setSelectedIds(s => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      setSelectedSimoPairs(prev => {
        const pairs: Record<string, string> = {}
        for (const [followerId, leaderId] of Object.entries(prev)) {
          if (next.has(followerId) && (!leaderId || next.has(leaderId))) pairs[followerId] = leaderId
        }
        return pairs
      })
      return next
    })
  }

  function toggleListSimo(moduleId: string, enabled: boolean) {
    setSelectedSimoPairs(prev => {
      const next = { ...prev }
      if (!enabled) {
        delete next[moduleId]
        return next
      }
      if (!(moduleId in next)) next[moduleId] = ''
      return next
    })
  }

  function setListSimoPair(moduleId: string, leaderId: string | null) {
    setSelectedSimoPairs(prev => {
      const next = { ...prev }
      if (!leaderId || leaderId === moduleId) {
        next[moduleId] = ''
        return next
      }
      if (Object.values(prev).includes(moduleId)) return prev
      next[moduleId] = leaderId
      return next
    })
  }

  function moveOrderedModule(sourceId: string, targetId: string) {
    if (sourceId === targetId) return
    setOrderedIds(prev => {
      const from = prev.indexOf(sourceId)
      const to = prev.indexOf(targetId)
      if (from < 0 || to < 0) return prev
      const next = [...prev]
      const [item] = next.splice(from, 1)
      next.splice(to, 0, item)
      return next
    })
  }

  function shiftOrderedModule(sourceId: string, direction: -1 | 1) {
    setOrderedIds(prev => {
      const from = prev.indexOf(sourceId)
      if (from < 0) return prev
      const to = from + direction
      if (to < 0 || to >= prev.length) return prev
      const next = [...prev]
      const [item] = next.splice(from, 1)
      next.splice(to, 0, item)
      return next
    })
  }

  // ── 建立 WI（ADR-022 B-3）：勾選動作 → rows 快照複本（深拷貝含 vocab_refs）──────
  function autoWiName(selected: MotionModuleSummary[]): string {
    if (selected.length === 1) return selected[0].name_zh
    return t('workbench.createWi.autoNameMulti', { name: selected[0].name_zh, n: selected.length })
  }

  async function handleCreateWi() {
    if (!opts) return
    const selected = orderedModules.filter(m => selectedIds.has(m.id))
    if (selected.length === 0) return
    setCreatingWi(true)
    try {
      const indexById = Object.fromEntries(selected.map((mod, index) => [mod.id, index]))
      // 每個動作的 rows[0] 快照複本（copy-on-write：WI 微調不影響來源動作）。
      // E-3 後 list 不再預載 detail → 建 WI 時才逐筆撈（僅勾選的少數幾筆，非 N+1）
      const rows: MotionModuleRow[] = await Promise.all(
        selected.map(async mod => {
          const detail = await apiGet<MotionModuleSummary>(`/api/v2/motion-modules/${mod.id}`)
          const src = detail.current_version_detail?.rows?.[0]
          if (!src) throw new Error(t('workbench.error.actionNoPublishedVersion', { name: mod.name_zh }))
          const clone = JSON.parse(JSON.stringify(src)) as MotionModuleRow  // 深拷貝（含 vocab_refs）
          const simoLeaderId = selectedSimoPairs[mod.id]
          return {
            sub_activity: clone.sub_activity ?? mod.name_zh,
            hand: clone.hand,
            frequency: clone.frequency,
            simo_pair_index: simoLeaderId ? indexById[simoLeaderId] ?? null : clone.simo_pair_index ?? null,
            vocab_refs: clone.vocab_refs ?? {},
            cycle: clone.cycle,
          }
        }),
      )
      const name = (wiName.trim() || autoWiName(selected)).slice(0, 200)
      const created = await createWiTemplate.mutateAsync({
        name_zh: name,
        category: 'wi-template',   // ADR-022：WI 大綱項明送 category
        keywords: [],
        scope: 'personal',
      })
      await waitModuleVisible(created.id)   // 後端 commit 可見性 race（見 helper 註解）
      await publishModule.mutateAsync({
        id: created.id,
        body: { rows, rule_set_code: opts.code },
      })
      // publish commit 同樣有可見性延遲 → 等 current_version ≥ 1 再刷新（否則展開
      // 子列會撈到 version 0 並被 staleTime 快取成「尚無已發布版本」）
      await waitModuleVisible(created.id, 1)
      qc.invalidateQueries({ queryKey: ['motion-modules'] })
      qc.invalidateQueries({ queryKey: ['wi-templates'] })
      setSelectedIds(new Set())
      setSelectedSimoPairs({})
      setWiName('')
      showToast(t('workbench.toast.wiCreated', { name, count: rows.length }), 'ok')
    } catch (err) {
      showToast(t('workbench.toast.wiCreateFailed', { message: (err as Error).message }), 'err')
    } finally {
      setCreatingWi(false)
    }
  }

  // ── Pool 摘要：合計走後端摘要欄加總；缺值顯示 —（audit §0.1） ─────────────────
  const tmuValues = modules.map(m => m.total_tmu).filter((v): v is number => v != null)
  const poolTotalTmu = tmuValues.length > 0
    ? Math.round(tmuValues.reduce((a, b) => a + b, 0) * 1000) / 1000
    : null

  function getModuleSeq(mod: MotionModuleSummary): string {
    if (typeof mod.seq_kind === 'string' && mod.seq_kind) return mod.seq_kind
    const seq = mod.current_version_detail?.rows?.[0]?.cycle?.seq
    return typeof seq === 'string' ? seq : '—'
  }

  function getModuleHand(mod: MotionModuleSummary): string {
    const hand = mod.hand ?? mod.current_version_detail?.rows?.[0]?.hand
    if (!hand) return '—'
    return handName(hand)
  }

  const isSaving = createModule.isPending || updateModule.isPending || publishModule.isPending

  // 摘要列九欄（v3 SequenceSummaryBar 對等）
  const summaryFields: Array<{ label: string; node: React.ReactNode; wide?: boolean }> = [
    {
      label: t('workbench.summary.seq'),
      node: <span className="bg-blue-100 text-blue-700 rounded px-1.5 py-0.5 text-xs font-medium">{gm ? t('workbench.seq.GM') : t('workbench.seq.CM')}</span>,
    },
    { label: t('workbench.summary.hand'), node: <span>{handName(cur.handCode)}</span> },
    { label: t('workbench.summary.baseTmu'), node: <b className="text-base" style={{ color: '#1a73e8' }} data-testid="summary-base-tmu">{tmu ?? '—'}</b> },
    {
      label: t('workbench.summary.frequency'),
      node: (
        <input
          type="number" min={1}
          className="border rounded w-14 px-1 py-0 text-sm"
          value={cur.freq}
          onChange={e => set({ freq: parseInt(e.target.value) || 1 })}
        />
      ),
    },
    { label: t('workbench.summary.effTmu'), node: <b className="text-base text-red-600">{effTmu ?? '—'}</b> },
    { label: t('workbench.summary.ctSeconds'), node: <span>{ctSec ?? '—'}</span> },
    { label: t('workbench.summary.simo'), node: <span className={isSimo ? 'text-orange-600 font-bold' : ''}>{isSimo ? t('workbench.summary.simoYes') : t('workbench.summary.simoNo')}</span> },
    {
      label: t('workbench.summary.includedTotal'),
      node: effTmu == null
        ? <span>—</span>
        : isSimo
          ? <span className="line-through text-slate-400">0</span>
          : <span>{effTmu}</span>,
    },
    { label: t('workbench.summary.miSentence'), node: <span className="text-xs text-slate-600 truncate">{miSentence}</span>, wide: true },
  ]

  return (
    <>
      <Toast toast={toast} />
      <div className="space-y-3">

        {/* ═══ 建立器卡片：AI 列 → 摘要列 → 交錯句型 → WI 語句 ═══ */}
        <div className="bg-white rounded-xl border p-4 space-y-3">

          {/* 1. AI 快速建模列 */}
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-xs font-semibold text-white bg-slate-600 rounded px-2 py-1">{t('workbench.builder.aiQuickModel')}</span>
            <input
              className="flex-1 min-w-0 border rounded px-2 py-1.5 text-sm"
              placeholder={t('workbench.builder.nlPlaceholder')}
              value={nlText}
              onChange={e => setNlText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !nlLoading) runNlDraft() }}
            />
            <button
              onClick={runNlDraft}
              disabled={nlLoading || !nlText.trim()}
              className="shrink-0 px-3 py-1.5 bg-blue-600 text-white rounded text-sm disabled:opacity-40"
            >
              {nlLoading ? t('workbench.builder.nlRunning') : t('workbench.builder.nlRun')}
            </button>
          </div>

          {/* 1b. NL 結果面板（可關閉） */}
          {nlResult && (
            <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs space-y-1.5" data-testid="nl-result-panel">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`rounded px-1.5 py-0.5 font-medium ${
                  (nlResult.overall_confidence ?? 0) >= 0.7
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-amber-100 text-amber-700'
                }`}>
                  {t('workbench.nl.confidence', { percent: Math.round((nlResult.overall_confidence ?? 0) * 100) })}
                </span>
                {!nlCompatHidden && nlResult.suggested_seq && (
                  <span className="bg-slate-200 text-slate-700 rounded px-1.5 py-0.5">
                    {t('workbench.nl.suggested', {
                      seq: nlResult.suggested_seq === 'GM'
                        ? t('workbench.nl.suggestedGm')
                        : t('workbench.nl.suggestedCm'),
                    })}
                  </span>
                )}
                {nlResult.ai && (
                  <span className="text-slate-500">
                    routing: {nlResult.ai.routing_status}
                    {nlResult.ai.provenance?.fallback ? t('workbench.nl.ruleFallback') : ''}
                  </span>
                )}
                <button
                  onClick={() => setNlResult(null)}
                  className="ml-auto text-slate-400 hover:text-slate-600 leading-none"
                  aria-label={t('workbench.nl.closeAria')}
                >✕</button>
              </div>

              {/* §18.3 多 action：逐筆呈現、逐筆採用，絕不靜默只取第一筆 */}
              {nlMulti && (
                <p
                  className="text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1"
                  data-testid="nl-multi-warning"
                >
                  {t('workbench.nl.multiWarning', { n: nlDrafts.length })}
                </p>
              )}

              {/* 單 action 但 LLM 權威草稿與 rule 相容欄位不一致：不自動套用（否則
                  編輯器被覆蓋成 rule 的猜測、卡片卻顯示另一結果）→ 由草稿卡採用 */}
              {nlDraftMismatch && (
                <p
                  className="text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1"
                  data-testid="nl-consistency-warning"
                >
                  {t('workbench.nl.mismatchWarning')}
                </p>
              )}

              {/* review 事件失敗（非阻斷）：不吞錯，灰字提示學習迴圈缺了這筆 */}
              {reviewWarn && (
                <p className="text-slate-400" data-testid="nl-review-warning">
                  {t('workbench.nl.reviewWarning', { message: reviewWarn })}
                </p>
              )}

              {/* ai.drafts 權威草稿卡（單 action 也顯示：CM 草稿無法用相容 slots 表達） */}
              {nlDrafts.length > 0 && (
                <div className="grid gap-2 sm:grid-cols-2" data-testid="nl-draft-cards">
                  {nlDrafts.map(d => (
                    <ActionCard
                      key={d.action_id}
                      action={nlActionsById[d.action_id]}
                      draft={d}
                      adopted={adoptedDraftIds.has(d.action_id)}
                      onAdopt={() => adoptNlDraft(d)}
                    />
                  ))}
                </div>
              )}

              {/* 逐 slot 命中/缺漏（badge 四態：明確/推斷/預設/待確認）。
                  多 action 或與權威草稿不一致時隱藏：頂層 slots 是 rule_based 的
                  壓平相容欄位，會誤導 */}
              {!nlCompatHidden && (
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {(nlResult.slots ?? []).map(s => (
                    <span key={s.field} className="inline-flex items-center gap-1">
                      <span className="text-slate-500">{t(`workbench.nl.field.${s.field}`, { defaultValue: s.field })}</span>
                      {s.chosen ? (
                        <>
                          <span className={`rounded border px-1 py-0.5 leading-none ${
                            sourceBadge(s.chosen.source) === 'exact' ? 'bg-blue-50 text-blue-600 border-blue-200'
                            : sourceBadge(s.chosen.source) === 'default' ? 'bg-amber-50 text-amber-600 border-amber-200'
                            : 'bg-emerald-50 text-emerald-600 border-emerald-200'
                          }`}>{t(`workbench.nl.badge.${sourceBadge(s.chosen.source)}`)}</span>
                          <span className="text-slate-700">{nlOptionLabel(s.field, s.chosen.option_code)}</span>
                        </>
                      ) : (
                        <span className="rounded border px-1 py-0.5 leading-none bg-red-50 text-red-500 border-red-200">{t('workbench.nl.badge.pending')}</span>
                      )}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 2. 動作類型 + 摘要列（九欄常駐） */}
          <div className="flex items-stretch gap-3">
            <select
              className="shrink-0 border rounded px-2 text-sm self-center py-1.5"
              value={cur.seq}
              onChange={e => setCur(c => migrateSeqState(c, e.target.value as 'GM' | 'CM'))}
              aria-label={t('workbench.builder.seqAriaLabel')}
            >
              <option value="GM">{t('workbench.seq.GM')}</option>
              <option value="CM">{t('workbench.seq.CM')}</option>
            </select>
            <div
              className="flex-1 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-lg border px-4 py-2"
              style={{ background: 'linear-gradient(135deg,#f8fbff 0%,#f0f7ff 100%)', borderColor: '#d4e5f7' }}
              data-testid="summary-bar"
            >
              {summaryFields.map(f => (
                <div key={f.label} className={`flex flex-col ${f.wide ? 'flex-1 min-w-[200px]' : ''}`}>
                  <span className="text-[10px] text-slate-400 tracking-wide">{f.label}</span>
                  <span className="text-sm font-medium text-slate-700 leading-5">{f.node}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 3. 交錯句型列（共用 SlotBuilder） */}
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

          {/* tech line（後端權威技術列） */}
          <div className="text-xs font-mono text-slate-400">{tech || '—'}</div>

          {/* 4. WI 語句 + 新增動作/清空 */}
          <div className="flex items-center gap-2 pt-2 border-t">
            <span className="shrink-0 text-xs font-semibold text-slate-600 border rounded px-2 py-1 bg-slate-50">{t('workbench.builder.wiSentence')}</span>
            <input
              className="flex-1 min-w-0 border rounded px-2 py-1.5 text-sm"
              placeholder={miSentence}
              value={wiSentence}
              onChange={e => setWiSentence(e.target.value)}
            />
            {editingModuleId && (
              <span className="shrink-0 text-xs text-amber-700 bg-amber-50 border border-amber-300 rounded px-2 py-0.5">
                {t('workbench.builder.editingBadge')}
              </span>
            )}
            {editingModuleId && (
              <button
                onClick={() => resetBuilder()}
                className="shrink-0 px-2 py-1.5 border rounded text-slate-600 hover:bg-slate-50 text-sm"
              >
                {t('workbench.builder.cancelEdit')}
              </button>
            )}
            <button
              disabled={isSaving || !tmu || tmu <= 0}
              onClick={handleSave}
              className="shrink-0 px-4 py-1.5 bg-emerald-600 text-white rounded-lg disabled:opacity-40 text-sm font-medium"
            >
              {isSaving ? t('workbench.builder.saving') : editingModuleId ? t('workbench.builder.updateModule') : t('workbench.builder.addAction')}
            </button>
            <button
              onClick={() => resetBuilder()}
              className="shrink-0 px-3 py-1.5 border rounded-lg text-slate-600 hover:bg-slate-50 text-sm"
            >
              {t('workbench.builder.clear')}
            </button>
          </div>

          {(tmu == null || tmu <= 0) && !calcErrMsg && (
            <p className="text-xs text-amber-700" data-testid="save-block-reason">
              {t('workbench.builder.saveBlockReason')}
            </p>
          )}
          {calcErrMsg && (
            <p className="text-xs text-red-600" data-testid="calc-error-message">
              {t('workbench.builder.calcError', { message: calcErrMsg })}
            </p>
          )}

          {source === 'ai' && (
            <p className="text-xs text-violet-600">{t('workbench.builder.aiSourceNote')}</p>
          )}
        </div>

        {/* ═══ 動作清單（個人模組 Pool） ═══ */}
        <div className="bg-white rounded-xl border p-4 space-y-3">
          {/* 工具列：搜尋 + 全部/我的 + 筆數 + 合計 */}
          <div className="flex items-center gap-3 flex-wrap">
            <input
              className="border rounded px-2 py-1 text-sm w-52"
              placeholder={t('workbench.pool.searchPlaceholder')}
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
            />
            {/* segmented：全部（預設）｜我的（scope=personal） */}
            <div className="inline-flex rounded-lg border overflow-hidden" data-testid="action-owner-filter">
              {([
                { key: 'all' as const, label: t('workbench.pool.all'), count: allQuery.data?.length },
                { key: 'mine' as const, label: t('workbench.pool.mine'), count: mineQuery.data?.length },
              ]).map(seg => (
                <button
                  key={seg.key}
                  onClick={() => setOwnerFilter(seg.key)}
                  aria-pressed={ownerFilter === seg.key}
                  className={`px-3 py-1 text-sm ${
                    ownerFilter === seg.key
                      ? 'bg-blue-600 text-white font-medium'
                      : 'bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {seg.label}
                  <span className="ml-1 text-xs opacity-80">{seg.count ?? '…'}</span>
                </button>
              ))}
            </div>
            <span className="text-sm text-slate-500">{t('workbench.pool.rowCount', { count: orderedModules.length })}</span>
            <span className="ml-auto text-sm text-slate-500">
              {t('workbench.pool.totalLabel')}{poolTotalTmu != null
                ? <><b style={{ color: '#1a73e8' }}>{poolTotalTmu}</b> TMU / <b className="text-red-600">{(poolTotalTmu * TMU_SEC).toFixed(3)}</b>s</>
                : '—'}
            </span>
          </div>

          {/* 動作清單表格 */}
          <MiCompositionTable
            modules={orderedModules}
            modulesLoading={modulesLoading}
            searchQ={searchQ}
            selectedIds={selectedIds}
            selectedSimoPairs={selectedSimoPairs}
            editingModuleId={editingModuleId}
            draggingId={draggingId}
            loadingModuleId={loadingModuleId}
            freqDraft={freqDraft}
            freqSavingIds={freqSavingIds}
            clonePending={cloneModule.isPending}
            deletePending={deleteModule.isPending}
            getModuleSeq={getModuleSeq}
            getModuleHand={getModuleHand}
            onSelectAll={checked => {
              if (checked) {
                setSelectedIds(new Set(orderedModules.map(m => m.id)))
                setSelectedSimoPairs({})
              } else {
                setSelectedIds(new Set())
                setSelectedSimoPairs({})
              }
            }}
            onToggleSelect={toggleSelect}
            onShiftOrderedModule={shiftOrderedModule}
            onDropReorder={moveOrderedModule}
            onDragStart={setDraggingId}
            onDragEnd={() => setDraggingId(null)}
            onFreqInput={onFreqInput}
            onToggleListSimo={toggleListSimo}
            onSetListSimoPair={setListSimoPair}
            onLoadModule={mod => loadModule(mod)}
            onReworkModule={mod => loadModule(mod, 'rework')}
            onCloneModule={handleClone}
            onDeleteModule={handleDelete}
          />

        </div>

        {/* ═══ WI 大綱（ADR-022 B-3：勾動作建 WI；子列開 Inspector） ═══ */}
        <WiOutlineSection
          onInspect={(wi, rowIndex, row) => setInspector({ wi, rowIndex, row })}
          showToast={showToast}
          activeTarget={inspector ? { moduleId: inspector.wi.id, rowIndex: inspector.rowIndex } : null}
        />
      </div>

      {/* 浮動建立 WI 列（勾選動作時出現） */}
      {selectedIds.size > 0 && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 bg-white border shadow-xl rounded-full px-5 py-2.5"
          data-testid="create-wi-bar"
        >
          <span className="text-sm text-slate-600 whitespace-nowrap">{t('workbench.createWi.selectedCount', { count: selectedIds.size })}</span>
          <input
            className="border rounded px-2 py-1 text-sm w-64"
            placeholder={t('workbench.createWi.namePlaceholder')}
            value={wiName}
            onChange={e => setWiName(e.target.value)}
          />
          <button
            onClick={handleCreateWi}
            disabled={creatingWi}
            className="px-4 py-1.5 bg-blue-600 text-white rounded-full text-sm font-medium disabled:opacity-40 hover:bg-blue-700"
          >
            {creatingWi ? t('workbench.createWi.creating') : t('workbench.createWi.create')}
          </button>
          <button
            onClick={() => { setSelectedIds(new Set()); setSelectedSimoPairs({}); setWiName('') }}
            className="text-xs text-slate-400 hover:text-slate-600"
          >
            {t('workbench.createWi.clearSelection')}
          </button>
        </div>
      )}

      {/* WiItemInspector 右抽屜（ADR-022 B-4） */}
      {inspector && (
        <WiItemInspector
          moduleId={inspector.wi.id}
          moduleName={inspector.wi.name_zh}
          rowIndex={inspector.rowIndex}
          row={inspector.row}
          onClose={() => setInspector(null)}
          onSaved={() => showToast(t('workbench.toast.rowSaved'), 'ok')}
        />
      )}

      {/* ═══ NL 覆蓋/填空對話框（audit §1.13） ═══ */}
      {nlAskOpen && nlResult && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setNlAskOpen(false)}
        >
          <div
            className="bg-white rounded-xl border shadow-2xl p-5 max-w-sm w-full mx-4 space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <h3 className="font-semibold text-base">{t('workbench.nl.askTitle')}</h3>
            <p className="text-sm text-slate-600">{t('workbench.nl.askMessage')}</p>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => applyNlDraft(nlResult, 'overwrite')}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium"
              >
                {t('workbench.nl.askOverwrite')}
              </button>
              <button
                onClick={() => applyNlDraft(nlResult, 'fill-empty')}
                className="px-4 py-2 border border-blue-300 text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-50"
              >
                {t('workbench.nl.askFillEmpty')}
              </button>
              <button
                onClick={() => setNlAskOpen(false)}
                className="px-4 py-1.5 text-slate-500 text-sm hover:text-slate-700"
              >
                {t('workbench.nl.askCancel')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
