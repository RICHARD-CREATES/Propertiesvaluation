import React from 'react';
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react';

export function Panel({
  children,
  className = '',
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <div id={id} className={`panel-surface ${className}`}>
      {children}
    </div>
  );
}

export function MetricCell({
  label,
  value,
  subtext,
  accent,
}: {
  label: string;
  value: string | number;
  subtext?: string;
  accent?: 'copper' | 'green' | 'amber' | 'rose' | 'default';
}) {
  const colorMap: Record<string, string> = {
    copper: 'var(--accent-copper)',
    green: '#22c55e',
    amber: '#f59e0b',
    rose: '#f43f5e',
    default: 'var(--text-primary)',
  };
  return (
    <div className="panel-elevated p-3.5 min-w-0">
      <div className="tech-label truncate">{label}</div>
      <div
        className="mt-1.5 font-mono text-base sm:text-lg font-semibold tabular-nums truncate"
        style={{ color: colorMap[accent || 'default'] }}
      >
        {value}
      </div>
      {subtext && <div className="mt-1 text-[11px] text-[var(--text-muted)] truncate">{subtext}</div>}
    </div>
  );
}

export function StatusTag({
  tone = 'neutral',
  children,
  id,
}: {
  tone?: 'verified' | 'preliminary' | 'insufficient' | 'danger' | 'neutral';
  children: React.ReactNode;
  id?: string;
}) {
  const styles: Record<string, string> = {
    verified: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400',
    preliminary: 'border-amber-500/40 bg-amber-500/10 text-amber-400',
    insufficient: 'border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]',
    danger: 'border-rose-500/40 bg-rose-500/10 text-rose-400',
    neutral: 'border-[var(--border-hairline)] bg-[var(--bg-elevated)] text-[var(--text-secondary)]',
  };
  return (
    <span
      id={id}
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 border text-[10px] font-mono uppercase tracking-wider rounded-[2px] ${styles[tone]}`}
    >
      {children}
    </span>
  );
}

export function HonestNotice({
  title,
  message,
  tone = 'info',
}: {
  title: string;
  message: string;
  tone?: 'info' | 'warning' | 'success';
}) {
  const Icon = tone === 'warning' ? AlertTriangle : tone === 'success' ? CheckCircle2 : Info;
  const accent = tone === 'warning' ? 'text-amber-400' : tone === 'success' ? 'text-emerald-400' : 'text-[var(--accent-copper)]';
  return (
    <div className="panel-elevated p-3.5 flex items-start gap-2.5 text-xs">
      <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${accent}`} />
      <div className="min-w-0">
        <div className="font-semibold text-[var(--text-primary)]">{title}</div>
        <div className="text-[var(--text-secondary)] mt-0.5 leading-relaxed">{message}</div>
      </div>
    </div>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  subtitle,
  right,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3 pb-4 border-b border-[var(--border-hairline)]">
      <div className="min-w-0">
        <div className="tech-label" style={{ color: 'var(--accent-copper)' }}>
          {eyebrow}
        </div>
        <h2 className="font-serif text-2xl sm:text-3xl tracking-tight mt-0.5">{title}</h2>
        {subtitle && <p className="text-xs text-[var(--text-secondary)] mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}
