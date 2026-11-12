import React, { useState } from 'react';
import {
  Activity,
  BarChart3,
  Building2,
  ChevronLeft,
  ChevronRight,
  Compass,
  Database,
  FileSpreadsheet,
  FolderKanban,
  Layers,
  Menu,
  Scale,
  ShieldCheck,
  SunMedium,
  Moon,
  X,
} from 'lucide-react';
import { usePlatform } from '@/context/PlatformContext';
import { WORKSPACE_NAV } from '@/components/navigation/routes';
import type { WorkspaceRoute } from '@/types/api';

const ICON_MAP: Record<WorkspaceRoute, React.ComponentType<{ className?: string }>> = {
  overview: Building2,
  valuation: Scale,
  spatial: Compass,
  market: BarChart3,
  comparables: Layers,
  rental: Activity,
  portfolio: FolderKanban,
  reports: FileSpreadsheet,
  coverage: Database,
  admin: ShieldCheck,
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const { route, setRoute, theme, toggleTheme, location, zoneResponse, valuationResult, adminActor } = usePlatform();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const coreNav = WORKSPACE_NAV.filter((n) => n.section === 'core');
  const adminNav = WORKSPACE_NAV.filter((n) => n.section === 'admin');

  const activeLocality = valuationResult?.location_summary?.locality || zoneResponse?.city || location.displayAddress;

  const selectRoute = (id: WorkspaceRoute) => {
    setRoute(id);
    setMobileMenuOpen(false);
  };

  const renderNavList = (items: typeof WORKSPACE_NAV) =>
    items.map((item) => {
      const Icon = ICON_MAP[item.id];
      const active = route === item.id;
      return (
        <button
          key={item.id}
          id={`nav-workspace-${item.id}`}
          type="button"
          onClick={() => selectRoute(item.id)}
          title={item.label}
          className={`arch-btn w-full flex items-center gap-2.5 px-2.5 py-2 text-left text-xs border ${
            active
              ? 'border-[var(--accent-copper)] bg-[var(--bg-elevated)] text-[var(--text-primary)] font-semibold'
              : 'border-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]'
          }`}
        >
          <span className="font-mono text-[10px] w-4 text-[var(--text-muted)] shrink-0">{item.shortTag}</span>
          <Icon className={`w-3.5 h-3.5 shrink-0 ${active ? 'text-[var(--accent-copper)]' : ''}`} />
          {!collapsed && <span className="truncate">{item.label}</span>}
        </button>
      );
    });

  return (
    <div className="min-h-[100dvh] flex flex-col lg:flex-row bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Compact Collapsible Left Navigation Rail (Zero Top Overhead) */}
      <aside
        className={`hidden lg:flex flex-col shrink-0 border-r border-[var(--border-hairline)] bg-[var(--bg-surface)] sticky top-0 h-[100dvh] transition-all duration-200 ${
          collapsed ? 'w-[68px]' : 'w-[232px]'
        }`}
      >
        <div className="h-12 px-3 flex items-center justify-between border-b border-[var(--border-hairline)]">
          {!collapsed ? (
            <div className="font-serif text-lg leading-none tracking-tight">PropIntel</div>
          ) : (
            <span className="font-serif text-lg mx-auto">P</span>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            aria-label="Toggle sidebar"
            className="arch-btn w-7 h-7 flex items-center justify-center border border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]"
          >
            {collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
          </button>
        </div>

        <nav className="flex-1 p-2.5 space-y-4 overflow-y-auto" aria-label="Workspace navigation">
          <div className="space-y-1">{renderNavList(coreNav)}</div>
          <div className="space-y-1 pt-3 border-t border-[var(--border-hairline)]">{renderNavList(adminNav)}</div>
        </nav>

        <div className="p-2.5 border-t border-[var(--border-hairline)] space-y-2 text-[10px] font-mono text-[var(--text-muted)]">
          {!collapsed && (
            <div className="space-y-0.5 px-1">
              <div className="text-[var(--text-primary)] truncate">{activeLocality}</div>
              <div className="truncate">{adminActor ? `${adminActor.id}` : 'Analyst Session'}</div>
            </div>
          )}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label="Toggle Obsidian or Stone theme"
            className="arch-btn w-full px-2 py-1 border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-xs flex items-center justify-center gap-1.5 text-[var(--text-primary)]"
          >
            {theme === 'obsidian' ? <SunMedium className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
            {!collapsed && <span className="font-mono text-[11px]">{theme === 'obsidian' ? 'Stone Mode' : 'Obsidian Mode'}</span>}
          </button>
        </div>
      </aside>

      {/* Mobile Compact Menu Bar Only (< lg) */}
      <div className="lg:hidden border-b border-[var(--border-hairline)] bg-[var(--bg-surface)] px-3 py-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={() => setMobileMenuOpen((v) => !v)}
            aria-label="Toggle mobile navigation"
            className="arch-btn w-8 h-8 flex items-center justify-center border border-[var(--border-strong)] bg-[var(--bg-elevated)]"
          >
            {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
          </button>
          <span className="font-serif text-base">PropIntel</span>
        </div>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label="Toggle theme"
          className="arch-btn w-8 h-8 flex items-center justify-center border border-[var(--border-strong)] bg-[var(--bg-elevated)]"
        >
          {theme === 'obsidian' ? <SunMedium className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
        </button>
      </div>

      {mobileMenuOpen && (
        <div className="lg:hidden border-b border-[var(--border-hairline)] bg-[var(--bg-surface)] p-3 z-20">
          <div className="grid grid-cols-2 gap-1.5">{renderNavList([...coreNav, ...adminNav])}</div>
        </div>
      )}

      <main className="flex-1 min-w-0 arch-grid-bg">
        <div className="max-w-[1520px] mx-auto px-3 sm:px-6 py-5 sm:py-6">{children}</div>
      </main>
    </div>
  );
}
