// DsxA3Suggestion — DSX 建議移動距離（a3 專用；MVP，契約草案 §1.1／§3.1）
// 只在 A2（GM 的 a3 slot，from→to 物件間移動）出現，不做 a0／a6（見契約草案 §0.2）。
// D4（ADR-031）：這是建議值不是權威——距離一律標「暫定值」徽章，且絕不自動寫入
// a3.reach_cm／a3.foot_cm；使用者必須明確點「填入伸手」或「填入腳步」才落值。
// 掛載點：`WiWorkbench.tsx` 既有的 a3/from/to 建立器面板（契約草案 §3.1 掛載點更正，
// 2026-08-24）——那裡組的多半是尚未存檔的新列，故 `wiRowId` 選填：有則帶（已存檔列可
// 補寫出處快照），沒有就不帶（後端一樣回查詢結果，只是不落 wi_row_dsx_suggestions）。
//
// 伸手／腳步互斥已在 2026-08-24 拿掉：MOST 引擎算 TMU 時對 A 格取
// `max(reach_index, foot_index, twist_index)`，同一格 reach_cm／foot_cm 本來就允許同時有值，
// 之前做互斥限制過頭了——「填入伸手」「填入腳步」兩顆按鈕現在各自獨立，互不影響對方欄位。
// `horizontal_cm`／`vertical_cm`（DSX 原始分量，後端 A3DistanceOut 新增欄位）只是多顯示
// 給使用者參考，**不是**「水平分量＝腳步建議、垂直分量＝伸手建議」這種一一對應
// （ADR-031 P1 尚未定案這種拆分規則），文案上要講清楚。
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ABand } from '../wi-workbench/cycle'
import { cmToBandValue } from '../wi-workbench/cycle'
import { useDsxA3Distance, type DsxA3DistanceResponse } from './dsxA3Distance'
import { ApiError } from '../../shared/api/client'

export interface DsxA3SuggestionProps {
  /** 已存檔的 WiRow 主鍵；選填——只有已經存進 `wi_rows` 的列才有。有帶，後端會
   *  額外 upsert 一筆 §2.2 的出處快照；沒帶（尚未存檔的新列）查詢一樣正常運作，
   *  只是不落那筆快照。 */
  wiRowId?: string
  fromVocabId: string
  toVocabId: string
  bandsReach: ABand[]
  bandsFoot: ABand[]
  onFillReach: (bandedCm: number) => void
  onFillFoot: (bandedCm: number) => void
}

