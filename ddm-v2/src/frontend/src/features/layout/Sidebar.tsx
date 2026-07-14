import { useState } from 'react'
import type { Me } from '../../shared/auth/useMe'
import { canEdit, isAdmin } from '../../shared/auth/useMe'
import type { NavItem } from './sidebar.types'

// ─── Nav item definitions (ADR-021 target IA §側欄, fixed order: 7 + 2 admin) ─

const PRIMARY_NAV: NavItem[] = [
  { id: 'dashboard',    label: '儀表板',            shortLabel: '表' },
  { id: 'workbench-v3', label: 'MOST 工作台',        shortLabel: 'M' },
  { id: 'wi-project',   label: 'WI 專案建立',        shortLabel: 'W' },
  { id: 'level',        label: 'Level System',       shortLabel: 'L' },
  { id: 'case',         label: '分析案件',            shortLabel: '案' },
  { id: 'dictionaries', label: '字典管理',            shortLabel: '典', minRole: 'analyst' },
  { id: 'users',        label: '使用者管理',          shortLabel: '人', minRole: 'admin' },
  { id: 'ruleset',      label: 'Rule-set',            shortLabel: 'R', minRole: 'admin' },
]

/** Legacy v2 tabs (L-04: SOP retired; kept as empty array for future use). */
const SECONDARY_NAV: NavItem[] = []

const SIDEBAR_BG = '#304156'

// ─── Inner nav button ─────────────────────────────────────────────────────────

interface NavButtonProps {
  item: NavItem
  active: boolean
  collapsed: boolean
  onClick: () => void
}

function NavButton({ item, active, collapsed, onClick }: NavButtonProps) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      style={{
        backgroundColor: active ? 'rgba(255,255,255,0.15)' : undefined,
        color: active ? '#ffffff' : 'rgba(255,255,255,0.7)',
      }}
      className={`w-full flex items-center py-2.5 text-sm hover:bg-white/10 transition-colors ${
        collapsed ? 'justify-center px-0' : 'px-3'
      }`}
    >
      {/* Short label — always rendered, centered when collapsed */}
      <span
        className="flex-shrink-0 font-medium"
        style={{ width: collapsed ? '100%' : '1.5rem', textAlign: 'center' }}
      >
        {item.shortLabel}
      </span>

      {/* Full label — only shown when expanded (spec §1.2) */}
      {!collapsed && (
        <span className="ml-2 whitespace-nowrap overflow-hidden text-ellipsis flex-1 text-left">
          {item.label}
        </span>
      )}
    </button>
  )
}

// ─── Sidebar nav list ─────────────────────────────────────────────────────────

interface NavListProps {
  items: NavItem[]
  activeTab: string
  onTabChange: (id: string) => void
  collapsed: boolean
  canSeeItem: (item: NavItem) => boolean
}

function NavList({ items, activeTab, onTabChange, collapsed, canSeeItem }: NavListProps) {
  return (
    <>
      {items.filter(canSeeItem).map(item => (
        <NavButton
          key={item.id}
          item={item}
          active={activeTab === item.id}
          collapsed={collapsed}
          onClick={() => onTabChange(item.id)}
        />
      ))}
    </>
  )
}

// ─── Sidebar public interface ─────────────────────────────────────────────────

export interface SidebarProps {
  activeTab: string
  onTabChange: (id: string) => void
  me?: Me
  /** Controls mobile slide-in (managed by AppLayout, toggled by header hamburger) */
  mobileOpen: boolean
  onMobileClose: () => void
}

export function Sidebar({ activeTab, onTabChange, me, mobileOpen, onMobileClose }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)

  const canSeeItem = (item: NavItem): boolean => {
    if (!item.minRole) return true
    if (item.minRole === 'admin') return isAdmin(me)
    if (item.minRole === 'analyst') return canEdit(me)
    return true
  }

  /** Tab change handler for mobile: also closes the slide-in panel */
  const handleMobileTabChange = (id: string) => {
    onTabChange(id)
    onMobileClose()
  }

  // Shared nav structure rendered inside both desktop and mobile sidebars
  const renderNav = (isCollapsed: boolean, onTab: (id: string) => void) => (
    <nav className="flex-1 overflow-y-auto py-2">
      <NavList
        items={PRIMARY_NAV}
        activeTab={activeTab}
        onTabChange={onTab}
        collapsed={isCollapsed}
        canSeeItem={canSeeItem}
      />
    </nav>
  )

  return (
    <>
      {/* ── Mobile backdrop overlay ── */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={onMobileClose}
          aria-hidden="true"
        />
      )}

      {/* ── Desktop sidebar (in flex flow, not fixed) ── */}
      {/* hidden on mobile; visible as flex column on md+ */}
      <div
        className="hidden md:flex flex-col flex-shrink-0 overflow-hidden"
        style={{
          width: collapsed ? '56px' : '200px',
          backgroundColor: SIDEBAR_BG,
          transition: 'width 0.2s ease',
        }}
      >
        {/* Toggle button — top of sidebar (spec: chevron icon) */}
        <button
          onClick={() => setCollapsed(c => !c)}
          aria-label={collapsed ? '展開側欄' : '折疊側欄'}
          style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.5)' }}
          className="flex-shrink-0 flex items-center justify-center h-9 hover:bg-white/5 transition-colors text-sm font-mono"
        >
          {collapsed ? '»' : '«'}
        </button>

        {renderNav(collapsed, onTabChange)}
      </div>

      {/* ── Mobile sidebar (fixed, slides in from left) ── */}
      {/* visible only on mobile; positioned below the 50px header */}
      <div
        className="fixed left-0 bottom-0 flex flex-col overflow-hidden z-50 md:hidden"
        style={{
          top: '50px',
          width: mobileOpen ? '200px' : '0px',
          backgroundColor: SIDEBAR_BG,
          transition: 'width 0.2s ease',
        }}
      >
        {renderNav(false, handleMobileTabChange)}
      </div>
    </>
  )
}
