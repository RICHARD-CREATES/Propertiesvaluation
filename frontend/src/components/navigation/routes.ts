import type { WorkspaceRoute } from '@/types/api';

export interface NavItem {
  id: WorkspaceRoute;
  label: string;
  section: 'core' | 'admin';
  shortTag: string;
}

export const WORKSPACE_NAV: NavItem[] = [
  { id: 'overview', label: 'Overview', section: 'core', shortTag: '01' },
  { id: 'valuation', label: 'Property Valuation', section: 'core', shortTag: '02' },
  { id: 'spatial', label: 'Spatial Intelligence', section: 'core', shortTag: '03' },
  { id: 'market', label: 'Market Explorer', section: 'core', shortTag: '04' },
  { id: 'comparables', label: 'Comparable Evidence', section: 'core', shortTag: '05' },
  { id: 'rental', label: 'Rental Intelligence', section: 'core', shortTag: '06' },
  { id: 'portfolio', label: 'Portfolio Analysis', section: 'core', shortTag: '07' },
  { id: 'reports', label: 'Reports', section: 'core', shortTag: '08' },
  { id: 'coverage', label: 'Data Coverage', section: 'core', shortTag: '09' },
  { id: 'admin', label: 'Evidence & Admin', section: 'admin', shortTag: 'AD' },
];
