# Final-submission fixes and temporal model benchmark

**Date:** 2026-10-02
**Scope:** fixes A1, A3 and A4 from `FINAL_PRESENTATION_READINESS_AUDIT.md`, a claim-safety wording pass, and a temporal benchmark of candidate models. No redesign, no new features. The segmentation pipeline, the production model and notebook 05 are unchanged.

## 1. Safety snapshot

Commit **`1e01a74`**: "Snapshot: Romer-layout UI redesign, 18 Sep audit fixes and refurbishment tests". It holds all work up to the audit (16 modified and 3 new files). `data.zip` and `outputs.zip` are not committed. Everything below is **uncommitted** on top of it.

## 2. Fixes

| # | Problem | Fix | Where |
|---|---|---|---|
| A1/A2 | 5,890 Medium/High-risk customers were shown as "Stable / Monitor" → "Monitor only" / "low churn risk" | The action plan defines Stable / Monitor as *Low risk minus the unmatched at-risk residual*. The per-customer file gave exactly those 5,890 customers (1,255 High + 4,635 Medium) the wrong label. The loader now applies the action plan's own rule (`data.resolve_segment`); they appear as "Unmatched At-Risk (no segment)" → "Standard outreach". The file's label is kept as `segment_file_label`, and a short note explains it next to affected customers. `outputs/` is unchanged, and no tier, score or probability changes. | `dashboard/lib/data.py`, `pages/priority_customers.py`, `pages/customer_360.py` |
| A3 | A calibrated probability could display as "100%" (1,277 customers) | `theme.fmt_probability`: anything that would display as 0% / 100% shows "<1%" / ">99%". It also handles Python's round-half-to-even (p = 0.005 used to display "0%"). The underlying numbers are unchanged. | `lib/theme.py`, `lib/copilot_engine.py`, both pages |
| A4 | The segment-mode "compare with Champions" prompt returned the generic overview | Prompt removed; the working customer-mode prompt is kept | `pages/retention_copilot.py` |
| Wording | "highest ROI cell" / "clearest ROI case" (no campaign data supports an ROI claim) | Now "top-priority cell" / "strongest candidates". The string also changed in notebook 09 (it uses it as a lookup key) and in two generated label files. No numbers changed. | notebooks 08 and 09; `outputs/risk_value_matrix.csv`, `outputs/marketing_value_analysis_results.json` |
| Wording | HRR described as "revenue at stake / at risk" | Historical Realized Revenue / "revenue to date" | `pages/action_center.py`, `lib/copilot_engine.py`, `lib/agent.py`, `lib/agent_tool_schemas.py`, `lib/agent_tools.py`, `lib/data.py` |
| Wording | Newcomer text: "points to an onboarding gap" (causal) | States the rule (short tenure, not discount usage) | `lib/data.py` |
| Units | "avg revenue/txn 305 vs 150" had no currency | Rendered as ₹ amounts | `lib/theme.py`, `lib/copilot_engine.py` |
| Docs | README `<PASTE LINK HERE>`; dashboard README said only Customer 360 loads the 971K-row table | Placeholder replaced (the real Drive links are still needed); memory note corrected (Priority Customers auto-loads) | `README.md`, `dashboard/README.md` |

## 3. Tests

| When | Passed | Failed | Skipped |
|---|---|---|---|
| Audit baseline (2 Oct) | 280 | 0 | 0 |
| After A1/A3/A4 | 293 | 0 | 0 |
| Final | **298** | **0** | **0** |

Command: `python -m pytest tests/ -p no:cacheprovider -q` (≈80 s).

- **18 new tests** in `tests/test_final_submission_fixes.py`.
- **1 existing assertion updated:** `test_final_visual_polish.py` searched the source code for the old probability guard. It now checks the new formatter, and also checks the behaviour directly (a missing value shows "—").
- No tests were deleted.

## 4. Temporal model benchmark

Artifacts:
- `notebooks/13_model_benchmark.ipynb` (executed)
- `src/model_benchmark.py`
- `outputs/model_benchmark_results.csv`, `outputs/model_benchmark_summary.json`
- `outputs/model_benchmark_plots/{pr_auc,roc_auc,precision_at_2_3pct}.png`

Two earlier attempts were **invalid and deleted**: a float32 load rounded the yyyymmdd date features, and a later run was stopped for memory. None of their numbers are used.

### Methodology

**Shared by every model:**
- **Test population:** the production temporal holdout (`outputs/kkbox_modeling_dataset_v2.csv`, March-2017 churn, 970,960 customers), never subsampled.
- **Training data:** notebook 05's v1 temporal training set (February-2017 churn).
- **Features:** notebook 05's full feature set and preprocessing.
- **Metrics:**
  - PR-AUC is primary.
  - ROC-AUC.
  - Brier score, both raw and after isotonic calibration on notebook 10's calibration halves.
  - Precision and recall in the top 22,692 customers, which is 2.337% of the holdout and the size of the production High tier.
