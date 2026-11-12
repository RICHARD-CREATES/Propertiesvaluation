"""
Downloadable Property Valuation Report Generator (HTML & JSON)
==============================================================
Milestone 8 — Phases 7 & 8
Builds self-contained printable/downloadable HTML and structured JSON valuation reports
explicitly separating AI model estimates from independently verified market deeds.
"""
from __future__ import annotations

from datetime import datetime
import html
from typing import Any, Dict


def _fmt_inr(val: Any) -> str:
    if val is None:
        return "N/A"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "N/A"
    if abs(n) >= 1e7:
        return f"Rs. {n / 1e7:.2f} Cr (Rs. {n:,.0f})"
    if abs(n) >= 1e5:
        return f"Rs. {n / 1e5:.2f} L (Rs. {n:,.0f})"
    return f"Rs. {n:,.0f}"


def build_json_report_payload(val_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "report_id": f"RPT-{val_id}",
        "valuation_id": val_id,
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "disclaimer": (
            "Model Valuation Estimate — NOT a government-registered appraisal or binding market transaction. "
            "Verify against locally registered SRO Sale Deeds before financial underwriting."
        ),
        "valuation": record.get("valuation", {}),
        "evidence_and_uncertainty": record.get("evidence_and_uncertainty", {}),
        "income_approach_and_reconciliation": record.get("income_approach_and_reconciliation", {}),
        "explainability": record.get("explainability", {}),
        "location_summary": record.get("location_summary", {}),
        "sources_status": record.get("sources_status", {}),
    }


def render_printable_html_report(val_id: str, record: Dict[str, Any]) -> str:
    val = record.get("valuation", {})
    eu = record.get("evidence_and_uncertainty", {})
    evq = eu.get("evidence_quality", {})
    cpi = eu.get("calibrated_prediction_interval", {})
    ood = eu.get("ood_assessment", {})
    inc = record.get("income_approach_and_reconciliation", {})
    rec = inc.get("three_way_reconciliation", {})
    loc = record.get("location_summary", {})
    exp = record.get("explainability", {})

    top_drivers = exp.get("top_positive_drivers", [])[:4] + exp.get("top_negative_drivers", [])[:3]
    driver_rows = "".join(
        f"<tr><td>{html.escape(str(d.get('feature', '')))}</td>"
        f"<td>{html.escape(str(d.get('shap_impact_inr', d.get('pct_impact', ''))))}</td></tr>"
        for d in top_drivers
    ) or "<tr><td colspan='2'>No driver breakdown available.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Valuation Dossier - {html.escape(val_id)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #0f172a; max-width: 900px; margin: 24px auto; padding: 0 16px; line-height: 1.45; }}
    .banner {{ background: #fef3c7; border-left: 4px solid #d97706; padding: 10px 14px; font-size: 13px; margin-bottom: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 18px; }}
    .card {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px 14px; }}
    .label {{ font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: bold; }}
    .val {{ font-size: 18px; font-weight: bold; color: #0f172a; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 7px 10px; text-align: left; }}
    th {{ background: #f8fafc; }}
    @media print {{ .no-print {{ display: none; }} }}
  </style>
</head>
<body>
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <h1 style="margin:0;">AI Property Valuation &amp; Evidence Dossier</h1>
      <p style="margin:4px 0;color:#475569;font-size:13px;">Valuation ID: <strong>{html.escape(val_id)}</strong> &bull; Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
    </div>
    <button class="no-print" onclick="window.print()" style="padding:8px 14px;background:#0284c7;color:#fff;border:none;border-radius:6px;cursor:pointer;">Print / Save PDF</button>
  </div>

  <div class="banner">
    <strong>Model Estimate vs Verified Market Transactions:</strong> Figures below represent an AI &amp; financial-model valuation estimate, NOT a registered Sub-Registrar Sale Deed or government benchmark valuation.
  </div>

  <div class="grid">
    <div class="card">
      <div class="label">Estimated Fair Value (Model Estimate)</div>
      <div class="val">{html.escape(_fmt_inr(val.get('estimated_value_inr') or val.get('fair_market_value')))}</div>
      <div style="font-size:12px;color:#475569;">Rate/sqft: {html.escape(_fmt_inr(val.get('price_per_sqft_inr')))}</div>
    </div>
    <div class="card">
      <div class="label">Evidence Confidence &amp; Calibration</div>
      <div class="val">{html.escape(str(evq.get('confidence_tier', 'UNSPECIFIED')))}</div>
      <div style="font-size:12px;color:#475569;">Interval Status: {html.escape(str(cpi.get('status', 'INSUFFICIENT_EVIDENCE')))}</div>
    </div>
    <div class="card">
      <div class="label">Location Context</div>
      <div class="val">{html.escape(str(loc.get('city', 'Bhubaneswar')))} ({html.escape(str(loc.get('state', 'Odisha')))})</div>
      <div style="font-size:12px;color:#475569;">Lat/Lon: {html.escape(str(loc.get('latitude')))} , {html.escape(str(loc.get('longitude')))}</div>
    </div>
    <div class="card">
      <div class="label">Out-of-Distribution (OOD) Assessment</div>
      <div class="val">{html.escape(str(ood.get('ood_severity', 'NOT_EVALUATED')))}</div>
      <div style="font-size:12px;color:#475569;">{html.escape(str(ood.get('recommended_fallback', '')))}</div>
    </div>
  </div>

  <h3>Three-Way Valuation Reconciliation &amp; Income Analysis</h3>
  <table>
    <tr><th>Approach</th><th>Estimate</th><th>Notes</th></tr>
    <tr><td>Sales Comparison / ML Ensemble</td><td>{html.escape(_fmt_inr(rec.get('sales_comparison_value_inr')))}</td><td>Weight: {html.escape(str(rec.get('weights', {}).get('sales_comparison', 'N/A')))}</td></tr>
    <tr><td>Land + Depreciated Cost</td><td>{html.escape(_fmt_inr(rec.get('cost_approach_value_inr')))}</td><td>Weight: {html.escape(str(rec.get('weights', {}).get('cost_approach', 'N/A')))}</td></tr>
    <tr><td>Income Capitalization</td><td>{html.escape(_fmt_inr(rec.get('income_approach_value_inr')))}</td><td>Monthly Rent Est: {html.escape(_fmt_inr(inc.get('estimated_monthly_rent_inr')))}</td></tr>
  </table>

  <h3>Key Feature Drivers</h3>
  <table>
    <tr><th>Feature</th><th>Attributed Impact</th></tr>
    {driver_rows}
  </table>
</body>
</html>"""
