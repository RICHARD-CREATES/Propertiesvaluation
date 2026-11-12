import React, { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '@/lib/api';
import { usePlatform } from '@/context/PlatformContext';
import { HonestNotice, MetricCell, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';

export function MarketPage() {
  const { config } = usePlatform();
  const [eda, setEda] = useState<any>(null);
  const [seasonality, setSeasonality] = useState<any>(null);
  const [microMarkets, setMicroMarkets] = useState<any>(null);
  const [shapType, setShapType] = useState('apartment');
  const [shapData, setShapData] = useState<any>(null);

  const loadAnalytics = async () => {
    try {
      const [e, s, m] = await Promise.all([
        api.getAnalyticsEda(),
        api.getAnalyticsSeasonality(),
        api.getAnalyticsMicroMarkets(),
      ]);
      setEda(e);
      setSeasonality(s);
      setMicroMarkets(m);
    } catch {}
  };

  const runShap = async (ptype = shapType) => {
    try {
      const d = await api.getAnalyticsExplain(ptype);
      setShapData(d);
    } catch {}
  };

  useEffect(() => {
    loadAnalytics();
    runShap('apartment');
  }, []);

  const shapChartRows = (shapData?.feature_attributions || []).slice(0, 8).map((a: any) => ({
    feature: String(a.feature).replace(/_/g, ' '),
    pctImpact: Number(a.pct_impact_on_price || 0),
  }));

  const pps = eda?.overall_distributions?.price_per_sqft_inr;

  return (
    <div id="workspace-analytics" className="space-y-6">
      <SectionHeader
        eyebrow="Workspace 04 · Market Explorer & TreeSHAP"
        title="Market Distribution, Seasonality & Feature Attribution"
        subtitle="Read-only verified analytics adhering to strict sample-size gates — insufficient local history suppresses misleading trend charts."
        right={
          <button
            type="button"
            onClick={loadAnalytics}
            className="arch-btn px-3.5 py-1.5 font-mono text-xs border border-[var(--border-strong)] bg-[var(--bg-surface)]"
          >
            Refresh Analytics
          </button>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <MetricCell label="Verified EDA Sample" value={eda?.valid_analyzed_records ?? 0} />
        <MetricCell label="Median PPSF" value={pps ? `INR ${pps.median?.toLocaleString()}` : 'INSUFFICIENT (<5)'} />
        <MetricCell label="Seasonality History Gate" value={seasonality?.status || 'CHECKING'} accent="amber" />
        <MetricCell label="Micro-Markets Tracked" value={microMarkets?.cohorts?.length ?? 0} />
      </div>

      {(!eda || (eda.valid_analyzed_records || 0) < 5) && (
        <HonestNotice
          tone="warning"
          title="Insufficient Verified Transaction History for Distribution Charts"
          message={`Current verified ground-truth count is ${eda?.valid_analyzed_records ?? 0}. Seasonality status: ${seasonality?.status || 'INSUFFICIENT_SEASONALITY_HISTORY'}. Charts for price-per-sqft timelines remain intentionally gated until verified sales arrive.`}
        />
      )}

      {/* Live Production Model TreeSHAP Interactive Chart */}
      <Panel className="p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[var(--border-hairline)]">
          <div>
            <span className="tech-label" style={{ color: 'var(--accent-copper)' }}>
              Live Production Model Feature Impact (TreeSHAP)
            </span>
            <h3 className="font-serif text-xl mt-0.5">Percentage Impact on Estimated Price by Feature</h3>
          </div>
          <div className="flex items-center gap-2">
            <select
              id="an-shap-type"
              value={shapType}
              onChange={(e) => {
                setShapType(e.target.value);
                runShap(e.target.value);
              }}
              className="arch-input text-xs w-52"
            >
              {(config?.shap_property_types || [{ value: 'apartment', label: 'Apartment (XGBoost)' }]).map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => runShap(shapType)}
              className="arch-btn px-3 py-1.5 font-mono text-xs font-semibold"
              style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
            >
              Explain
            </button>
          </div>
        </div>

        {shapData?.status === 'OK' ? (
          <>
            <div className="flex flex-wrap items-center gap-3 text-xs font-mono">
              <StatusTag tone="verified">ADDITIVITY VERIFIED: {String(shapData.additivity_verified).toUpperCase()}</StatusTag>
              <span>Predicted Value: INR {Math.round(shapData.predicted_value_inr || 0).toLocaleString()}</span>
              <span className="text-[var(--text-muted)]">Source: Champion Model Artifact · Sample N=1 Subject</span>
            </div>
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shapChartRows} layout="vertical" margin={{ left: 110, right: 20, top: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                  <XAxis type="number" unit="%" tick={{ fill: '#9ba3ae', fontSize: 11 }} />
                  <YAxis type="category" dataKey="feature" width={120} tick={{ fill: '#eceee9', fontSize: 11 }} />
                  <Tooltip
                    formatter={(val: any) => [`${val}%`, 'Price Impact']}
                    contentStyle={{ backgroundColor: '#111419', border: '1px solid rgba(255,255,255,0.16)', fontSize: 12 }}
                  />
                  <Bar dataKey="pctImpact" fill="#c86d3b" radius={[0, 2, 2, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        ) : (
          <HonestNotice
            tone="info"
            title={shapData?.status || 'TreeSHAP Status'}
            message={shapData?.message || 'Select a trained property category to inspect TreeSHAP feature attributions.'}
          />
        )}
      </Panel>
    </div>
  );
}
