import { useRef, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { OptionEditor } from './OptionEditor'
import { VersionList } from './VersionList'
import { useRuleSetVersions, useVersionMutations } from './api'

/**
 * MOST 字典（ADR-023 §3.1；資料層稱 rule-set，兩者同物）。
 *
 * 單一入口的兩層結構（v3 心智模型）：
 * L1 版本清單 → 點進版本 → L2 七參數分頁編輯該版所有字典設定。
 */

type CloneAsk = {
  code: string
  resolve: (target: string | null) => void
}

export function DictionaryPage() {
  const { t } = useTranslation()
  const [openCode, setOpenCode] = useState<string | null>(null)
  const [ask, setAsk] = useState<CloneAsk | null>(null)
  /** clone 成功後的「已建立」階段：**不自動切換版本**，由使用者決定何時前往。 */
  const [created, setCreated] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const { data: versions = [] } = useRuleSetVersions()
  const { cloneDraft } = useVersionMutations()
  const askRef = useRef<CloneAsk | null>(null)

  /**
   * clone-on-write（ADR-023 §3.3 規則 2）：
   * 在 published/active 版按任何編輯動作 → 確認後自動建草稿。
   * 使用者不該撞到 409。
   */
  const requestEdit = (code: string) => (): Promise<string | null> => {
    const v = versions.find(x => x.code === code)
    // draft 且非認證匯入 → 可直接寫入
    if (v && v.status === 'draft' && v.provenance !== 'certified_import') return Promise.resolve(code)
    return new Promise<string | null>(resolve => {
      const entry = { code, resolve }
      askRef.current = entry
      setAsk(entry)
    })
  }

  /** 一律以「不繼續本次寫入」收尾——草稿是空白畫布，本次編輯內容不會被帶過去。 */
  const settle = () => {
    askRef.current?.resolve(null)
    askRef.current = null
  }

  const cancel = () => {
    settle()
    setAsk(null)
    setErr(null)
  }

  const confirmClone = async () => {
    if (!ask) return
    setBusy(true); setErr(null)
    try {
      const draft = await cloneDraft.mutateAsync(ask.code)
      // 先讓本次寫入停止，再進入「已建立」階段。
      // **不呼叫 setOpenCode** —— OptionEditor 帶 key={openCode}，切換會 remount 整棵子樹，
      // 使用者尚未儲存的編輯（最嚴重是 BandEditor 的整組帶界）會靜默消失。
      settle()
      setCreated(draft.code)
      setAsk(null)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const askVersion = ask ? versions.find(v => v.code === ask.code) : undefined
  // 是否為認證版看 provenance（不靠 status 間接推論）
  const isCertified = askVersion?.provenance === 'certified_import'

  return (
    <div>
      {openCode === null ? (
        <VersionList onOpen={setOpenCode} />
      ) : (
        <OptionEditor
          key={openCode}
          code={openCode}
          onBack={() => setOpenCode(null)}
          onRequestEdit={requestEdit(openCode)}
        />
      )}

      {/* 階段一：確認建立草稿 */}
      {ask && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md" data-testid="dict-clone-dialog">
            <div className="px-4 py-3 border-b font-medium">{t('dictionary.clone.title')}</div>
            <div className="px-4 py-4 space-y-2 text-sm">
              <p>
                <Trans
                  i18nKey="dictionary.clone.ask"
                  values={{ kind: isCertified ? t('dictionary.clone.kindCertified') : t('dictionary.clone.kindPublished') }}
                  components={{ b: <b /> }}
                />
              </p>
              {isCertified && (
                <p className="text-xs text-violet-700">
                  {t('dictionary.clone.certifiedNote')}
                </p>
              )}
              <p className="text-xs text-amber-700">
                <Trans i18nKey="dictionary.clone.warn" components={{ b: <b /> }} />
              </p>
              <p className="text-xs text-slate-500">{t('dictionary.clone.autoName')}</p>
              {err && <p className="text-sm text-red-600">{err}</p>}
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t">
              <button onClick={cancel} disabled={busy} className="px-3 py-1 rounded border text-sm">{t('dictionary.clone.cancel')}</button>
              <button onClick={() => void confirmClone()} disabled={busy} className="px-3 py-1 rounded bg-sky-600 text-white text-sm disabled:opacity-50">
                {busy ? t('dictionary.clone.creating') : t('dictionary.clone.create')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 階段二：已建立 —— 明講「未套用」，由使用者按鈕決定是否前往（不自動跳轉） */}
      {created && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md" data-testid="dict-clone-created">
            <div className="px-4 py-3 border-b font-medium">{t('dictionary.clone.createdTitle')}</div>
            <div className="px-4 py-4 space-y-2 text-sm">
              <p>
                <Trans
                  i18nKey="dictionary.clone.createdBody"
                  values={{ code: created }}
                  components={{ code: <span className="font-mono text-xs" /> }}
                />
              </p>
              <p className="text-amber-800">
                <Trans i18nKey="dictionary.clone.createdWarn" components={{ b: <b /> }} />
              </p>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t">
              <button onClick={() => setCreated(null)} className="px-3 py-1 rounded border text-sm">{t('dictionary.clone.stay')}</button>
              <button
                onClick={() => { setOpenCode(created); setCreated(null) }}
                className="px-3 py-1 rounded bg-sky-600 text-white text-sm"
              >
                {t('dictionary.clone.goto')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
