import { useState, type ReactNode } from 'react'

/**
 * 破壞性版本操作的二次確認。
 *
 * 風險梯度：`requireText` 用於**不可逆且無 UI 可救**的操作（retire —— 後端無
 * unretire、無 DELETE），強制使用者手打版本 code；一般高衝擊操作（activate）
 * 只需按鈕確認。
 */
export function ConfirmDialog({ title, body, confirmLabel, tone = 'warn', requireText, busy, error, blockConfirm, blockReason, onCancel, onConfirm }: {
  title: string
  body: ReactNode
  confirmLabel: string
  tone?: 'warn' | 'danger'
  /** 給定時：使用者必須輸入完全相同的字串才能按下確認。 */
  requireText?: string
  busy?: boolean
  error?: string | null
  /**
   * 外部條件不允許確認（例如版本差異尚未取得）。
   * 差異載入中／失敗時**不得**讓確認鈕可按而假裝沒有差異（守則 §7 第 8 條）。
   */
  blockConfirm?: boolean
  blockReason?: string
  onCancel: () => void
  onConfirm: () => void
}) {
  const [typed, setTyped] = useState('')
  const blocked = (requireText !== undefined && typed !== requireText) || !!blockConfirm

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md" data-testid="dict-confirm-dialog">
        <div className="px-4 py-3 border-b font-medium">{title}</div>
        <div className="px-4 py-4 space-y-2 text-sm">
          {body}
          {requireText !== undefined && (
            <div className="pt-1">
              <label htmlFor="confirm-code" className="block text-xs text-slate-600 mb-1">
                請輸入版本代碼 <span className="font-mono text-slate-800">{requireText}</span> 以確認：
              </label>
              <input
                id="confirm-code" autoComplete="off" disabled={busy}
                className="w-full border rounded px-2 py-1 font-mono text-sm"
                value={typed} onChange={e => setTyped(e.target.value)}
              />
            </div>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <div className="flex justify-end items-center gap-2 px-4 py-3 border-t">
          {blockConfirm && blockReason && (
            <span className="text-xs text-slate-500 mr-auto" data-testid="confirm-blocked-reason">{blockReason}</span>
          )}
          <button onClick={onCancel} disabled={busy} className="px-3 py-1 rounded border text-sm">取消</button>
          <button
            onClick={onConfirm} disabled={busy || blocked}
            className={`px-3 py-1 rounded text-white text-sm disabled:opacity-40 disabled:cursor-not-allowed ${tone === 'danger' ? 'bg-red-600' : 'bg-amber-600'}`}
          >
            {busy ? '處理中…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
