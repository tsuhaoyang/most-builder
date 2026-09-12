// 存檔 payload builder（ADR-035 D10 F1）：從 WiWorkbench.doSave 抽出，作業版與工時表共用同一份 body。
// body 除每列多 wi_group 外，與抽出前逐鍵相同（回歸：e2e/wp12-lb-tags.spec.ts）。
import type { Row } from './store'
import type { LevelPayloadRow } from '../level-system/logic'

export interface SaveBody {
  base_revision?: number
  rows: Array<Record<string, unknown>>
}

/** rows（wi 狀態）＋ levelPayload（derive() 輸出，逐列對應）→ PUT /worksheets/{id} 的 body。 */
export function buildSaveBody(
  rows: Row[],
  levelPayload: LevelPayloadRow[],
  baseRevision: number | null,
): SaveBody {
  return {
    base_revision: baseRevision ?? undefined,
    rows: rows.map((r, i) => {
      const e = (levelPayload[i] || {}) as Partial<LevelPayloadRow>
      return {
        id: r.id, seq_no: i + 1, hand: r.handCode,
        object_vocab_id: r.nv.obj || null,
        from_vocab_id: r.nv.from || null, to_vocab_id: r.nv.to || null,
        frequency: r.freq, simo_group_id: r.simoGroup || null,
        // Backend regenerates narrative_zh/narrative_en from the pinned rule-set; never send
        // the locale-dependent display selection back as the Chinese narrative input.
        narrative: r.narr || null,
        wi_group: r.wiGroup ?? null,   // ADR-035 D10：作業名稱
        cycle: r.payload,
        level: {
          coefficient: e.coefficient ?? 1, ascription: e.ascription ?? 'main', level: e.level ?? String(i + 1),
          countersignature: e.countersignature ?? null, parent_countersignature: e.parent_countersignature ?? null,
          order: e.order ?? null, number: e.number ?? null, number_count: e.number_count ?? null,
          machine_count: 1, manpower: 1,
          // WP12（ADR-035）LB projection tags — 預設對齊 LevelFieldsIn（字串 ?? null、bool ?? false）
          worker_cub: e.worker_cub ?? null, offline: e.offline ?? false, segment: e.segment ?? null,
          station_pin: e.station_pin ?? null, is_general: e.is_general ?? false, general_role: e.general_role ?? null,
          merge_lock: e.merge_lock ?? false, action_type: e.action_type ?? null,
        },
      }
    }),
  }
}
