import { useTranslation } from 'react-i18next'
import { useActiveRuleSet } from '../../shared/api/useActiveRuleSet'
import { useRuleSetOptions, useVocab, type RuleOption } from './api'
import { payloadToState, shortNarr } from './cycle'
import type { Row } from './store'

/**
 * 動作列的顯示敘述。**結果不得存進 state**：`i18n.t` 的產物一旦凍結，切成英文後
 * 先前加的列就永遠停在加入當下的語言（新加的才是英文）。同 repo 的正解是
 * `ActionModuleWorkspace` 的 `miSentence`——每次 render 重算。
 *
 * 已儲存列只消費後端已治理的欄位：`zh-TW` 選 `narrative_zh`，`en` 選
 * `narrative_en`（ADR-032 D3.3）。兩欄不互相翻譯、合併或猜測；英文欄位缺值時，
 * 已儲存列維持空白。尚未存檔的本地列沒有後端敘述，才使用既有 `shortNarr` 預覽。
 *
 * 用 hook 包起來是因為預覽句要查 rule-set 選項標籤與詞彙名；兩個 query 都已被
 * 工作台掛載過，這裡是 react-query 快取讀取，不會多打 API。
 */
export function useRowNarr(): (r: Row) => string {
  const { i18n } = useTranslation()
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
    const isEnglish = i18n.resolvedLanguage === 'en' || i18n.language === 'en'
    if (isEnglish) {
      // null means no governed English narrative was persisted; '' is an explicit value.
      if (r.narrEn !== null) return r.narrEn
      // A loaded row may still have sub_activity as the zh display fallback. Do not expose it
      // as English and do not fabricate a replacement narrative for a saved row.
      if (r.narr) return ''
    } else if (r.narr) {
      return r.narr
    }

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
