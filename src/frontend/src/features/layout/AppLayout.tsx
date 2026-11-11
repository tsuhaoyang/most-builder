import { useState } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Sidebar } from './Sidebar'
import { LocaleSwitcher } from './LocaleSwitcher'
import type { Me } from '../../shared/auth/useMe'

interface AppLayoutProps {
  activeTab: string
  onTabChange: (id: string) => void
  me?: Me
  /** If true, the "匯入 Excel" button is shown in the header */
  canEdit?: boolean
  onImportClick?: () => void
  children: ReactNode
}

/**
 * Global shell layout (UX spec §1).
 *
 * Structure:
 *   ┌──────────────────────────────────┐
 *   │ Header (fixed 50px, #304156)      │
 *   ├─────────┬────────────────────────┤
 *   │ Sidebar │ Main content           │
 *   │ 200/56px│ #f5f7fa, 16px padding  │
 *   └─────────┴────────────────────────┘
 *
 * Color tokens: sidebar-bg #304156 / page-bg #f5f7fa (spec §1.3)
 */
export function AppLayout({
  activeTab,
  onTabChange,
  me,
  canEdit,
  onImportClick,
  children,
}: AppLayoutProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { t } = useTranslation()

  return (
    <div
      className="flex flex-col overflow-hidden"
      style={{ height: '100vh' }}
    >
      {/* ── Header (50px, sidebar-bg colour) ── */}
      <header
        className="flex-shrink-0 flex items-center justify-between px-4 text-white z-30"
        style={{ height: '50px', backgroundColor: '#304156' }}
      >
        {/* Left: hamburger (mobile only) + app title */}
        <div className="flex items-center gap-2">
          {/* Hamburger — only visible on mobile (md:hidden) */}
          <button
            className="md:hidden text-white/70 hover:text-white p-1 leading-none text-lg"
            onClick={() => setMobileOpen(o => !o)}
            aria-label={t('header.toggleSidebarAria')}
          >
            ☰
          </button>
          <h1 className="font-semibold text-sm tracking-wide m-0 leading-none">{t('header.appTitle')}</h1>
        </div>

        {/* Right: import button (if permitted) + language switcher + user info */}
        <div className="flex items-center gap-3">
          {canEdit && onImportClick && (
            <button
              onClick={onImportClick}
              className="px-2 py-1 text-xs rounded border border-white/30 text-white/80 hover:bg-white/10 transition-colors"
            >
              {t('header.importExcel')}
            </button>
          )}
          <LocaleSwitcher />
          <span className="text-xs text-white/70">
            {me?.employee_no ?? '…'}
            {me ? ` · ${me.roles.join(',') || 'viewer'}` : ''}
          </span>
        </div>
      </header>

      {/* ── Body row: sidebar + main content ── */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activeTab={activeTab}
          onTabChange={onTabChange}
          me={me}
          mobileOpen={mobileOpen}
          onMobileClose={() => setMobileOpen(false)}
        />

        {/* Main content area — page-bg #f5f7fa, 16px padding, scrollable */}
        <main
          className="flex-1 overflow-y-auto"
          style={{ backgroundColor: '#f5f7fa', padding: '16px' }}
        >
          {children}
        </main>
      </div>
    </div>
  )
}
