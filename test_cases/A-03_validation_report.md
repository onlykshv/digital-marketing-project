# Validation Report — Ticket A-03: Risk score labeling

**Status:** TODO → **REVIEW**
**Priority:** HIGH | **Category:** UX + Analytics
**Date:** 2026-09-09

---

## 1. Inspection performed before changing anything

Searched the entire dashboard (`pages/`, `lib/`) and project documentation (`README.md`,
`dashboard/README.md`, `FEATURE_AUDIT.md`, and notebooks 05/06's markdown cells) for every
occurrence of `risk score`, `Risk Score`, `probability`, `Probability`, `score`, and any
percentage-formatting applied near a score value. Also reviewed A-01 and A-02's changes, since
A-02 introduced the first real "calibrated probability" artifact this ticket needed to account for.

**Findings, by location:**

| Location | Issue found | Action |
|---|---|---|
| `pages/customer_360.py` — results table column header | Labeled "Risk Score" (ambiguous) | Renamed to "Model Risk Score" |
| `pages/customer_360.py` — profile stat row | Labeled "Risk Score" | Renamed to "Model Risk Score"; added the ticket's exact explanatory line underneath |
| `pages/customer_360.py` — "why flagged" fallback bullet | lowercase "the risk score reflects..." | Aligned to "the Model Risk Score reflects..." |
| `pages/customer_value.py` — KPI caption | "The underlying risk score is not yet calibrated" | Reworded to name it explicitly: "based on Model Risk Score, which is not a calibrated probability" |
| `pages/risk_intelligence.py` — section subtitle | "the model's risk score" | Aligned to "Model Risk Score" |
| `pages/risk_intelligence.py` — threshold expander (caption, slider label, chart x-axis) | **"Probability threshold" / "at any probability cutoff"** — the threshold sweep in `risk_scoring_threshold_analysis.csv` is built on the **raw**, uncalibrated score (confirmed against `06_risk_scoring.ipynb`'s `threshold_sweep(y_true, proba_full, ...)`), so calling it a "probability" mislabels it. This was the clearest concrete violation found. | All three renamed to "Model Risk Score [threshold/cutoff]"; caption now explicitly adds "This is the raw, uncalibrated score -- not a probability." |
| `lib/caveats.py` — `_calibration_body` | **"A score of 90% does not mean a 90% chance of churning"** — the raw score itself was formatted with a `%` sign. Direct violation of "no percentage sign for the raw risk score." | Changed to "A score of 0.90 does not mean a 90% chance of churning" (the *hypothetical true probability* concept correctly keeps its %; only the raw-score number was fixed) |
| `lib/caveats.py` — `_calibration_body` / `_revenue_exposure_body` | Text said calibration was "tracked as separate follow-up work" -- now stale, since A-02 delivered it | Updated to state a calibrated `Estimated Churn Probability` now exists in `outputs/calibrated_probabilities.csv`, while being explicit that no dashboard calculation uses it yet |
| `lib/caveats.py` — CAVEAT_DEFS title | "Risk scores aren't literal probabilities" | Renamed to "Model Risk Score isn't a literal probability" |
| `lib/data.py` docstring | Refers to "raw, uncalibrated predict_proba output" | Already unambiguous (developer-facing, doesn't claim raw score is a probability) — **left unchanged** |
| `06_risk_scoring.ipynb`, `08_marketing_value_analysis.ipynb` | Use "predicted probability" / "% of base" language, and a table literally titled "Model says X% / Actually churns Y%" | **Left unchanged** — this is the notebook's own diagnostic finding illustrating *why* the raw score is miscalibrated, not a claim that it is one; already unambiguous in context. Editing an already-executed, already-cited (by A-01/A-02) notebook risked unintended diffs for no benefit. |
| `dashboard/README.md` | "risk-score miscalibration" (topic-list bullet) | Already accurate, no change needed |
| Every `fmt_pct()` call site | Checked each one individually | None apply a `%` format to `risk_score_full` or `calibrated_probability` -- all are legitimate percentages (churn rate, precision/recall, % targeted) |

## 2. What "Model Risk Score" vs. "Estimated Churn Probability" looks like now

- **Every visible reference to the raw XGBoost output is now labeled "Model Risk Score"** and
  formatted as a plain decimal (e.g. `0.95`), never with a `%` sign.
- **No dashboard calculation currently displays a calibrated probability** (A-02 produced
  `calibrated_probability` as a standalone file, not wired into any page — deliberately, per this
  ticket's "do not migrate calculations" instruction and A-02's own scope limit). Per the ticket's
  conditional instruction ("if calibrated probabilities are later introduced, label them
  separately as 'Estimated Churn Probability'"), that label is used only in forward-looking
  methodology text (caveats.py) explaining what a *future* calibrated display would be called --
  it is not attached to any number on screen today, because no such number is shown yet.
- **Customer 360 now carries the ticket's exact requested copy**, directly under the Model Risk
  Score value in the profile panel: *"Model Risk Score is used for prioritization; it is not a
  calibrated probability."*

## 3. What changed (4 files)

| File | Change |
|---|---|
| `dashboard/pages/customer_360.py` | Renamed both "Risk Score" labels (table column, profile stat) to "Model Risk Score"; widened that table column (`width="medium"`) since the longer label no longer fit the default auto-width -- a direct, necessary consequence of the rename, not a UI redesign; added the ticket's required explanatory caption; aligned one factual-bullet sentence's terminology. |
| `dashboard/pages/customer_value.py` | Reworded the KPI caption to name "Model Risk Score" explicitly and confirm it is not a calibrated probability. |
| `dashboard/pages/risk_intelligence.py` | Renamed the section subtitle, the threshold-expander caption, the slider label, and the chart x-axis title -- all four previously said "probability" while operating on the raw score. |
| `dashboard/lib/caveats.py` | Fixed the one concrete `%`-on-raw-score violation; renamed the "calibration" caveat's title; updated both the "calibration" and "revenue_exposure" caveat bodies to (a) never format the raw score as a percentage and (b) accurately reflect that a calibrated `Estimated Churn Probability` now exists (from A-02) but isn't used in any dashboard calculation yet. |

**Not touched:** `dashboard/app.py`, `dashboard/lib/theme.py`, `dashboard/lib/components.py`,
`dashboard/lib/data.py`, `dashboard/pages/command_center.py`, `dashboard/pages/action_center.py`,
`dashboard/README.md`, any notebook, any model, any output file. Confirmed via file-modification-
time check — nothing under `outputs/`, `models/`, `notebooks/`, or `src/` changed; only the 4
files above changed under `dashboard/`.

## 4. Scope discipline

- **No model logic changed** — no `.joblib`, notebook, or feature engineering touched.
- **No UI redesign** — no new components, no layout changes, no new pages/sections. The one
  necessary technical adjustment (widening a table column so a longer label isn't clipped) is a
  direct, minimal consequence of the label change itself, not a design change.
- **No calculation migrated to calibrated probability** — `calibrated_probability` is mentioned
  only in prose (explaining it exists and where), never substituted into a live KPI or chart. Per
  this ticket's own instruction, that migration is out of scope unless A-03 explicitly required
  it, and it does not.

## 5. Validation performed

1. **Full-project search** for every "risk score" / "probability" / percentage-on-score occurrence
   (§1) — the audit basis for every edit above.
2. **Syntax check** — all dashboard `.py` files parse cleanly after the edits.
3. **Streamlit `AppTest` suite** — all 5 pages run with zero exceptions (including Customer 360's
   full gate → filter → select flow). Identical pass/fail results to before this ticket — no
   regressions.
4. **Live browser smoke test** — started the real app and manually walked through:
   - Customer 360: loaded data, filtered to High risk, selected a row, confirmed the table column
     reads "Model Risk Score" (and is no longer clipped after the width fix), and confirmed the
     profile panel shows "Model Risk Score: 0.95" directly above the required explanatory caption.
   - Risk Intelligence: expanded "Model performance & threshold trade-off," confirmed the caption,
     slider label, and chart x-axis all read "Model Risk Score" (not "Probability"); expanded
     "Methodology & limitations" and confirmed the corrected `0.90` (not `90%`) wording and the new
     calibration-availability sentence both render correctly.
   - Customer Value: confirmed the KPI caption now names Model Risk Score explicitly.
5. **Isolation check** — confirmed via file-modification-time comparison that exactly the 4 files
   in §3 changed, and nothing under `outputs/`, `models/`, `notebooks/`, or `src/` was touched.

## 6. Acceptance criteria — status

| Criterion | Met? |
|---|---|
| All visible raw-score references are unambiguous | ✅ — every occurrence now reads "Model Risk Score"; the Customer 360 profile carries the ticket's exact explanatory sentence |
| Raw score is never formatted as a churn probability | ✅ — the one `%`-on-raw-score instance found (`lib/caveats.py`) is fixed; every other raw-score display already used plain decimals; audited every `fmt_pct()` call site to confirm none touches the raw or calibrated score |

## 7. Notes for the next reviewer

- If a future ticket wires `calibrated_probability` into a dashboard-facing number, the "Estimated
  Churn Probability" label is already anticipated in `caveats.py`'s prose — just attach it to the
  actual displayed value at that time.
- Notebooks 05/06 were audited and found already compliant in context (they exist specifically to
  document the miscalibration problem) — intentionally left unmodified rather than edited for
  terminology consistency with the dashboard, to avoid touching already-cited, already-executed
  analytical artifacts for no substantive gain.