- **Not compared:** fixed-threshold F1, because the models' raw score scales differ.

**Differs by model:**

| Model | Training configuration |
|---|---|
| Rule: auto-renew off | latest_is_auto_renew == 0; its score is the training-set churn rate of the customer's group |
| Logistic Regression | Notebook 02 settings (`class_weight='balanced'`, `max_iter=1000`); full training set; converged in 276 iterations |
| LightGBM | Fixed, untuned, memory-conscious: 300 trees, lr 0.05, 31 leaves, depth 8, bagging/feature fraction 0.8, `scale_pos_weight` = 14.64 (same as XGBoost), `n_jobs=2` |
| Random Forest (**resource-constrained**) | 150 trees, depth 16, min leaf 20, `n_jobs=2`, a **stratified 300,000-row sample** of the 992,931 training rows. Not notebook 03's configuration |
| XGBoost (tuned, production) | Not retrained. Its holdout scores were read from `risk_scoring_predictions.csv` and reproduce notebook 05's 0.8696 / 0.5432 exactly |

**Memory safety:**
- Each model ran as its own process, sequentially, after a free-RAM check.
- Scores were saved immediately; completed models are never re-run.
- Preprocessed data is held sparse in float32 (matches notebook 05 within 3e-6); the holdout is scored in chunks.
- All five models completed; none hit the memory guard.

### Results (same 970,960-customer holdout, churn 8.99%)

| Model | PR-AUC | ROC-AUC | Brier (raw) | Brier (after isotonic) | Precision@2.3% | Recall@2.3% | Train rows | Fit time |
|---|---|---|---|---|---|---|---|---|
| Random Forest (resource-constrained) | **0.5498** | **0.8753** | 0.1150 | **0.0561** | **0.812** | 0.211 | 300,000 | 65 s |
| XGBoost (tuned, production) | 0.5432 | 0.8696 | 0.1179 | 0.0567 | 0.800 | 0.208 | 992,931 | (notebook 05) |
| Logistic Regression | 0.5234 | 0.8543 | 0.1209 | 0.0569 | 0.755 | 0.196 | 992,931 | 43 s |
| LightGBM | 0.5162 | 0.8669 | 0.1208 | 0.0580 | 0.725 | 0.188 | 992,931 | 35 s |
| Rule: auto-renew off | 0.2626 | 0.7306 | 0.0693 | 0.0681 | 0.411 | 0.107 | 992,931 | — |

**PR-AUC minus production XGBoost:** paired bootstrap, 500 resamples, 95% interval. It covers holdout sampling only, not training variability.

| Model | Difference | 95% interval |
|---|---|---|
| Random Forest | +0.0066 | +0.0052 to +0.0082 |
| Logistic Regression | −0.0198 | −0.0220 to −0.0173 |
| LightGBM | −0.0270 | −0.0286 to −0.0253 |
| Rule | −0.2806 | −0.2833 to −0.2781 |

### Final model decision (accepted 2026-10-02)

**The tuned XGBoost remains the production model.** It is not claimed to be the best model.

> Random Forest achieved the highest observed temporal PR-AUC (0.550) versus 0.543 for the production tuned XGBoost. However, the Random Forest was trained using a resource-constrained 300,000-row sample and a single training run, while XGBoost was tuned and trained using the established production setup. The small observed difference is therefore not treated as definitive model superiority. XGBoost remains the production model, while the benchmark demonstrates that the ML approaches substantially outperform the simple auto-renew-off rule.

The bootstrap intervals capture **holdout sampling variance only**. Training and seed variance (a different seed, Random Forest sample or tuning run) was not measured. No further model experiments were run.

## 5. Source-label check: the 5,890 "Unmatched At-Risk" customers

**Why the label is missing from the source file.**
- Notebook 07 defines **six** labels.
- Its four at-risk rules (auto-renew off, tenure ≥ 730, tenure < 180, discount > 5%) are deliberately not exhaustive. An at-risk customer matching none of them falls into the default `Stable / Monitor`. The notebook prints the count (5,890) and a warning not to treat them as safe.
- The **seventh** group was introduced later, by notebook 09, which relabels exactly `risk_tier ∈ {High, Medium} & segment == "Stable / Monitor"` as `Unmatched At-Risk (no segment)` when building `marketing_action_plan.csv`. It never wrote that label back to `customer_segments.csv`.

