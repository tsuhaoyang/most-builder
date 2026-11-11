// 共用存檔 hook（ADR-035 D10 F1）：mutation + setRevisionMeta + 三個 invalidateQueries。
// WiWorkbench.doSave 與作業版「儲存」共用，行為一致。
import { useQueryClient } from '@tanstack/react-query'
import { useSaveWorksheet, type SaveResult } from './api'
import { useWiStore } from './store'
import type { SaveBody } from './savePayload'

export function useSaveWorkspace(worksheetId: string) {
  const save = useSaveWorksheet(worksheetId)
  const qc = useQueryClient()

  async function saveBody(body: SaveBody): Promise<SaveResult> {
    const res = await save.mutateAsync(body)
    if (typeof res.revision_no === 'number') {
      useWiStore.getState().setRevisionMeta({
        revisionNo: res.revision_no,
        contentHash: res.content_hash ?? null,
      })
    }
    qc.invalidateQueries({ queryKey: ['wi-preview'] })
    qc.invalidateQueries({ queryKey: ['versions'] })
    qc.invalidateQueries({ queryKey: ['worksheet', worksheetId] })
    return res
  }

  return { saveBody, isPending: save.isPending }
}
