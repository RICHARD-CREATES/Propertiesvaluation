import React from 'react';
import { HonestNotice, Panel, StatusTag } from '@/components/ui/Primitives';
import type { ValuationResponse } from '@/types/api';

export function ConfidencePanel({ data }: { data: ValuationResponse }) {
  const eu = data.evidence_and_uncertainty;
  const eq = eu.evidence_quality;
  const cal = eu.calibrated_prediction_interval;
  const ood = eu.ood_assessment;

  const tierTone =
    eq.confidence_tier === 'HIGH' ? 'verified' : eq.confidence_tier === 'MODERATE' ? 'preliminary' : 'insufficient';

  return (
    <Panel className="p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-hairline)]">
        <div>
          <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
            F. Confidence, Statistical Calibration &amp; Limitations
          </span>
          <h3 className="font-serif text-xl mt-0.5">Evidence Sufficiency &amp; Prediction Interval</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusTag id="ev-conf-tier-badge" tone={tierTone}>
            EVIDENCE: {eq.confidence_tier}
          </StatusTag>
          <StatusTag id="ev-ood-badge" tone={ood.is_ood ? 'danger' : 'verified'}>
            OOD: {ood.ood_severity}
          </StatusTag>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        <div className="panel-elevated p-4 space-y-2">
          <div className="flex justify-between items-center">
            <span className="tech-label">Composite Evidence Score</span>
            <strong className="font-mono text-sm">{eq.composite_confidence_score.toFixed(2)} / 1.00</strong>
          </div>
          <div className="space-y-1.5 pt-2 border-t border-[var(--border-hairline)]">
            {Object.entries(eq.score_components || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between font-mono text-[11px]">
                <span className="font-sans text-[var(--text-secondary)] capitalize">{k.replace(/_/g, ' ')}</span>
                <span>{Math.round(v * 100)}%</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel-elevated p-4 space-y-2">
          <div className="flex justify-between items-center">
            <span className="tech-label">Empirical Holdout Calibration</span>
            <StatusTag tone={cal.status === 'CALIBRATED_ON_INDEPENDENT_HOLDOUT' ? 'verified' : 'insufficient'}>
              {cal.status}
            </StatusTag>
          </div>
          <div className="font-mono text-sm font-semibold tabular-nums pt-1">
            {cal.lower_estimate !== null && cal.upper_estimate !== null
              ? `${cal.lower_estimate.toLocaleString()} — ${cal.upper_estimate.toLocaleString()} (±${cal.empirical_quantile_margin_pct}%)`
              : 'INSUFFICIENT_EVIDENCE (Min 10 Holdout Deeds Required)'}
          </div>
          <div className="text-[11px] text-[var(--text-secondary)]">
            Verified Holdout Samples: <strong className="font-mono">{cal.calibration_sample_count}</strong>
          </div>
          {cal.evidence_limitations?.map((lim, idx) => (
            <p key={idx} className="text-[11px] text-[var(--text-muted)]">
              • {lim}
            </p>
          ))}
        </div>
      </div>

      <HonestNotice
        tone={eq.confidence_tier === 'INSUFFICIENT_EVIDENCE' ? 'warning' : 'info'}
        title="Statistical Honesty Policy"
        message="An Evidence Quality Score reflects data completeness, proximity, and verification tier — never a calibrated probability of market-price accuracy unless independent holdout residuals satisfy sample thresholds."
      />
    </Panel>
  );
}
