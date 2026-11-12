import React, { Suspense, lazy } from 'react';
import { PlatformProvider, usePlatform } from '@/context/PlatformContext';
import { AppShell } from '@/components/layout/AppShell';
import { ErrorBoundary } from '@/components/layout/ErrorBoundary';

const OverviewPage = lazy(() => import('@/pages/overview/OverviewPage').then((m) => ({ default: m.OverviewPage })));
const ValuationPage = lazy(() => import('@/pages/valuation/ValuationPage').then((m) => ({ default: m.ValuationPage })));
const SpatialPage = lazy(() => import('@/pages/spatial/SpatialPage').then((m) => ({ default: m.SpatialPage })));
const MarketPage = lazy(() => import('@/pages/market/MarketPage').then((m) => ({ default: m.MarketPage })));
const ComparablesPage = lazy(() => import('@/pages/comparables/ComparablesPage').then((m) => ({ default: m.ComparablesPage })));
const RentalPage = lazy(() => import('@/pages/rental/RentalPage').then((m) => ({ default: m.RentalPage })));
const PortfolioPage = lazy(() => import('@/pages/portfolio/PortfolioPage').then((m) => ({ default: m.PortfolioPage })));
const ReportsPage = lazy(() => import('@/pages/reports/ReportsPage').then((m) => ({ default: m.ReportsPage })));
const CoveragePage = lazy(() => import('@/pages/coverage/CoveragePage').then((m) => ({ default: m.CoveragePage })));
const AdminPage = lazy(() => import('@/pages/admin/AdminPage').then((m) => ({ default: m.AdminPage })));

function ActiveWorkspace() {
  const { route } = usePlatform();

  switch (route) {
    case 'overview':
      return <OverviewPage />;
    case 'valuation':
      return <ValuationPage />;
    case 'spatial':
      return <SpatialPage />;
    case 'market':
      return <MarketPage />;
    case 'comparables':
      return <ComparablesPage />;
    case 'rental':
      return <RentalPage />;
    case 'portfolio':
      return <PortfolioPage />;
    case 'reports':
      return <ReportsPage />;
    case 'coverage':
      return <CoveragePage />;
    case 'admin':
      return <AdminPage />;
    default:
      return <OverviewPage />;
  }
}

function AppRouter() {
  const { route } = usePlatform();

  const content = (
    <ErrorBoundary fallbackTitle="Workspace Render Recovery">
      <Suspense
        fallback={
          <div className="min-h-[60vh] flex items-center justify-center font-mono text-xs text-[var(--text-secondary)]">
            LOADING ARCHITECTURAL MODULE...
          </div>
        }
      >
        <ActiveWorkspace />
      </Suspense>
    </ErrorBoundary>
  );

  if (route === 'overview') {
    return content;
  }

  return <AppShell>{content}</AppShell>;
}

export function App() {
  return (
    <PlatformProvider>
      <AppRouter />
    </PlatformProvider>
  );
}

export default App;
