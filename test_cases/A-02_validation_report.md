# Validation Report — Ticket A-02: Probability calibration

**Status:** TODO → **REVIEW**
**Priority:** CRITICAL | **Category:** Machine Learning
**Date:** 2026-09-09

---

## 1. Inspection performed before changing anything

- **`notebooks/05_temporal_validation.ipynb`** — confirmed `models/xgboost_temporal_full.joblib` and
  `models/xgboost_temporal_proxy_controlled.joblib` were trained on 100% of `train.csv` (v1,
  Jan-2017-cutoff features, 992,931 rows), with `scale_pos_weight` used for class-imbalance
  handling. No leftover, unused-by-training slice of v1 exists.
- **`notebooks/06_risk_scoring.ipynb`** — confirmed `risk_score_full` / `risk_score_proxy_controlled`
  in `outputs/risk_scoring_predictions.csv` are raw `predict_proba` output on the temporal holdout
  (`kkbox_modeling_dataset_v2.csv`, Mar-2017 outcomes, 970,960 rows, never used for training). §7 of
  that notebook already documents severe miscalibration (reliability bins all overconfident, worse
  at higher scores) and explicitly names post-hoc calibration as unfinished follow-up work.
- **Model artifacts** — both `.joblib` files load correctly; no retraining was performed or needed
  for this ticket (calibration only needs the model's already-computed output scores + true labels,
  both already present in `risk_scoring_predictions.csv`).
- **A-01 changes** — confirmed the dashboard currently has no `P(churn) x revenue` calculation
  anywhere to migrate onto a calibrated column (A-01 renamed the one metric that could have been
  read that way to an explicitly non-probabilistic "High-Risk Historical Revenue Exposure"). This
  means there is nothing to rewire in the dashboard yet — consistent with this ticket's "do not
  redesign the dashboard yet" instruction.

## 2. Methodology

### Calibration-fit / calibration-eval split (not a train/holdout split)

Since the model was trained on all of v1 with no unused slice available, this notebook instead
splits the **temporal holdout itself** into two random, `is_churn`-stratified halves
(`random_state=42`):

| Split | Rows | Churn rate | Used for |
|---|---:|---:|---|
| `calib_fit` | 485,480 | 8.99% | Fitting the sigmoid and isotonic calibrators only |
| `calib_eval` | 485,480 | 8.99% | Brier score, reliability curve, method selection — **untouched by fitting** |

Both halves are the same population (same cutoff, same "future" period never seen during
training), so there's no train/test population mismatch — the standard risk when calibrating on
training-set scores instead. No temporal leakage: `calib_eval` never influences any parameter used
to score it.

### Methods compared

- **Sigmoid (Platt scaling)** — 1-feature `LogisticRegression` mapping raw score → P(churn).
- **Isotonic regression** — non-parametric monotonic step function; ~43,600 positives in
  `calib_fit` per model, comfortably enough to fit without overfitting (per the ticket's own
  "if sample size permits" caveat).

No hyperparameter tuning was performed on either — both fit with library defaults, per the
ticket's explicit instruction.

## 3. Results (all figures from `calib_eval`, held out from fitting)

| Model | Method | Brier score | vs. raw | ROC-AUC |
|---|---|---:|---:|---:|
| full | raw | 0.1180 | — | 0.8709 |
| full | sigmoid | 0.0602 | -49.0% | 0.8709 |
| full | **isotonic (winner)** | **0.0567** | **-52.0%** | 0.8712 |
| proxy_controlled | raw | 0.1133 | — | 0.8494 |
| proxy_controlled | sigmoid | 0.0597 | -47.4% | 0.8494 |
| proxy_controlled | **isotonic (winner)** | **0.0573** | **-49.4%** | 0.8499 |

**Isotonic regression won for both models** (lower Brier score) and is what populates the final
`calibrated_probability` columns.

**ROC-AUC barely moves** (full: 0.8709 → 0.8712; proxy: 0.8494 → 0.8499) — confirming calibration
fixed the probability *values* without hurting *ranking power*. `risk_tier` is built on raw-score
ranking (`06_risk_scoring.ipynb`) and remains valid and unchanged.

**Global sanity check** — mean `calibrated_probability` across all 970,960 customers is **0.0901**,
against an actual base churn rate of **0.0899** — calibrated scores are correctly centered.
The raw score's mean was **0.2931** — confirming the raw score was inflated **~3.3x** on average,
exactly the effect `06_risk_scoring.ipynb` predicted from `scale_pos_weight`.

