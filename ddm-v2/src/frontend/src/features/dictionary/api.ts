import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiDelete, apiDeleteJson, apiGet, apiPatch, apiPost, apiPut } from '../../shared/api/client'

/**
 * MOST 字典（資料層稱 rule-set；ADR-023 §3.1 明記兩者同物）API。
 *
 * 兩種形狀（ADR-023 §2）：
 * - `kind='options'`：有 code 的選項表 → 單筆 CRUD
 * - `kind='bands'`：區間帶表，無 code → 只能整組替換 `PUT /params/{param}/bands`
 */

export interface RuleSetSummary {
  id: string
  code: string
  name_zh: string
  status: 'draft' | 'published' | 'retired'
  is_active: boolean
  provenance: 'certified_import' | 'manual' | 'cloned' | null
  created_at: string | null
  notes: string | null
  multiplier: number
}

export type OptionRow = Record<string, unknown> & { id: string }

export interface ParamOptionsResponse {
  rule_set_code: string
  param: string
  section: string
  kind: 'options' | 'bands'
  items: OptionRow[]
}

export interface Synonym {
  id: string
  parameter: string
  option_code: string
  synonym_raw: string
  synonym_norm: string
  priority: number
}

/**
 * A 的次級選擇在 API 上叫 `component`，其餘叫 `section`
 * （後端 SECTION_QUERY_NAME）。單一區塊的參數（B/G/X/I）不帶查詢參數。
 */
function sectionQuery(param: string, section: string): string {
  if (section === 'default') return ''
  const name = param === 'A' ? 'component' : 'section'
  return `?${name}=${encodeURIComponent(section)}`
}

const base = (code: string, param: string) =>
  `/api/v2/rule-sets/${encodeURIComponent(code)}/params/${param}`

// ── 版本級 ─────────────────────────────────────────────────────────

export const useRuleSetVersions = () =>
  useQuery({
    queryKey: ['rule-sets'],
    queryFn: () => apiGet<RuleSetSummary[]>('/api/v2/rule-sets'),
  })

export function useVersionMutations() {
  const qc = useQueryClient()
  const done = () => {
    void qc.invalidateQueries({ queryKey: ['rule-sets'] })
    void qc.invalidateQueries({ queryKey: ['rule-set-active'] })
  }
  return {
    cloneDraft: useMutation({
      // new_code 不傳 → 後端自動命名 {code}_DRAFT_{YYYYMMDDHHMM}（ADR-023 §3.2）
      mutationFn: (code: string) =>
        apiPost<{ code: string; name_zh: string }>(
          `/api/v2/rule-sets/${encodeURIComponent(code)}/clone-draft`,
          {},
        ),
      onSuccess: done,
    }),
    publish: useMutation({
      mutationFn: (code: string) =>
        apiPost<unknown>(`/api/v2/rule-sets/${encodeURIComponent(code)}/publish`),
      onSuccess: done,
    }),
    activate: useMutation({
      mutationFn: (code: string) =>
        apiPost<unknown>(`/api/v2/rule-sets/${encodeURIComponent(code)}/activate`),
      onSuccess: done,
    }),
    retire: useMutation({
      mutationFn: (code: string) =>
        apiPost<unknown>(`/api/v2/rule-sets/${encodeURIComponent(code)}/retire`),
      onSuccess: done,
    }),
    // D3b：retired → published；is_active 維持 false（解除封存 ≠ 啟用）
    unretire: useMutation({
      mutationFn: (code: string) =>
        apiPost<unknown>(`/api/v2/rule-sets/${encodeURIComponent(code)}/unretire`),
      onSuccess: done,
    }),
    // D3b：僅 draft 可刪；13 張子表由 DB CASCADE 連帶清除
    remove: useMutation({
      mutationFn: (code: string) =>
        apiDeleteJson<unknown>(`/api/v2/rule-sets/${encodeURIComponent(code)}`),
      onSuccess: done,
    }),
  }
}