**Why these customers match no rule:**
- auto-renew is ON for 5,176; the other 714 have no transaction record, so the field is missing;
- tenure is missing for 3,241 and 180–729 days for 2,649;
- none has a discount above 5%.

**Is notebook 07's logic correct?** Yes, for its own 6-label design.

**Can the file be safely regenerated? No.**
- **It wouldn't fix the label.** Rerunning notebook 07 would reproduce the same six labels.
- **It would break things.** The current `outputs/segment_summary.csv` (with `rule_definition`, `actual_churn_rate_pct`, the median columns and `marketing_objective`) comes from a "07 follow-up validation" step that exists in no notebook. Notebook 07 writes a different column layout. A rerun would overwrite the file that notebook 09 and the dashboard read, and would also recompute the SHAP drivers.

**Decision:** no regeneration. The display correction (`data.resolve_segment`) applies notebook 09's own rule, so the dashboard and the action plan agree by construction.

**Verified:**
- All 7 group counts in the dashboard equal `marketing_action_plan.csv`: 113,820 / 6,261 / 1,796 / 1,968 / **5,890** / 321,006 / 520,219.
- The 5,890 are the same customers in `customer_segments.csv`, `customer_value_tiers.csv` (notebook 09's rule), notebook 07's printed count and the action plan.

## 6. Final browser QA (2026-10-02, real Chrome, fresh server, no API key)

| Check | Result |
|---|---|
| All six pages render | Overview, Priority Customers, Customer Value, Action Center, Customer 360, Retention Intelligence: pass |
| High-risk customer not "Monitor only" | Pass. The audit's top customer (`2eO88…`) shows HIGH · Unmatched At-Risk · **Standard outreach** on Priority Customers, Customer 360 and in Retention Intelligence. "Who should we contact first?" returns 5 High-risk customers, all "Standard outreach". |
| No bare 0% / 100% | Pass. That customer shows Estimated Churn Probability **>99%** (Priority Customers, Customer 360, the assistant's Champions comparison). |
| Champions comparison button | Pass. Absent in segment mode (3 prompts); present and answering in customer mode. |
| Currency / HRR terminology | Pass. ₹ throughout; "revenue to date", "Historical Realized Revenue: money already collected, not a forecast", "High-Risk Historical Revenue Exposure". No "at stake" anywhere. |
| No "highest ROI" | Pass |
| No unsupported causal language | One instance found and fixed during QA: Overview said "personal outreach **pays off**" (there is no campaign-response data). It now says "is most worth considering", and a regression test guards it. |

## 7. Files changed since `1e01a74`

- **Modified:**
  - Dashboard code: `dashboard/lib/{data,theme,copilot_engine,agent,agent_tools,agent_tool_schemas}.py`, `dashboard/pages/{overview,priority_customers,customer_360,retention_copilot,action_center}.py`.
  - Docs, notebooks and tests: `README.md`, `dashboard/README.md`, `notebooks/08_marketing_value_analysis.ipynb`, `notebooks/09_marketing_action_plan.ipynb`, `tests/test_final_visual_polish.py`.
- **New:** `src/model_benchmark.py`, `notebooks/13_model_benchmark.ipynb`, `tests/test_final_submission_fixes.py`, this report.
- **Generated, git-ignored:** `outputs/model_benchmark/`, `outputs/model_benchmark_results.csv`, `outputs/model_benchmark_summary.json`, `outputs/model_benchmark_plots/`. Two label strings in `outputs/risk_value_matrix.csv` and `outputs/marketing_value_analysis_results.json`.

## 8. Remaining known limitations

- **The benchmark covers the full feature set only.** The proxy-controlled set is not included.
- **The real Drive links** for `data.zip` / `outputs.zip` still need adding to the README if they should be there.
- **"−2.5%" average discount rate** in the segment evidence is unchanged (it's a real negative average in the source data).
- **Root cause of A1 still upstream:** `customer_segments.csv` still carries notebook 07's 6-label scheme; it is corrected at load time (section 5) and deliberately not regenerated.
- **Notebook 08's 6-group summary:** Customer Value's "Where revenue concentrates" chart reads `value_by_segment.csv`, which uses the same 6-label scheme, so the 5,890 unmatched customers' revenue is counted inside Stable / Monitor there.
- **Source text left unchanged:** the action plan's own intensity label for At-Risk Newcomer is "Monitor only (no value data)", and its Auto-Renew-Off objective calls it the "highest-leverage campaign". Both are verbatim from `marketing_action_plan.csv`.
- **AI synthesis never exercised live:** no API key exists, so every answer comes from the deterministic fallback.
- **Memory:** the machine has 7.4 GB RAM; loading the customer table can make the browser briefly unresponsive. Close other apps before a demo.
