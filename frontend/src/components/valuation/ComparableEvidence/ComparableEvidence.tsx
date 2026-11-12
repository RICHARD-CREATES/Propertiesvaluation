import React from 'react';
import { HonestNotice, Panel, StatusTag } from '@/components/ui/Primitives';
import type { ValuationResponse } from '@/types/api';

function verificationTone(cat: string): 'verified' | 'preliminary' | 'insufficient' {
  const c = cat.toUpperCase();
  if (c.includes('VERIFIED') || c.includes('REGISTRATION')) return 'verified';
  if (c.includes('BROKER') || c.includes('DOCUMENT')) return 'preliminary';
  return 'insufficient';
}

export function ComparableEvidence({ data }: { data: ValuationResponse }) {
  const rentalComps = data.income_approach_and_reconciliation?.rental_comparables;
  const list = rentalComps?.comparables || [];

  return (
    <Panel className="p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[var(--border-hairline)]">
        <div>
          <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
            C. Evidence &amp; Comparable Records
          </span>
          <h3 className="font-serif text-xl mt-0.5">Sourced Comparables Contributing to Estimate</h3>
        </div>
        <StatusTag tone="neutral">
          COMP CONFIDENCE: {Math.round((rentalComps?.data_confidence_score || 0) * 100)}% ({rentalComps?.data_confidence_label || 'OK'})
        </StatusTag>
      </div>

      {list.length === 0 ? (
        <HonestNotice
          tone="warning"
          title="Zero Nearby Registered Sales / Verified Lease Comparables in Local Store"
          message="No matched ground-truth deeds exist in the local SQLite transaction vault yet. Comparable-sales anchoring currently falls back to municipal circle-rate ratios and benchmark schedules."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[var(--border-hairline)] tech-label">
                <th className="py-2 pr-3">Locality</th>
                <th className="py-2 pr-3">Source Category</th>
                <th className="py-2 pr-3 text-right">Distance</th>
                <th className="py-2 pr-3 text-right">Area (sq ft)</th>
                <th className="py-2 text-right">Achieved / Indicated Rent</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-hairline)] font-mono tabular-nums">
              {list.map((c, idx) => (
                <tr key={idx}>
                  <td className="py-2.5 pr-3 font-sans font-medium">{c.locality}</td>
                  <td className="py-2.5 pr-3">
                    <StatusTag tone={verificationTone(c.data_category)}>{c.data_category.replace(/_/g, ' ')}</StatusTag>
                  </td>
                  <td className="py-2.5 pr-3 text-right">{c.distance_km} km</td>
                  <td className="py-2.5 pr-3 text-right">{c.builtup_area_sqft.toLocaleString()}</td>
                  <td className="py-2.5 text-right">INR {c.monthly_rent_inr.toLocaleString()} / mo</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