/**
 * 各引用表的中文名（`RULE_SET_IN_USE` 的 `detail.references` 鍵）。
 *
 * ⚠️ 這份對照表必須與後端 `src/ddm_v2/services/v2/rule_set_service.py` 的
 * `_RESTRICT_REFERRERS` 保持同步。後端新增一張指向 rule_sets 的 RESTRICT FK 時，
 * **一定要回來這裡補中文名**——後端那份清單有 pg_catalog 反查測試守著
 * （`test_count_references_covers_every_restrict_referrer`），前端這份沒有測試會擋，
 * 漏加不會壞掉、只會靜靜降級：`describeInUse` 的 fallback 是原始表名，
 * 使用者看到的是「此草稿已被 3 筆ai_parse_runs引用，無法刪除。」這種中英夾雜的句子。
 * 這件事已經發生過一次：v2_0026（ai_parse_runs）／v2_0028（ai_parse_jobs）加了 FK，
 * 後端清單與這裡都漏補。
 *
 * 命名原則：用 IE 使用者看得懂的業務名詞（不是表名直譯），讓人一眼知道
 * 「這個規則版本被什麼東西用著、所以不能刪」。
 */
const REFERRER_ZH: Record<string, string> = {
  most_cycles: '動作循環',
  most_worksheets: '工時表',
  motion_module_versions: '動作模組版本',
  ai_parse_runs: '語句解析紀錄',      // v2_0026：一次語句解析的執行紀錄（互動式／匯入逐列共用）
  ai_parse_jobs: '批次解析作業',      // v2_0028：Excel 匯入的批次解析作業
}

/**
 * 把 `RULE_SET_IN_USE` 的引用筆數轉成人話。
 * 非該錯誤碼回 null——呼叫端沿用一般錯誤訊息。
 */
export function describeInUse(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.code !== 'RULE_SET_IN_USE') return null
  const refs = (err.detail as { references?: Record<string, number> })?.references
  if (!refs) return err.humanMessage
  const parts = Object.entries(refs)
    .filter(([, n]) => n > 0)
    .map(([table, n]) => `${n} 筆${REFERRER_ZH[table] ?? table}`)
  if (parts.length === 0) return err.humanMessage
  return `此草稿已被 ${parts.join('、')}引用，無法刪除。`
}

// ── 差異（D7 / H-1）─────────────────────────────────────────────────

export interface FieldDelta { before: unknown; after: unknown }
export interface DiffAdded { key: string; after: Record<string, unknown> }
export interface DiffRemoved { key: string; before: Record<string, unknown> }
export interface DiffChanged { key: string; fields: Record<string, FieldDelta> }
export interface DiffSection {
  added?: DiffAdded[]
  removed?: DiffRemoved[]
  changed?: DiffChanged[]
}
export interface DiffSummary {
  added: number
  removed: number
  changed: number
  changed_sections: string[]
  header_changed: string[]
  identical: boolean
}
export interface RuleSetDiff {
  target_code: string
  target_status: string
  /** 比較基準＝目前 active 版本；呈現時必須標明。 */
  base_code: string
  base_is_active: boolean
  /** target 本身就是 active → 沒有比較對象（與 identical 不同義）。 */
  compared_with_self: boolean
  /** 本版 clone 自哪一版；查不到 clone 紀錄＝null（不得猜成 base）。 */
  source_code: string | null
  /** source 是否等於 base；null＝不知道。 */
  base_is_source: boolean | null
  /** base_is_source === false 時後端附上的說明（優先顯示，不要自己造句）。 */
  lineage_note?: string
  diff: {
    header: Record<string, FieldDelta>
    sections: Record<string, DiffSection>
    row_counts: Record<string, { before: number; after: number }>
    summary: DiffSummary
  }
}

/**
 * 本版相對目前 active 版本的值差異。
 *
 * **前端不自行比對兩份 full**（守則 §7 第 3 條）：差異一律用後端算好的。
 * 取不到就是取不到——呼叫端必須顯示錯誤，不得當成「無差異」而放行。
 */
