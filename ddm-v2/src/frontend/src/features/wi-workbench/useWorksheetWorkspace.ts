import { useEffect } from 'react'
import { useLevelStore } from '../level-system/store'
import { type GroupMeta, type LevelCell } from '../level-system/logic'
import { useWorksheet } from './api'
import { useWiStore } from './store'

export function useWorksheetWorkspace(worksheetId: string) {
  const query = useWorksheet(worksheetId)
  const setRows = useWiStore((state) => state.setRows)

  useEffect(() => {
    const worksheet = query.data
    if (!worksheet || worksheet.worksheet_id !== worksheetId) {
      setRows([])
      useLevelStore.getState().hydrate({}, {}, 0)
      return
    }

    setRows(worksheet.rows.map((row) => ({
      id: row.wi_row_id,
      seq: (row.cycle?.seq_kind === 'CM' ? 'CM' : 'GM') as 'GM' | 'CM',
      handCode: row.hand ?? 'RH',
      freq: row.frequency,
      simoGroup: row.simo_group_id ?? '',
      nv: {
        obj: row.object_vocab_id ?? '',
        from: row.from_vocab_id ?? '',
        to: row.to_vocab_id ?? '',
      },
      narr: row.cycle?.narrative ?? row.sub_activity ?? '',
      tmu: row.cycle?.total_tmu ?? 0,
      seconds: row.cycle?.total_seconds ?? 0,
      payload: row.cycle?.slot_inputs ?? null,
    })))

    const levelMap: Record<string, LevelCell> = {}
    const groupMeta: Record<string, GroupMeta> = {}
    worksheet.rows.forEach((row, index) => {
      const level = row.level
      levelMap[row.wi_row_id] = {
        coefficient: level?.coefficient ?? 1,
        number: level?.number ?? '',
        number_count: level?.number_count ?? '',
        level: level?.level ?? String(index + 1),
        countersignature: level?.countersignature ?? '',
        machine_count: 1,
        manpower: 1,
      }
      const countersignature = (level?.countersignature ?? '').trim()
      if (countersignature && !groupMeta[countersignature]) {
        groupMeta[countersignature] = {
          type: countersignature.startsWith('cub') ? 'cub' : 'sub',
          parent: level?.parent_countersignature ?? '',
          seq: index,
        }
      }
    })
    useLevelStore.getState().hydrate(levelMap, groupMeta, worksheet.rows.length)
  }, [query.data, setRows, worksheetId])

  return query
}