Full reliability diagram (raw vs. sigmoid vs. isotonic, both models, quantile bins) is rendered
inline in `notebooks/10_probability_calibration.ipynb`, §4.

## 4. What changed (all additive — nothing existing was modified)

| File | Type | Why |
|---|---|---|
| `notebooks/10_probability_calibration.ipynb` | **New** | The calibration notebook itself: loads existing scores, splits, fits, evaluates, selects, applies, saves. Fully executed — all outputs (tables, printed diagnostics, reliability plot) are real, not hand-typed. |
| `outputs/calibrated_probabilities.csv` | **New** | Per-customer `msno`, `is_churn`, `risk_tier`, `calib_split`, both raw scores, and both `calibrated_probability*` columns — raw and calibrated clearly separated, per acceptance criteria. |
| `outputs/calibration_diagnostics.json` | **New** | Machine-readable methodology, split sizes, winning method per model, and every Brier/ROC-AUC figure in §3, for downstream reuse without re-running the notebook. |

**Not touched:** `outputs/risk_scoring_predictions.csv`, `outputs/risk_scoring_summary.json`,
`outputs/risk_scoring_threshold_analysis.csv`, any other existing `outputs/*`, any `models/*.joblib`,
any existing notebook (`01`–`09`), anything under `src/`, and anything under `dashboard/`. Confirmed
via file-modification-time check before and after — only the 3 new files above changed on disk.

## 5. "Update downstream probability-based calculations" — status

Per this ticket's own instruction ("do not redesign the dashboard yet") and A-01's audit (no
existing `P(churn) x revenue` calculation exists anywhere in the current codebase), there is
**nothing to migrate today**. `calibrated_probability` now exists in
`outputs/calibrated_probabilities.csv`, ready for whichever future ticket reintroduces a genuine
expected-loss metric on top of it.

## 6. Validation performed

1. **Environment check** — confirmed `scikit-learn` 1.9.0, `xgboost` 3.4.1 available and models
   load without error.
2. **Notebook executed end-to-end** via `nbclient` (real Jupyter kernel, `python3`) — zero errors,
   all cells produced real output (verified by reading the saved `.ipynb`'s cell outputs directly,
   not by re-typing numbers).
3. **Internal consistency checks** (asserted in the notebook itself): no NaNs in inputs, both
   calibrated-probability columns bounded in `[0, 1]`.
4. **Isolation check** — `find -newermt` before/after confirms only the 3 files in §4 changed
   anywhere under `outputs/`, `models/`, `notebooks/`, `src/`, or `dashboard/`.
5. **Streamlit `AppTest` regression suite** — re-ran the full 5-page suite (including Customer
   360's gate → filter → select flow) used for prior tickets. **Zero regressions** — identical
   pass/fail results to before this ticket, as expected since `dashboard/` was not touched.
6. **No stray artifacts** — checked for and found no `.ipynb_checkpoints` or other leftover files
   from notebook execution.

## 7. Acceptance criteria — status

| Criterion | Met? |
|---|---|
| Calibration metrics and curve exist | ✅ — Brier score + ROC-AUC table (§3) and reliability diagram, both models, in the executed notebook |
| Calibrated probability is clearly separated from raw risk score | ✅ — `calibrated_probability` / `calibrated_probability_proxy_controlled` are new columns alongside the unchanged `risk_score_full` / `risk_score_proxy_controlled` in a new file; nothing renamed or overwritten |
| No leakage in calibration | ✅ — calibrators fit only on `calib_fit`; every reported metric computed on `calib_eval`, which never influenced fitting; no training data used for calibration fitting (rationale in §2) |

## 8. Notes for the next reviewer

- This notebook does not change `risk_tier`, the 0.65/0.95 thresholds, or any dashboard-visible
  number — it is purely additive. Ticket **A-05** (risk threshold rationale) and any future ticket
  that wires `calibrated_probability` into a dashboard-facing expected-loss metric are natural
  next steps, not part of this ticket's scope.
- Isotonic regression was chosen by Brier score on both models; if a future reviewer prefers
  sigmoid for its smoother, extrapolation-safer shape, both calibrators' diagnostics are in
  `calibration_diagnostics.json` to compare without re-running anything.
