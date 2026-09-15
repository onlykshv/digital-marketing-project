# Validation Report — Ticket A-01: Revenue at Risk methodology

**Status:** TODO → **REVIEW**
**Priority:** CRITICAL | **Category:** Analytics
**Date:** 2026-09-09

---

## 1. Audit trail (source → notebook → output → dashboard)

| Stage | File | What happens |
|---|---|---|
| Raw score | `notebooks/06_risk_scoring.ipynb`, cell 3 | `risk_score_full = model_full.predict_proba(...)[:, 1]` — XGBoost's **raw**, uncalibrated probability output. |
| Tier label | `notebooks/06_risk_scoring.ipynb`, cells 12–13 | `risk_tier` = threshold bucket of `risk_score_full` (High ≥0.95, chosen by a precision-target heuristic, not calibration). Saved to `outputs/risk_scoring_predictions.csv`. |
| Aggregation | `notebooks/08_marketing_value_analysis.ipynb`, cell 15 | `avg_hrr_*` = `df.pivot_table(..., values="total_revenue", aggfunc="mean")`, grouped by the `risk_tier` **label**. Saved to `outputs/risk_value_matrix.csv`. No probability appears anywhere in this notebook. |
| Dashboard KPI | `dashboard/lib/data.py` (was `revenue_at_risk`) | `sum(n_High-tier-in-value-tier × avg_hrr-in-that-cell)` across value tiers — i.e. **100% of the historical revenue held by every High-tier customer**, headcount-weighted, not probability-weighted. |
| Display | `dashboard/pages/customer_value.py` | Labeled **"Revenue at Risk"** — wording that implies an expected-loss / probability-weighted figure. |

**Notebook 06 already documents this exact concern in its own §7 findings** ("the raw scores are severely miscalibrated... not safe to plug directly into `expected_revenue_at_risk = P(churn) x customer_revenue`... a natural next step, not done here per the no-retraining scope of this notebook").

## 2. Finding

The KPI is **not literally `raw_score × revenue`** (no multiplication by any score happens anywhere in the pipeline) — but it **is** built entirely from a threshold bucket of the raw, uncalibrated XGBoost score, and every dollar in it is counted at 100% weight regardless of where a customer's individual score sits within that tier (0.95–0.9986, in this dataset). Labeling that "Revenue at Risk" reads to any audience as an expected-loss figure, which it is not.

**Independent reproducibility check** — recomputed directly from the two raw per-customer files, bypassing the pre-aggregated `risk_value_matrix.csv` entirely:

```
Dashboard function (via risk_value_matrix.csv):        NT$ 34,870,119.00
Independent recomputation (predictions + value tiers):  NT$ 34,870,119.00   [22,692 High-tier customers]
Match: True

If P(churn) x revenue had been used instead:             NT$ 33,691,054.14
Difference from actual:                                  NT$ 1,179,064.86  (~3.4%)
```

This confirms both (a) the calculation is reproducible and internally consistent, and (b) it is genuinely a 100%-weighted headcount sum, not a probability-weighted one — the two would differ by ~3.4% if it were.

## 3. Decision: option (2), not option (1)

The ticket allows either implementing calibration (option 1) or renaming to a non-probabilistic metric (option 2). Option 1 was **not** implemented here because:

- It is the explicit, separately-scoped subject of ticket **A-02** ("Probability calibration") — doing it inside A-01 would duplicate that ticket's work and go beyond "work one ticket at a time" (per the tracker's own "How to Use" sheet).
- The ticket's own instruction: *"Preserve the underlying source data and model unless modification is required."* No model change is required to fix the mislabeling — only the presentation and documentation needed to change.

Per rule 6 in the tracker's "How to Use" sheet ("if a ticket reveals a deeper issue, add a new ticket rather than silently changing the methodology") — no new ticket was needed here, since A-02 already exists and already covers the calibration follow-up this finding points to.

## 4. What changed

| File | Change |
|---|---|
| `dashboard/lib/data.py` | `revenue_at_risk()` → `high_risk_historical_revenue_exposure()`, with a docstring stating the exact formula and explicitly noting it is not `P(churn) x revenue`. |
| `dashboard/pages/customer_value.py` | KPI label "Revenue at Risk" → **"High-Risk Historical Revenue Exposure"**; added a visible one-line caption directly under the KPI row explaining what the number is (and isn't); loads `risk_summary` and wires the new caveat into the page's Methodology panel. |
| `dashboard/lib/caveats.py` | Added a new methodology panel, **"'Revenue Exposure' is a headcount sum, not an expected loss"**, explaining the exact formula, that `risk_score_full` is raw/uncalibrated `predict_proba` output, that `scale_pos_weight` inflates it, and pointing to `06_risk_scoring.ipynb §7` and the calibration follow-up. |

No other file was touched.

## 5. What was NOT changed (by design)

- `src/`, `notebooks/`, `models/`, `outputs/` — **zero files touched** (verified via mtime check before and after).
- The underlying score, thresholds (0.65/0.95), and `risk_tier` assignment — unchanged.
- No new statistics were invented; every number in the new copy is read from existing files or computed the same way as before.

## 6. Validation performed

1. **Formula audit** — traced the KPI from `predict_proba` through both notebooks to the dashboard (§1 above).
2. **Independent reproducibility check** — recomputed the KPI from raw per-customer CSVs, outside the dashboard's own code path; exact match (§2 above).
3. **Syntax check** — all dashboard `.py` files parse cleanly.
4. **Streamlit `AppTest` suite** — all 5 pages run with zero exceptions after the change (including Customer 360's full gate → filter → select flow).
5. **Live server + browser check** — started the real app, navigated to Customer Value, confirmed:
   - New label and value render correctly (`HIGH-RISK HISTORICAL REVENUE EXPOSURE`, `₹91.36M`).
   - New caption is visible without opening anything.
   - New Methodology panel entry expands and renders correctly (bold/italic/inline-code all correct).
6. **Isolation check** — confirmed via `find -newermt` that only the 3 files listed in §4 were modified.

## 7. Acceptance criteria — status

| Criterion | Met? |
|---|---|
| Formula is documented | ✅ — docstring in `data.py` + methodology panel in `caveats.py` |
| Calculation is reproducible | ✅ — independent recomputation matches exactly (§2) |
| Dashboard wording matches methodology | ✅ — renamed label + inline caption + expander note |
| No raw-score × revenue metric presented as expected loss | ✅ — was never literally that formula, and is now explicitly labeled and documented as a headcount exposure total, not an expected loss |

## 8. Observation out of scope for this ticket

While verifying the rendered Methodology panel, `NT$` was seen silently rendering as `NT` in the pre-existing HRR caveat text (`_hrr_body` in `caveats.py`, written for the earlier INR-conversion work) — Streamlit's markdown appears to be interpreting the `$` characters as KaTeX math delimiters. **Not fixed here** — it lives in a function A-01 doesn't touch, and the instruction was to fix A-01 only. Worth its own ticket.
