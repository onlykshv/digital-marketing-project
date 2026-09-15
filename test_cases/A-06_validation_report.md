# Validation Report — Ticket A-06: False positive / false negative analysis

**Status:** TODO → **REVIEW**
**Priority:** MEDIUM | **Category:** Machine Learning
**Date:** 2026-09-09

---

## 1. Inspection performed before changing anything

- **`06_risk_scoring.ipynb`** and **`11_threshold_rationale.ipynb`** (A-05) — confirmed the
  dashboard's actual operational cutoff: every segment in `marketing_action_plan.csv` is built
  from `risk_tier in {High, Medium}`, i.e. raw score &ge; 0.65. Used this as "the chosen
  operational threshold" the ticket asks for, rather than an arbitrary 0.5.
- **`outputs/kkbox_modeling_dataset_v2.csv`** (the temporal holdout's full feature set) and
  **`outputs/risk_scoring_predictions.csv`** (`risk_score_full`, already computed) — confirmed
  these two files together have everything needed (features + scores + true labels) without
  reloading any model or re-scoring.
- **`outputs/risk_scoring_threshold_analysis.csv`** — the existing precision/recall sweep, used as
  an independent cross-check for this notebook's re-derived confusion matrix at 0.65.

## 2. What was done

Built **`notebooks/12_error_analysis.ipynb`** — a new, read-only notebook (no retraining, no
re-scoring, no change to the production scoring pipeline) that:

1. **Merges** `kkbox_modeling_dataset_v2.csv` (features) with `risk_scoring_predictions.csv`
   (`risk_score_full`) on `msno`.
2. **Defines TP/FP/FN/TN** at threshold 0.65 (`predicted_positive = risk_score_full >= 0.65`).
3. **Confusion matrix**: TP=57,307, FP=72,428, FN=30,023, TN=811,202.
4. **Cross-check**: re-derived precision (0.441724) and recall (0.656212) from this confusion
   matrix and asserted they match `risk_scoring_threshold_analysis.csv`'s saved row for threshold
   0.65 exactly — confirms this notebook's independent computation agrees with the production
   scoring notebook.
5. **Compares FP/FN/TP/TN group medians** across every feature the ticket names: auto-renew status
   (`latest_is_auto_renew`, `auto_renew_pct`), recency (`days_since_last_txn`), tenure
   (`tenure_days_at_cutoff`), transaction volume/value (`total_transactions`,
   `avg_revenue_per_txn`, `total_revenue`), payment method (`latest_payment_method_id`, most
   common per group), and membership status (`latest_is_cancel`, `membership_remaining_days`,
   `cancel_rate`).
6. **Findings**, written *after* inspecting the actual computed tables (see §3 -- an initial draft
   written before execution assumed a simpler pattern and was rewritten once the real numbers
   contradicted part of it; see §4).

## 3. Key findings (from the executed notebook)

- **Biggest blind spot: long-tenured, high-value customers.** FN customers have the *highest*
  median tenure (1,303 days) and *highest* median historical revenue (NT$2,682) of all four
  groups -- above even TP (876 days, NT$1,782) and TN (1,036 days, NT$1,937). The model misses
  are disproportionately veteran, higher-spending accounts, not marginal ones.
- **Auto-renew and payment method cleanly track the model's own top driver**: median
  `latest_is_auto_renew` is 0 for TP & FP, 1 for FN & TN; dominant payment method matches the same
  split. FP customers genuinely look like churners on the model's strongest signal -- they just
  didn't churn this particular month.
- **Recency does not split cleanly**: TP has the *longest* median gap since last transaction (26
  days) of any group -- longer than FN (20), FP (16), or TN (13). No single feature discriminates
  error type on its own.
- **`latest_is_cancel`/`cancel_rate` show no median signal** (0 for all groups) -- correctly
  flagged in the notebook as a limitation of using medians on a mostly-zero flag, not a finding.
- **Every finding is framed as an association, with an explicit no-causal-claim statement** at the
  end of the findings section.

## 4. A verification note worth being explicit about

The findings prose was drafted once, before the notebook was executed, based on a plausible-
sounding hypothesis ("FP looks like TP, FN looks like TN" across every feature). After execution,
the actual group-median table contradicted that hypothesis on tenure and total revenue (FN turned
out to be more extreme than TN on both, not merely similar) and on recency (no clean split at
all). The findings cell was **rewritten to match the real computed output** before this ticket was
considered complete -- this is called out explicitly here because it's exactly the kind of
unverified claim this whole tracker exists to catch, and it was caught during this ticket's own
validation pass rather than being left in.

## 5. What changed (2 files, both new/additive)

| File | Change |
|---|---|
| `notebooks/12_error_analysis.ipynb` | **New.** Full error-analysis notebook per §2-3. Fully executed via a real Jupyter kernel. |
| `outputs/error_analysis_summary.json` | **New.** Confusion matrix, precision/recall, and group medians from this run, for reuse without re-running the notebook (e.g. by a future methodology page, ticket U-02). |

**Not touched:** `06_risk_scoring.ipynb` or any other notebook, any model, any existing output
file, `risk_tier` assignment, the production scoring pipeline, and the entire `dashboard/`
directory -- this ticket's own text frames it as an analysis for the "IEEE report/viva," not a
dashboard feature, and neither the Fix Prompt nor the Acceptance Criteria ask for a dashboard
change, so none was made.

## 6. Validation performed

1. **Independent precision/recall cross-check** — re-derived from this notebook's own confusion
   matrix and asserted equal to `risk_scoring_threshold_analysis.csv`'s saved values; both
   assertions passed exactly.
2. **Notebook executed end-to-end** via `nbclient` (real Jupyter kernel) — checked every code
   cell's output for an `error` output type; none found.
3. **Findings verified against actual output** and rewritten where the pre-execution draft didn't
   match (§4) — `nbformat.validate()` re-run after the edit to confirm the notebook file is still
   well-formed.
4. **Isolation check** — confirmed via file-modification-time comparison that exactly the 2 files
   in §5 changed; nothing else under `outputs/`, `models/`, `notebooks/`, `src/`, or `dashboard/`
   was touched.

## 7. Acceptance criteria — status

| Criterion | Met? |
|---|---|
| Confusion matrix exists | ✅ — §2.3, cross-checked against the existing threshold sweep |
| FP/FN profiles are quantified | ✅ — full group-median table across every named feature, plus dominant payment method per group, all in the executed notebook |
| Findings explicitly distinguish association from causation | ✅ — explicit no-causal-claim statement in the findings section |