export const useRuleSetDiff = (code: string | null, enabled = true) =>
  useQuery({
    queryKey: ['rule-set-diff', code],
    queryFn: () => apiGet<RuleSetDiff>(`/api/v2/rule-sets/${encodeURIComponent(code!)}/diff`),
    enabled: !!code && enabled,
  })

/** 匯出（ADR-023 §3.6，D3）。回 `PUT /full` 對稱形狀 ＋ schema_version/exported_at。 */
export const exportRuleSet = (code: string) =>
  apiGet<Record<string, unknown>>(`/api/v2/rule-sets/${encodeURIComponent(code)}/export`)

// ── 選項/帶級 ───────────────────────────────────────────────────────

export const useParamOptions = (code: string, param: string, section: string) =>
  useQuery({
    queryKey: ['rule-set-params', code, param, section],
    // active_only 留 false：編輯畫面必須看得到已停用的列才能重新啟用
    queryFn: () =>
      apiGet<ParamOptionsResponse>(`${base(code, param)}/options${sectionQuery(param, section)}`),
    enabled: !!code,
  })

export const useSynonyms = (code: string) =>
  useQuery({
    queryKey: ['rule-set-synonyms', code],
    queryFn: () => apiGet<Synonym[]>(`/api/v2/rule-sets/${encodeURIComponent(code)}/synonyms`),
    enabled: !!code,
  })

export interface SynonymCreateIn {
  parameter: string
  option_code: string
  synonym_raw: string
  priority?: number
}

/**
 * 同義詞增刪（ADR-024 §5）。
 *
 * ⚠️ **刻意不經 clone-on-write gate**：同義詞是 ADR-014 明定「published/certified 版本
 * 唯一可後補的資料」。值變更（改 TMU）才需先 clone-draft；同義詞直接寫入目標版本。
 * 呼叫端**不得**把這些 mutation 包進 OptionEditor 的 `guarded()`（那會 onRequestEdit →
 * 撞 clone 對話框）。retired（終態）由後端回 409 RULE_SET_RETIRED，前端另在 UI 隱藏控制。
 */
export function useSynonymMutations(code: string) {
  const qc = useQueryClient()
  const done = () => {
    void qc.invalidateQueries({ queryKey: ['rule-set-synonyms', code] })
  }
  return {
    create: useMutation({
      mutationFn: (payload: SynonymCreateIn) =>
        apiPost<Synonym>(`/api/v2/rule-sets/${encodeURIComponent(code)}/synonyms`, payload),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (synId: string) =>
        apiDelete(`/api/v2/rule-sets/${encodeURIComponent(code)}/synonyms/${encodeURIComponent(synId)}`),
      onSuccess: done,
    }),
  }
}

export function useOptionMutations(code: string, param: string, section: string) {
  const qc = useQueryClient()
  const q = sectionQuery(param, section)
  const done = () => {
    void qc.invalidateQueries({ queryKey: ['rule-set-params', code, param, section] })
  }
  return {
    create: useMutation({
      mutationFn: (payload: Record<string, unknown>) =>
        apiPost<OptionRow>(`${base(code, param)}/options${q}`, payload),
      onSuccess: done,
    }),
    update: useMutation({
      mutationFn: ({ optionCode, payload }: { optionCode: string; payload: Record<string, unknown> }) =>
        apiPatch<OptionRow>(
          `${base(code, param)}/options/${encodeURIComponent(optionCode)}${q}`,
          payload,
        ),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (optionCode: string) =>
        apiDelete(`${base(code, param)}/options/${encodeURIComponent(optionCode)}${q}`),
      onSuccess: done,
    }),
    duplicate: useMutation({
      mutationFn: (optionCode: string) =>
        apiPost<OptionRow>(
          `${base(code, param)}/options/${encodeURIComponent(optionCode)}/duplicate${q}`,
        ),
      onSuccess: done,
    }),
    /** 帶型整組替換：單筆增刪不提供（會產生非法中間態，ADR-023 §2）。 */
    replaceBands: useMutation({
      mutationFn: (items: Record<string, unknown>[]) =>
        apiPut<unknown>(`${base(code, param)}/bands${q}`, { items }),
      onSuccess: done,
    }),
  }
}
