// DSX 3D 擺放介面入口（內部／工程用，非正式對外功能）。
// DSX 那頁沒有正式部署（dev server、零認證），底層 NVIDIA Kit 只支援單一 WebRTC 觀看者——
// 第二個人開會看到黑畫面或連不上（架構限制，不是 bug）。這件事前端解決不了，但**必須**在
// 開啟前明確警告使用者，所以點擊入口後一律先跳確認對話框，使用者確認後才真的開 iframe modal。
//
// 網址來自後端 GET /api/v2/dsx/ui-url（{url: string | null}）；url 為 null 代表尚未設定，
// 入口本身即為 disabled 並顯示原因——不讓使用者點了才發現沒東西可看。查詢在掛載時就發出
// （而非等點擊才查），才能在使用者點擊前就決定入口是否可用。
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useDsxUiUrl } from './dsxUiUrl'

export function DsxUiEntry() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useDsxUiUrl()
  const [confirming, setConfirming] = useState(false)
  const [open, setOpen] = useState(false)
  const url = data?.url ?? null
  const disabled = !url
  // 首次查詢中／查詢失敗／確實未設定（url===null）三種狀態原本都顯示同一句
  // 「尚未設定」，使用者無法分辨是不是該重試——分開顯示對應原因。
  const reasonText = isLoading
    ? t('workbench.dsxUi.loadingReason')
    : isError
      ? t('workbench.dsxUi.queryFailedReason')
      : t('workbench.dsxUi.unavailableReason')

  // Esc 關閉＝釋放唯一的 WebRTC 觀看者名額，這個操作的便利性有實質價值。
  useEffect(() => {
    if (!open) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])

  return (
    <>
      <span className="inline-flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={disabled}
          title={disabled ? reasonText : undefined}
          className="text-xs px-2.5 py-1 border border-slate-300 text-slate-500 rounded-lg hover:bg-slate-50 hover:text-slate-700 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
          data-testid="dsx-ui-entry-btn"
        >
          {t('workbench.dsxUi.entryLabel')}
        </button>
        {disabled && (
          <span className="text-[11px] text-slate-400" data-testid="dsx-ui-unavailable-reason">
            {reasonText}
          </span>
        )}
      </span>

      {confirming && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
          role="dialog" aria-modal="true"
          onClick={() => setConfirming(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl w-full max-w-md"
            data-testid="dsx-ui-confirm-dialog"
            onClick={e => e.stopPropagation()}
          >
            <div className="px-4 py-3 border-b font-medium">{t('workbench.dsxUi.confirmTitle')}</div>
            <div className="px-4 py-4 text-sm text-slate-700">
              <p>{t('workbench.dsxUi.confirmBody')}</p>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t">
              <button
                onClick={() => setConfirming(false)}
                className="px-3 py-1 rounded border text-sm"
                data-testid="dsx-ui-confirm-cancel"
              >
                {t('workbench.dsxUi.confirmCancel')}
              </button>
              <button
                onClick={() => { setConfirming(false); setOpen(true) }}
                className="px-3 py-1 rounded text-white text-sm bg-amber-600 hover:bg-amber-700"
                data-testid="dsx-ui-confirm-proceed"
              >
                {t('workbench.dsxUi.confirmProceed')}
              </button>
            </div>
          </div>
        </div>
      )}

      {open && url && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="bg-white rounded-xl shadow-2xl w-full h-full max-w-6xl max-h-[92vh] flex flex-col" data-testid="dsx-ui-modal">
            <div className="flex items-center justify-between px-4 py-2 border-b shrink-0">
              <h3 className="font-medium text-sm text-slate-700">{t('workbench.dsxUi.modalTitle')}</h3>
              <button
                onClick={() => setOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none"
                aria-label={t('workbench.dsxUi.closeAria')}
                data-testid="dsx-ui-modal-close"
              >
                ✕
              </button>
            </div>
            {/* sandbox：只給 WebRTC/signaling/storage 必要的 allow-scripts＋
                allow-same-origin，刻意不給 allow-top-navigation／allow-popups／
                allow-modals／allow-downloads／allow-forms——沒有 sandbox 時被嵌入頁面
                預設能整頁導航走，未存檔的工時表編輯內容會消失。這兩者同時給不構成常見的
                sandbox 自我逃脫風險（那只在被嵌入內容與父頁同源時成立，DSX 不是同源）。
                allow：沒有這個屬性跨來源 iframe 不會繼承 autoplay/fullscreen 的
                permissions policy，WebRTC 串流可能因此播不出來（黑畫面，跟「被搶走
                觀看者名額」長得一樣，使用者無從分辨）。
                ⚠️ 這裡沒辦法連到真的 DSX 主機驗證串流播放/滑鼠操作不受影響，需要人工
                對真實頁面驗證；若 3D 操作需要 pointer lock，可能還要加 allow-pointer-lock。 */}
            <iframe
              src={url}
              className="flex-1 w-full border-0"
              title={t('workbench.dsxUi.modalTitle')}
              data-testid="dsx-ui-iframe"
              sandbox="allow-scripts allow-same-origin"
              allow="autoplay; fullscreen"
              referrerPolicy="no-referrer"
            />
          </div>
        </div>
      )}
    </>
  )
}
