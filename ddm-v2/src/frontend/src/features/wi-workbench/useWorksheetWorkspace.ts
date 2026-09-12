import { useEffect } from 'react'
import { useLevelStore } from '../level-system/store'
import { type GroupMeta, type LevelCell } from '../level-system/logic'
import { useWorksheet } from './api'
import { useWiStore } from './store'

export function useWorksheetWorkspace(worksheetId: string) {
  const query = useWorksheet(worksheetId)
  const setRows = useWiStore((state) => state.setRows)
  const setRevisionMeta = useWiStore((state) => state.setRevisionMeta)

  useEffect(() => {
    const worksheet = query.data
    if (!worksheet || worksheet.worksheet_id !== worksheetId) {
      setRows([])
      setRevisionMeta({ revisionNo: null, contentHash: null })
      useLevelStore.getState().hydrate({}, {}, 0)
      return
    }

    setRows(worksheet.rows.map((row) => ({
      id: row.wi_row_id,
      seq: (row.cycle?.seq_kind === 'CM' ? 'CM' : 'GM') as 'GM' | 'CM',
      handCode: row.hand ?? 'RH',
      freq: row.frequency,
      simoGroup: row.simo_group_id ?? '',
      wiGroup: row.wi_group ?? null,
      nv: {
        obj: row.object_vocab_id ?? '',
        from: row.from_vocab_id ?? '',
        to: row.to_vocab_id ?? '',
      },
      narr: row.cycle?.narrative ?? row.sub_activity ?? '',
      narrEn: row.cycle?.narrative_en ?? null,
      tmu: row.cycle?.total_tmu ?? 0,
      seconds: row.cycle?.total_seconds ?? 0,
      payload: row.cycle?.slot_inputs ?? null,
    })))
    setRevisionMeta({
      revisionNo: worksheet.revision_no ?? 1,
      contentHash: worksheet.content_hash ?? null,
    })

    const levelMap: Record<string, LevelCell> = {}
    const groupMeta: Record<string, GroupMeta> = {}
    const workerCubMeta: Record<string, { seq: number }> = {}
    worksheet.rows.forEach((row, index) => {
      const level = row.level
      const tags = row.lb_tags
      levelMap[row.wi_row_id] = {
        coefficient: level?.coefficient ?? 1,
        number: level?.number ?? '',
        number_count: level?.number_count ?? '',
        level: level?.level ?? String(index + 1),
        countersignature: level?.countersignature ?? '',
        machine_count: 1,
        manpower: 1,
        // ADR-035 D10 F1：hydrate 還原 8 個 LB 標記（後端 read_worksheet 已回 lb_tags；舊註解過時）。
        workerCub: tags?.worker_cub ?? '',
        offline: tags?.offline ?? false,
        segment: tags?.segment ?? '',
        stationPin: tags?.station_pin ?? '',
        isGeneral: tags?.is_general ?? false,
        generalRole: tags?.general_role ?? '',
        mergeLock: tags?.merge_lock ?? false,
        actionType: tags?.action_type ?? '',
        // ADR-035 D10 §3.4：機台三態（null/false/true）由 read_worksheet lb_tags 還原（B7）。
        machineUnattended: tags?.machine_unattended ?? null,
      }
      const countersignature = (level?.countersignature ?? '').trim()
      if (countersignature && !groupMeta[countersignature]) {
        groupMeta[countersignature] = {
          type: countersignature.startsWith('cub') ? 'cub' : 'sub',
          parent: level?.parent_countersignature ?? '',
          seq: index,
        }
      }
      // workerCubMeta 依出現順序重建（F1；wcub 是與 countersignature 正交的第二維度）
      const wc = (tags?.worker_cub ?? '').trim()
      if (wc && !workerCubMeta[wc]) workerCubMeta[wc] = { seq: index }
    })

    // I-1：同一 top-level chain 的 level 字串統一（後端對非首列回 null → 上面補了 String(index+1) 會讓反投影讀錯）。
    // top-level chain = countersignature 群組（cub 巢狀在 sub 時併入 sub），或單一未分組列。
    const topOf = (cs: string): string => {
      const c = cs.trim()
      if (!c) return ''
      const parent = (groupMeta[c]?.parent ?? '').trim()
      return parent || c
    }
    const chainHeadLevel: Record<string, string> = {}
    worksheet.rows.forEach((row) => {
      const top = topOf(levelMap[row.wi_row_id].countersignature)
      if (top && !(top in chainHeadLevel)) chainHeadLevel[top] = levelMap[row.wi_row_id].level
    })
    worksheet.rows.forEach((row) => {
      const top = topOf(levelMap[row.wi_row_id].countersignature)
      if (top) levelMap[row.wi_row_id].level = chainHeadLevel[top]
    })

    useLevelStore.getState().hydrate(levelMap, groupMeta, worksheet.rows.length, workerCubMeta, worksheet.rows.length)
  }, [query.data, setRows, setRevisionMeta, worksheetId])

  return query
}