export function DsxA3Suggestion({
  wiRowId, fromVocabId, toVocabId, bandsReach, bandsFoot, onFillReach, onFillFoot,
}: DsxA3SuggestionProps) {
  const { t } = useTranslation()
  const dsx = useDsxA3Distance()
  const [result, setResult] = useState<DsxA3DistanceResponse | null>(null)
  // reach／foot 各自獨立記錄「這個 widget 有沒有填過那一格、填的是什麼」；兩者互不影響
  // （沒有互斥），所以拆成兩個 state 而不是像互斥版那樣共用一個 `filled` 值。
  const [filledReach, setFilledReach] = useState<{ cm: number; band: number } | null>(null)
  const [filledFoot, setFilledFoot] = useState<{ cm: number; band: number } | null>(null)
  const canQuery = !!fromVocabId && !!toVocabId

  // from/to 換了 → 舊建議已經對不上，清掉避免誤導使用者填入錯誤配對的距離
  useEffect(() => {
    setResult(null)
    setFilledReach(null)
    setFilledFoot(null)
  }, [fromVocabId, toVocabId])

  function runQuery() {
    if (!canQuery) return
    dsx.mutate(
      { ...(wiRowId ? { wi_row_id: wiRowId } : {}), from_vocab_id: fromVocabId, to_vocab_id: toVocabId },
      { onSuccess: setResult },
    )
  }

  function fill(target: 'reach' | 'foot', distanceCm: number) {
    const bands = target === 'reach' ? bandsReach : bandsFoot
    const band = cmToBandValue(distanceCm, bands)
    if (target === 'reach') {
      onFillReach(band)
      setFilledReach({ cm: distanceCm, band })
    } else {
      onFillFoot(band)
      setFilledFoot({ cm: distanceCm, band })
    }
  }

  return (
    <div className="space-y-2 border-t border-dashed border-slate-200 pt-3" data-testid="dsx-a3-suggestion">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-600">{t('workbench.dsxA3.title')}</span>
        <button
          type="button"
          onClick={runQuery}
          disabled={!canQuery || dsx.isPending}
          className="px-2.5 py-1 text-xs rounded border border-sky-300 text-sky-700 bg-sky-50 hover:bg-sky-100 disabled:opacity-40 disabled:cursor-not-allowed"
          data-testid="dsx-a3-query-btn"
        >
          {dsx.isPending ? t('workbench.dsxA3.querying') : t('workbench.dsxA3.query')}
        </button>
      </div>

      {!canQuery && (
        <p className="text-[11px] text-slate-400">{t('workbench.dsxA3.needFromTo')}</p>
      )}

      {dsx.isError && (
        <p className="text-[11px] text-red-600 break-all" data-testid="dsx-a3-error">
          {t('workbench.dsxA3.queryFailed', { message: apiErrorText(dsx.error) })}
        </p>
      )}

      {result && !result.available && (
        <p className="text-[11px] text-amber-700" data-testid="dsx-a3-unavailable">
          {result.reason
            ? t(`workbench.dsxA3.reason.${result.reason}`)
            : t('workbench.dsxA3.queryFailed', { message: 'available=false without reason' })}
        </p>
      )}

      {/* A3DistanceOut 是扁平 optional schema，不是判別聯合：`available` 不會讓 TS 自動窄化
          出 distance_cm 非 null，這裡自己判斷（見 dsxA3Distance.ts 檔頭註）。 */}
      {result && result.available && result.distance_cm != null && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 space-y-1.5" data-testid="dsx-a3-result">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded border bg-amber-100 text-amber-700 border-amber-300">
              {t('workbench.dsxA3.provisionalBadge')}
            </span>
            <span className="text-sm font-bold text-amber-800">{result.distance_cm} cm</span>
          </div>
          {/* 水平/垂直分量：DSX 原始分量，僅供參考——不是「水平分量該填腳步、垂直分量該填
              伸手」這種系統自動拆分建議（沒有這條規則，ADR-031 P1 未定案），文案要講清楚。
              兩個數值各自獨立的 testid，e2e 才能精確比對到「哪個數字配哪個標籤」，
              不會被水平/垂直對調的錯誤蒙混過去（見 e2e H-DSX-2 的註解）。 */}
          {(result.horizontal_cm != null || result.vertical_cm != null) && (
            <p className="text-[10px] text-slate-500" data-testid="dsx-a3-components">
              {result.horizontal_cm != null && (
                <span data-testid="dsx-a3-component-horizontal">
                  {t('workbench.dsxA3.horizontalComponent', { cm: result.horizontal_cm })}
                </span>
              )}
              {result.horizontal_cm != null && result.vertical_cm != null && ' / '}
              {result.vertical_cm != null && (
                <span data-testid="dsx-a3-component-vertical">
                  {t('workbench.dsxA3.verticalComponent', { cm: result.vertical_cm })}
                </span>
              )}
              {t('workbench.dsxA3.componentsDisclaimer')}
            </p>
          )}
          {result.measure_from_mode && (
            <p className="text-[10px] text-slate-500">
              {t('workbench.dsxA3.measureFrom')}: {result.measure_from_mode}
            </p>
          )}
          {(result.warnings?.length ?? 0) > 0 && (
            <ul className="text-[10px] text-amber-700 list-disc list-inside">
              {result.warnings!.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={() => fill('reach', result.distance_cm!)}
              aria-pressed={!!filledReach}
              className={
                filledReach
                  ? 'px-2 py-1 text-[11px] rounded bg-emerald-100 border border-emerald-400 text-emerald-800'
                  : 'px-2 py-1 text-[11px] rounded bg-white border border-amber-300 text-amber-800 hover:bg-amber-100'
              }
              data-testid="dsx-a3-fill-reach"
            >
              {filledReach ? `✓ ${t('workbench.dsxA3.fillReach')}` : t('workbench.dsxA3.fillReach')}
            </button>
            <button
              type="button"
              onClick={() => fill('foot', result.distance_cm!)}
              aria-pressed={!!filledFoot}
              className={
                filledFoot
                  ? 'px-2 py-1 text-[11px] rounded bg-emerald-100 border border-emerald-400 text-emerald-800'
                  : 'px-2 py-1 text-[11px] rounded bg-white border border-amber-300 text-amber-800 hover:bg-amber-100'
              }
              data-testid="dsx-a3-fill-foot"
            >
              {filledFoot ? `✓ ${t('workbench.dsxA3.fillFoot')}` : t('workbench.dsxA3.fillFoot')}
            </button>
          </div>
        </div>
      )}

      {filledReach && (
        <p className="text-[11px] text-emerald-700" data-testid="dsx-a3-filled-reach">
          {t('workbench.dsxA3.filledReach', { raw: filledReach.cm, band: filledReach.band })}
        </p>
      )}
      {filledFoot && (
        <p className="text-[11px] text-emerald-700" data-testid="dsx-a3-filled-foot">
          {t('workbench.dsxA3.filledFoot', { raw: filledFoot.cm, band: filledFoot.band })}
        </p>
      )}
    </div>
  )
}

function apiErrorText(err: unknown): string {
  if (err instanceof ApiError) return err.humanMessage
  return err instanceof Error ? err.message : String(err)
}
