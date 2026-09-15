# Validation Report — Ticket A-05: Risk threshold rationale

**Status:** TODO → **REVIEW**
**Priority:** HIGH | **Category:** Model Governance
**Date:** 2026-09-09

---

## 1. Inspection performed before changing anything

- **`06_risk_scoring.ipynb`** (the source of the thresholds) — confirmed the exact selection rule:
  High = the lowest threshold on a 0.05-step sweep where precision first reaches 55%
  (`PRECISION_TARGET_HIGH = 0.55`), falling back to the highest-precision threshold if 55% is
  never reached; Medium = the F1-maximizing threshold on the same sweep. Both are chosen targets,
  not derived from a cost model.
- **`outputs/risk_scoring_threshold_analysis.csv`** — the full precision/recall/F1/%-targeted
  sweep (19 rows, thresholds 0.05-0.95) this rule operates on. Already saved; reused, not
  regenerated.
- **`outputs/risk_scoring_summary.json`** — the realized per-tier rates the dashboard actually
  shows (High: 22,692 customers, 80.0% observed churn; Medium: 107,043, 36.6%; Low: 841,225, 3.6%).
- **`outputs/calibrated_probabilities.csv`** (from A-02) — needed to answer the ticket's specific
  question about whether calibrated probabilities require different thresholds.
- **Dashboard** — `pages/risk_intelligence.py`'s "Model performance & threshold trade-off"
  expander is the only place thresholds are explained/interacted with; `lib/caveats.py` is the
  existing methodology-note mechanism (used by A-01/A-02/A-03).

## 2. What was done

Built **`notebooks/11_threshold_rationale.ipynb`** — a new, additive notebook (no retraining,
no re-scoring, no threshold change) that:

1. **Re-derives both thresholds** from the saved sweep and asserts they match production exactly
   (0.95 and 0.65) — confirms the documented rule is in fact the rule that was used.
2. **Reports precision/recall/coverage/churn-lift** at both cutoffs, both the marginal rate *at*
   the cutoff and the realized rate *within* the resulting tier (9x lift in High, 4x in Medium
   vs. the 8.99% base rate).
3. **Sensitivity analysis**:
   - Swept the High cutoff's free parameter (the 55% precision target) across 40%-85% — found the
     result is **robust above ~50%** (precision jumps sharply from 53% at threshold 0.90 to 80% at
     0.95, so most reasonable targets land on 0.95 regardless) but **sensitive in the 40-50% band**
     (would resolve to 0.75-0.90 instead).
   - Checked F1 flatness around the Medium cutoff — F1 varies **<1%** across the entire 0.55-0.85
     threshold band even though precision and recall individually move substantially within it,
     meaning "F1-optimal" picked 0.65 from a wide near-equivalent band, not a sharp optimum. The
     real decision hiding inside that pick is a precision/recall preference.
4. **Calibrated-probability comparison** (the ticket's explicit question): applying 0.65/0.95
   directly to `calibrated_probability` would flag only 2.87% and 0.34% of customers (vs. 13.36%
   and 2.34% today) — the two numbers do not transfer, because the calibrated scale is honest
   about how rare a genuinely high churn probability is. However, mean calibrated probability
   still rises sharply and monotonically across the existing (raw-score-based) tiers (Low 3.6% →
   Medium 36.6% → High 80.1%), confirming the tiers remain valid **for their actual purpose**
   (ranking/prioritization) even though the literal threshold values are raw-score-specific.
5. **Conclusion**: no clear problem was found with 0.65/0.95 for their current use (raw-score
   ranking/tiering) — **thresholds were not changed**, per the ticket's own instruction to change
   them only if the analysis demonstrated a clear problem.

**Dashboard methodology update** (text only, no functional change):

- `dashboard/lib/caveats.py` — added a new caveat panel, **"Why 0.65 and 0.95 — and their
  limits"**, summarizing all of §2 above: the heuristic rule, the sensitivity findings, and the
  explicit statement that these thresholds do not transfer to `calibrated_probability`.
- `dashboard/pages/risk_intelligence.py` — added a one-line caption under the existing
  precision/recall/F1 chart pointing to the new caveat panel; wired `"thresholds"` into that
  page's existing `render_caveats(...)` call (previously `["calibration", "causal", "temporal"]`,
  now includes `"thresholds"`).

## 3. What changed (3 files)

| File | Change |
|---|---|
| `notebooks/11_threshold_rationale.ipynb` | **New.** Full analysis notebook per §2. Fully executed — every number is a genuine computed output, not hand-typed. |
| `dashboard/lib/caveats.py` | Added `_thresholds_body()` + `"thresholds"` entry in `CAVEAT_DEFS`. |
| `dashboard/pages/risk_intelligence.py` | Added one caption line; added `"thresholds"` to the page's `render_caveats(...)` call. |

**Not touched:** `06_risk_scoring.ipynb` (the thresholds' original source — left exactly as-is,
since the rule was reproduced, not changed), any other notebook, any model, any existing output
file, `risk_tier` assignment, the 0.65/0.95 values themselves, and every other dashboard page.

## 4. Validation performed

1. **Re-derivation check** — the notebook's own re-computed High/Medium thresholds are asserted
   equal to production values (`risk_scoring_summary.json`); both assertions passed.
2. **Notebook executed end-to-end** via a real Jupyter kernel (`nbclient`) — zero errors; checked
   every code cell's output for an `error` output type — none found.
3. **Syntax check** — all dashboard `.py` files parse cleanly after the edits.
4. **Streamlit `AppTest` suite** — all 5 pages run with zero exceptions (including Customer 360's
   full gate → filter → select flow). No regressions.
5. **Live browser check** — started the real app, expanded both the "Model performance &
   threshold trade-off" and "Methodology & limitations" panels on Risk Intelligence, confirmed the
   new caption and the new "Why 0.65 and 0.95" panel render correctly (including the `→` arrows
   and inline-code spans in the calibrated-probability comparison sentence).
6. **Isolation check** — confirmed via file-modification-time comparison that exactly the 3 files
   in §3 changed; nothing else under `outputs/`, `models/`, `notebooks/`, `src/`, or `dashboard/`
   was touched.

## 5. Acceptance criteria — status

| Criterion | Met? |
|---|---|
| Thresholds have a documented rationale | ✅ — the exact selection rule (55% precision target for High, F1-argmax for Medium) is now explicit in both the notebook and the dashboard, explicitly labeled a heuristic, not a statistically optimal derivation |
| Sensitivity analysis exists | ✅ — §2.3 above: precision-target sweep for High, F1-flatness band for Medium, both in the executed notebook |
| Dashboard explanation is concise and accurate | ✅ — one caption + one caveat panel, no UI redesign, states plainly that thresholds don't transfer to calibrated probabilities |

## 6. Notes for the next reviewer

- This notebook's §4 data (calibrated-probability distribution within each tier) is a ready
  starting point if a future ticket ever needs to define tiers directly on `calibrated_probability`
  — that re-tiering exercise is explicitly out of scope here.
- Ticket A-06 (false positive / false negative analysis) can reuse this notebook's re-derived
  thresholds and the same `risk_scoring_predictions.csv` / temporal-holdout population.
