import { useActiveRuleSet } from '../../shared/api/useActiveRuleSet'
import { useRuleSetOptions, useVocab, type RuleOption } from './api'
import { payloadToState, shortNarr } from './cycle'
import type { Row } from './store'

/**
 * 動作列的顯示敘述。**結果不得存進 state**：`i18n.t` 的產物一旦凍結，切成英文後
 * 先前加的列就永遠停在加入當下的語言（新加的才是英文）。同 repo 的正解是
 * `ActionModuleWorkspace` 的 `miSentence`——每次 render 重算。
 *
 * 兩個來源，優先序固定：
 *   1. `row.narr` 非空＝後端敘述（`most_cycles.narrative_zh`，權威），照用。
 *   2. 尚未存檔的本地列沒有後端敘述，即時重算**簡化版預覽句**（`shortNarr`）。
 *
 * 用 hook 包起來是因為預覽句要查 rule-set 選項標籤與詞彙名；兩個 query 都已被
 * 工作台掛載過，這裡是 react-query 快取讀取，不會多打 API。
 */
export function useRowNarr(): (r: Row) => string {
  const active = useActiveRuleSet()
  const { data: opts } = useRuleSetOptions(active.data?.code)
  const { data: vocab = [] } = useVocab()

  const vname = (_kind: string, id: string) => vocab.find(v => v.id === id)?.name_zh ?? ''
  const label = (kind: string, code: string) => {
    const m: Record<string, RuleOption[]> = {
      g: opts?.g ?? [], p_base: opts?.p_bases ?? [], m_verb: opts?.m_verbs ?? [],
    }
    return m[kind]?.find(o => o.code === code)?.label ?? ''
  }

  return (r: Row) => {
    if (r.narr) return r.narr
    // payload（CycleIn）只帶得回格位；情境欄（object/from/to/component/where）在 Row 上
    const st = payloadToState((r.payload ?? {}) as Record<string, unknown>)
    st.seq = r.seq
    st.handCode = r.handCode
    st.freq = r.freq
    st.simoGroup = r.simoGroup
    st.nv = {
      obj: r.nv.obj, from: r.nv.from, to: r.nv.to,
      component: r.nv.component ?? '', where: r.nv.where ?? '',
    }
    return shortNarr(st, label, vname)
  }
}
