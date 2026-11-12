import React, { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { usePlatform } from '@/context/PlatformContext';
import { HonestNotice, MetricCell, Panel, SectionHeader, StatusTag } from '@/components/ui/Primitives';
import type { AdminQueueItem } from '@/types/api';

export function AdminPage() {
  const { adminToken, adminActor, setAdminSession, health } = usePlatform();
  const [tab, setTab] = useState<'review' | 'ingestion' | 'models' | 'health'>('review');
  const [username, setUsername] = useState('registry_verifier');
  const [password, setPassword] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [queue, setQueue] = useState<AdminQueueItem[]>([]);
  const [ingestionRuns, setIngestionRuns] = useState<any[]>([]);
  const [validationDash, setValidationDash] = useState<any>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const [bmvRef, setBmvRef] = useState('');
  const [bmvLocality, setBmvLocality] = useState('Patia');
  const [bmvRate, setBmvRate] = useState('4500');

  const loadProtectedData = async (token = adminToken) => {
    try {
      const [runs, val] = await Promise.all([api.getIngestionRuns(), api.getValidationDashboard()]);
      setIngestionRuns(runs?.runs || []);
      setValidationDash(val);
      if (token) {
        const q = await api.getAdminReviewQueue(token);
        setQueue(q.items || []);
      }
    } catch {}
  };

  useEffect(() => {
    loadProtectedData();
  }, [adminToken]);

  const handleLogin = async () => {
    setAuthError(null);
    try {
      const res = await api.adminLogin(username.trim(), password);
      setAdminSession(res.access_token, { id: res.actor_id, role: res.actor_role });
      setPassword('');
    } catch (e: any) {
      setAuthError(e?.message || 'Authentication rejected by server.');
    }
  };

  const handleTransition = async (txId: string, status: string) => {
    if (!adminToken) return;
    try {
      const res = await api.transitionVerification(adminToken, txId, status);
      setActionMsg(`Transitioned ${txId} -> ${res.verification_status}`);
      loadProtectedData(adminToken);
    } catch (e: any) {
      setActionMsg(`Blocked: ${e?.message}`);
    }
  };

  const handleSync = async () => {
    if (!adminToken) return;
    try {
      const res = await api.syncGroundTruth(adminToken);
      setActionMsg(`Synced ${res.synced_to_ground_truth} verified deeds.`);
    } catch (e: any) {
      setActionMsg(`Sync blocked: ${e?.message}`);
    }
  };

  const handleSubmitBmv = async () => {
    if (!adminToken) return;
    try {
      const res = await api.ingestGovtBmv(adminToken, {
        circular_or_query_ref: bmvRef.trim(),
        mouza: bmvLocality.trim() || 'Patia',
        benchmark_value_inr: Number(bmvRate) || 0,
        latitude: 20.3533,
        longitude: 85.8266,
      });
      setActionMsg(`BMV Ingestion Run: ${res.status} (accepted=${res.accepted}, rejected=${res.rejected})`);
      loadProtectedData(adminToken);
    } catch (e: any) {
      setActionMsg(`Failed: ${e?.message}`);
    }
  };

  return (
    <div id="workspace-admin" className="space-y-6">
      <SectionHeader
        eyebrow="Admin · Server RBAC Governance"
        title="Evidence Review, Ingestion Runs & System Telemetry"
        subtitle="Role authorization is enforced strictly by the server. Protected review transitions log atomically to the immutable verification ledger."
        right={
          <StatusTag tone={adminActor ? 'verified' : 'insufficient'}>
            {adminActor ? `${adminActor.id} (${adminActor.role})` : 'UNAUTHENTICATED'}
          </StatusTag>
        }
      />

      {/* Sub-navigation */}
      <div className="flex flex-wrap gap-2">
        {[
          { id: 'review' as const, label: 'Evidence Review' },
          { id: 'ingestion' as const, label: 'Data Ingestion & BMV' },
          { id: 'models' as const, label: 'Model Monitoring' },
          { id: 'health' as const, label: 'System Health' },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`arch-btn px-3 py-1.5 font-mono text-xs border ${
              tab === t.id
                ? 'border-[var(--accent-copper)] bg-[var(--bg-elevated)] text-[var(--accent-copper)] font-semibold'
                : 'border-[var(--border-hairline)] bg-[var(--bg-surface)] text-[var(--text-secondary)]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Staff Authentication Gate */}
      {!adminToken ? (
        <Panel className="p-5 max-w-xl space-y-3">
          <div className="tech-label">Staff Bearer Token Sign-In</div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Staff Username" className="arch-input text-xs" />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Server Password" className="arch-input text-xs" />
            <button
              type="button"
              onClick={handleLogin}
              className="arch-btn px-4 text-xs font-mono font-semibold"
              style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
            >
              Authenticate
            </button>
          </div>
          {authError && <p className="text-xs text-rose-400">{authError}</p>}
        </Panel>
      ) : (
        <Panel className="p-4 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span>
            Active Principal: <strong className="font-mono text-emerald-400">{adminActor?.id} ({adminActor?.role})</strong>
          </span>
          <div className="flex gap-2">
            <button type="button" onClick={handleSync} className="arch-btn px-3 py-1 font-mono border border-[var(--border-strong)] bg-[var(--bg-elevated)]">
              Sync Verified Deeds
            </button>
            <button
              type="button"
              onClick={() => setAdminSession(null, null)}
              className="arch-btn px-3 py-1 font-mono border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-rose-400"
            >
              Sign Out
            </button>
          </div>
        </Panel>
      )}

      {actionMsg && <HonestNotice tone="info" title="Admin Action Log" message={actionMsg} />}

      {tab === 'review' && (
        <Panel className="p-5 space-y-3">
          <div className="tech-label">Pending Evidence Queue ({queue.length})</div>
          {!adminToken ? (
            <p className="text-xs text-[var(--text-muted)]">Authenticate above to inspect review records and trigger verified transitions.</p>
          ) : queue.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)]">Zero canonical records pending verification review.</p>
          ) : (
            <div className="space-y-2">
              {queue.map((item) => (
                <div key={item.transaction_id} className="panel-elevated p-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div>
                    <div className="font-mono font-semibold">{item.transaction_id} · {item.locality || 'N/A'}</div>
                    <div className="text-[11px] text-[var(--text-secondary)]">
                      Status: {item.verification_status} · Category: {item.source_category} · Flags: {(item.review_flags || []).join(', ') || 'None'}
                    </div>
                  </div>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => handleTransition(item.transaction_id, 'DOCUMENT_VERIFIED')}
                      className="arch-btn px-2.5 py-1 font-mono text-[11px] border border-emerald-500/40 text-emerald-400"
                    >
                      Verify Doc
                    </button>
                    <button
                      type="button"
                      onClick={() => handleTransition(item.transaction_id, 'REJECTED')}
                      className="arch-btn px-2.5 py-1 font-mono text-[11px] border border-rose-500/40 text-rose-400"
                    >
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      {tab === 'ingestion' && (
        <div className="space-y-4">
          {adminToken && (
            <Panel className="p-5 space-y-3">
              <div className="tech-label">Authorized Govt BMV Circle Rate Reference Import</div>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
                <input type="text" value={bmvRef} onChange={(e) => setBmvRef(e.target.value)} placeholder="Circular Ref (IGR/KH/BMV)" className="arch-input text-xs" />
                <input type="text" value={bmvLocality} onChange={(e) => setBmvLocality(e.target.value)} placeholder="Locality / Mouza" className="arch-input text-xs" />
                <input type="number" value={bmvRate} onChange={(e) => setBmvRate(e.target.value)} placeholder="Benchmark INR" className="arch-input font-mono text-xs" />
                <button
                  type="button"
                  onClick={handleSubmitBmv}
                  className="arch-btn px-3 text-xs font-mono font-semibold"
                  style={{ backgroundColor: 'var(--accent-copper)', color: 'var(--accent-copper-ink)' }}
                >
                  Import BMV Reference
                </button>
              </div>
            </Panel>
          )}
          <Panel className="p-5 space-y-2 text-xs">
            <div className="tech-label">Recent Ingestion Runs ({ingestionRuns.length})</div>
            {ingestionRuns.length === 0 ? (
              <p className="text-[var(--text-muted)]">No ingestion batches executed yet.</p>
            ) : (
              ingestionRuns.map((r: any, idx: number) => (
                <div key={idx} className="panel-elevated p-2.5 font-mono flex justify-between">
                  <span>{r.adapter_name || r.source_reference}</span>
                  <span>{r.status} (accepted: {r.accepted_count ?? r.accepted ?? 0})</span>
                </div>
              ))
            )}
          </Panel>
        </div>
      )}

      {tab === 'models' && (
        <Panel className="p-5 space-y-3">
          <div className="tech-label">Independent Holdout Validation Telemetry</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricCell label="Validation Status" value={validationDash?.validation_status || 'UNVALIDATED'} />
            <MetricCell label="Verified Holdout Deeds" value={validationDash?.verified_sample_count ?? 0} />
            <MetricCell
              label="Reconciled MedAPE"
              value={validationDash?.overall_metrics_by_approach?.three_way_reconciliation?.medape_pct ?? 'UNVALIDATED'}
            />
            <MetricCell
              label="Models Loaded"
              value={health?.production_models_loaded?.length ?? 0}
              subtext={(health?.production_models_loaded || []).join(', ')}
            />
          </div>
          {validationDash?.limitations_note && (
            <HonestNotice tone="info" title="Validation Limitations" message={validationDash.limitations_note} />
          )}
        </Panel>
      )}

      {tab === 'health' && (
        <Panel className="p-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCell label="API Service Status" value={health?.status?.toUpperCase() || 'UNKNOWN'} accent="green" />
          <MetricCell label="Specialist AI Layers" value={health?.specialist_models_registered ?? 0} />
          <MetricCell label="SQLite Tables" value={health?.database_tables_count ?? 0} subtext={health?.database_connected ? 'Connected' : 'Disconnected'} />
          <MetricCell label="Evidence Vault" value={health?.private_evidence_vault_ready ? 'READY' : 'NOT INITIALIZED'} />
        </Panel>
      )}
    </div>
  );
}
