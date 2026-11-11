import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useUpdateMyLocale } from '../../shared/auth/useMe'
import { LOCALE_STORAGE_KEY, SUPPORTED_LOCALES, isSupportedLocale, type SupportedLocale } from '../../shared/i18n/i18n'

// 失敗回饋用的輕量 toast——同 `ActionModuleWorkspace.tsx`／`WiWorkbench.tsx` 既有的
// local toast pattern（元件內自帶 state + 定時消失，fixed 定位），刻意不新增共用的
// toast 機制／context（複審要求：用現有 UI 的元件，不新增機制）。
interface ToastState { msg: string }

function writeCachedLocale(locale: SupportedLocale) {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    // localStorage 不可用：忽略，下次首屏會回退預設再由 /me 校正
  }
}

/**
 * 語言切換 UI（ADR-032 D3.4）：AppLayout 標頭右側，使用者資訊左邊。
 *
 * 語言來源是使用者個人設定（D3.1，非站別、非瀏覽器偵測），所以切換要立即
 * 反映在畫面上（i18n.changeLanguage）＋寫回 localStorage（首屏快取，D3.2）
 * ＋送 PATCH /me/locale 讓伺服器成為下次登入的權威值。三件事的順序刻意是
 * 「先切畫面，再送後端」：翻譯只影響顯示（I3），使用者不需要等網路來回
 * 才看到語言切換生效。
 *
 * PATCH 失敗時必須回滾＋出聲（複審 2026-08-18 實測到的無聲失效模式）：
 * 若只切畫面不管後端結果，PATCH 500 時使用者會停留在「畫面已切換、
 * localStorage 已寫入、但伺服器仍是舊值」的分裂狀態且**沒有任何提示**；
 * 下次開頁 `/me` 回舊值，`useLocaleSync` 會把畫面與 localStorage 都悄悄改回去，
 * 使用者完全看不到這中間發生過什麼。回滾（畫面＋localStorage 都復原成
 * `previous`）讓這次失敗當下就可見，也讓下次開頁不會出現「悄悄改回去」的落差。
 */
export function LocaleSwitcher() {
  const { i18n, t } = useTranslation()
  const updateLocale = useUpdateMyLocale()
  const current = isSupportedLocale(i18n.language) ? i18n.language : 'zh-TW'
  const [toast, setToast] = useState<ToastState | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showError = (msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ msg })
    toastTimer.current = setTimeout(() => setToast(null), 5000)
  }

  const handlePick = (locale: SupportedLocale) => {
    if (locale === current) return
    const previous = current
    void i18n.changeLanguage(locale)
    writeCachedLocale(locale)
    updateLocale.mutate(locale, {
      onError: (err) => {
        void i18n.changeLanguage(previous)
        writeCachedLocale(previous)
        showError(t('locale.updateFailed', { message: (err as Error).message }))
      },
    })
  }

  return (
    <>
      <div
        role="group"
        aria-label={t('locale.switcherAriaLabel')}
        data-testid="locale-switcher"
        className="flex items-center rounded border border-white/30 overflow-hidden text-xs"
      >
        {SUPPORTED_LOCALES.map(locale => (
          <button
            key={locale}
            type="button"
            aria-pressed={current === locale}
            onClick={() => handlePick(locale)}
            className={`px-2 py-1 transition-colors ${
              current === locale ? 'bg-white/20 text-white' : 'text-white/60 hover:bg-white/10'
            }`}
          >
            {t(`locale.${locale === 'zh-TW' ? 'zhTW' : 'en'}`)}
          </button>
        ))}
      </div>
      {toast && (
        <div
          role="alert"
          data-testid="locale-switcher-error"
          className="fixed bottom-6 right-6 z-50 px-4 py-2 rounded shadow-lg text-white text-sm bg-red-600"
        >
          {toast.msg}
        </div>
      )}
    </>
  )
}
