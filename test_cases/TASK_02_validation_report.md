# Validation Report — Task 02: Deterministic Agent Tool Layer

**Status:** Deterministic tool layer implemented and validated. **Not yet wired to an LLM or any UI** —
per this task's explicit scope, that is deliberately not started. Do not treat this as a finished
end-to-end feature; it is the foundation the next task (LLM tool-calling) will build on.
**Date:** 2026-09-10

---

## 1. Files changed

| File | Change | Why |
|---|---|---|
| `dashboard/lib/agent_tools.py` | **New.** The 9 deterministic tools (§2), each returning `{"ok", "data", "error"}`. | This task's primary deliverable. |
| `tests/test_agent_tools.py` | **New.** 39 tests against real project output files, no mocks. | This task's required test file — see §4. Also the first committed test file in this repo (see `AGENT_ARCHITECTURE_PLAN.md` §A: previously all validation lived in an ephemeral scratchpad). |
| `dashboard/lib/copilot_data.py` | **Bug fix** (5 lines): `get_customer_context()` now guards `latest_is_auto_renew`, `auto_renew_pct`, `total_transactions`, `avg_revenue_per_txn`, `discount_rate`, `cancel_rate` with `pd.notna()`, matching the pattern already used for the three fields next to them. | A real, pre-existing crash this task's own tests caught — see §5. |
| `dashboard/lib/data.py` | **Bug fix** (4 lines): `key_risk_signal()` now guards its three inputs against `None` instead of assuming they're always real numbers. | Same root cause as above — the fixed `get_customer_context()` now hands this function `None` instead of raising before it's ever called, so this function needed its own guard too. |
| `dashboard/lib/copilot_engine.py` | **Bug fix** (6 lines): `build_customer_evidence_lines()`'s auto-renew line no longer uses Python truthiness on `latest_is_auto_renew` (which silently turned `None` into "OFF" -- a factually wrong statement, not just a missing one). New `_fmt_auto_renew()` helper renders `None` as "not available". | Directly exposed by the fix above: before it, this line was unreachable (the page crashed first); after it, this line ran and produced a misleading answer. Fixing it keeps the fix from trading a crash for a wrong fact, which would violate this project's core "never fabricate" principle. |
| `test_cases/TASK_02_validation_report.md` | **New.** This report. | Required deliverable. |

**No other file was touched.** `dashboard/app.py`, `dashboard/lib/theme.py`, `dashboard/lib/components.py`, `dashboard/lib/llm_provider.py`, `dashboard/lib/caveats.py`, and all six `dashboard/pages/*.py` files are unmodified.

## 2. Tools implemented

All 9 tools requested, in `dashboard/lib/agent_tools.py`. Each accepts already-loaded pandas/dict data (never loads anything itself) and returns `{"ok": bool, "data": ..., "error": str | None}`.

| Tool | Reuses | New code |
|---|---|---|
| `get_customer` | `copilot_data.get_customer_context()`, `data.key_risk_signal()` | Wraps them in the ok/error contract |
| `search_customers` | The filter pattern from `pages/priority_customers.py`, generalized | Yes — no reusable function existed; this is the one genuinely new retrieval tool |
| `get_aggregate_metrics` | `data.load_risk_summary()`'s fields, `data.total_realized_revenue()`, `data.high_risk_historical_revenue_exposure()` | Thin wrapper composing existing numbers, plus the by-segment breakdown |
| `get_segment` | `copilot_data.get_segment_context()` | Wraps it; validates against the 7 known segment names first |
| `explain_customer_risk` | `copilot_data.get_customer_context()`, `copilot_data.get_top_drivers()`, `copilot_data.get_population_baselines()` | The deviation-sentence builder (same phrasing style already established in `copilot_engine.py`, kept consistent rather than duplicated verbatim) |
| `recommend_action` | `data.SHORT_ACTION_BY_SEGMENT`, `data.SHORT_WHY_BY_SEGMENT`, `data.AVOID_BY_SEGMENT`, `marketing_action_plan.csv` | Accepts either a segment name or a customer dict |
| `compare_to_champions` | `copilot_data.get_champions_context()` | Accepts either a segment name or a customer dict |
| `rank_segments_by_priority` | `data.priority_opportunities()` **directly, unchanged** | Only reshapes its output into tool-friendly rows |
| `build_dashboard_deep_link` | The `cust360_search` session-state key (the exact, already-proven cross-page mechanism) | New, but deliberately produces plain data only — no Streamlit call, no rendering |

## 3. Source of truth for each tool

| Tool | Source file(s) |
|---|---|
| `get_customer` | `outputs/customer_segments.csv` + `risk_scoring_predictions.csv` + `customer_value_tiers.csv` + `calibrated_probabilities.csv` |
| `search_customers` | Same four files, as the cached merged frame `data.load_customer_lookup_data()` already builds |
| `get_aggregate_metrics` | `outputs/risk_scoring_summary.json`, `outputs/value_by_risk_tier.csv`, `outputs/risk_value_matrix.csv`, `outputs/marketing_action_plan.csv`, `outputs/value_by_segment.csv` |
| `get_segment` | `outputs/marketing_action_plan.csv` + `outputs/segment_summary.csv` |
| `explain_customer_risk` | The above customer files + `outputs/shap_feature_importance.csv` (global driver ranking only — see §6 terminology note) |
| `recommend_action` | `outputs/marketing_action_plan.csv` + `data.SHORT_WHY_BY_SEGMENT` / `AVOID_BY_SEGMENT` (both already-validated restatements of that same file, documented as such in `data.py`) |
| `compare_to_champions` | `outputs/marketing_action_plan.csv` + `outputs/value_by_segment.csv` |
| `rank_segments_by_priority` | `outputs/marketing_action_plan.csv` |
| `build_dashboard_deep_link` | None — pure UI-state plumbing, validated against `app.py`'s actual page registry |

Every one of these is documented in the corresponding function's docstring in `agent_tools.py`, per the task's requirement.

## 4. Tests executed and results

**`tests/test_agent_tools.py` — 39/39 passed.** Pytest-compatible (`test_*` functions, plain `assert`), runnable standalone (`python tests/test_agent_tools.py`) since pytest is not installed and this task said not to add unnecessary dependencies. Covers all 12 required cases (A-L) plus the additionally-required edge cases:

- **A/B.** Valid lookup and nonexistent customer.
- **C/D.** High-risk search; high-risk + high-value search.
- **E.** Aggregate metrics, cross-checked against `risk_scoring_summary.json`'s literal numbers (22,692 High-risk customers, etc.).
- **F/G.** Valid segment (exact `segment_summary.csv` values: 113,820 customers, 20-day median recency, 809-day median tenure) and invalid segment.
- **H.** Risk explanation, including an explicit assertion that no causal phrase ("will churn because", "causes", "guarantee") appears in the output.
- **I.** Action recommendation, by segment and by customer dict, plus the "exactly one argument" contract.
- **J.** Champions comparison, by customer and by segment.
- **K.** Segment ranking — order, exclusion of Champions/Stable, `top_n`.
- **L.** Deep-link generation — valid page + customer, valid page + filters, invalid page.
- **Additional:** empty result sets (Champions filtered to High risk → 0 rows, not an error), limit enforcement and the 200-row cap, ascending/descending sort, malformed `sort_by`/`risk_tier`/`segment`/`limit` inputs, and a customer with a regex-special-character ID (`+`/`/`) to prove `get_customer`'s exact-match lookup is immune to the kind of `.str.contains()` bug found in an earlier session.

**Existing offline Copilot suite (`scratchpad/test_copilot.py`, from the prior Retention Copilot task) — re-run, 34/34 still passed.** Confirms the `copilot_data.py`/`data.py`/`copilot_engine.py` bug fixes (§5) did not regress the already-shipped Retention Copilot page.

**AppTest (`scratchpad/apptest_master_restructure.py`, the existing 6-page suite) — re-run, no new failures.** Every page loads without exception except the one pre-existing, already-documented harness limitation (`AppTest.from_file()` can't resolve `st.page_link` outside `st.navigation`'s page registry on Overview — unrelated to this task, documented in two prior validation reports).

**Live browser regression check.** Restarted the server fresh and specifically exercised the exact customer that crashed before the fix (`gNwFLjQe+7UnzxaHCB58QZEXAFnmRvAKapoxq0O465M=`, one of the ~2,527 customers with no transaction history) end-to-end through Retention Copilot: search → customer context panel renders (`MEDIUM RISK`, `UNKNOWN (NO TRANSACTION DATA) VALUE`, `AT-RISK NEWCOMER`, Estimated Churn Probability 28%, Model Risk Score 0.86, HRR "—") → "Why is this customer at risk?" → full evidence renders with "Key risk signal: Limited transaction history", "Auto-renew: not available" (not the pre-fix-adjacent "OFF"), and every other missing field correctly shown as "not available" rather than fabricated. Confirmed no horizontal overflow.

## 5. A real, pre-existing bug found and fixed (outside this task's original file list, fixed because it blocks honest validation)

`copilot_data.get_customer_context()` — used today by the live Retention Copilot page, not introduced by this task — unconditionally did `int(row["latest_is_auto_renew"])`. ~2,527 of 970,960 customers (0.26%) have **no recorded transaction activity at all**: `latest_is_auto_renew`, `auto_renew_pct`, `avg_revenue_per_txn`, `discount_rate`, `cancel_rate`, and `days_since_last_txn` are all `NaN` for them in `customer_segments.csv` itself (not a merge artifact — confirmed by inspecting the raw file). They are still real, scored customers (valid `risk_tier`, `model_risk_score`, `calibrated_probability` — the model scores them from non-transaction features) — never "not found." The unconditional `int()` cast raised `ValueError: cannot convert float NaN to integer` for every one of them, meaning **Retention Copilot has been crashing today, before this task began, for any of these 2,527 customers searched by exact ID.**

This was caught by this task's own test suite (a direct consequence of the task's explicit instruction to test "missing values"), not discovered separately. Since `agent_tools.get_customer()` wraps this exact function, it could not honestly be called "validated" without fixing the crash — and since the same crash already affects the shipped Retention Copilot page, fixing it here also fixes a live bug, not just a theoretical one for the new tool layer.

**Fix, in three small, pattern-consistent steps** (all documented inline where changed):
1. `copilot_data.get_customer_context()` — the 6 previously-unguarded fields now use the same `pd.notna()` guard already used for the 3 fields next to them.
2. `data.key_risk_signal()` — now returns `"Limited transaction history"` when all three inputs are `None`, and no longer raises on a `None > 30` comparison for a partially-missing case.
3. `copilot_engine.build_customer_evidence_lines()` — the auto-renew line no longer relies on Python truthiness (which silently turned `None` into "OFF", a wrong fact, not just a missing one); a new `_fmt_auto_renew()` helper renders it as "not available".

All three were re-tested (offline suite item 4 above, plus a dedicated regression test in `tests/test_agent_tools.py`: `test_get_customer_no_transaction_history_does_not_crash`, `test_explain_customer_risk_no_transaction_history_does_not_crash`, `test_search_customers_includes_no_transaction_history_customers_without_crashing`) and confirmed live in the browser (§4).

## 6. Terminology — preserved exactly, verified

- **Model Risk Score** (`risk_score_full`) and **Estimated Churn Probability** (`calibrated_probability`) are kept as two distinct fields in every tool's output dict — never merged, never relabeled.
- **Historical Realized Revenue** (`historical_realized_revenue_ntd` / `total_hrr_ntd`) is never called CLV, Lifetime Value, or Future Revenue anywhere in `agent_tools.py` — docstrings explicitly say so.
- **High-Risk Historical Revenue Exposure** (`get_aggregate_metrics`'s `high_risk_historical_revenue_exposure_ntd`, via `data.high_risk_historical_revenue_exposure()` unchanged) is documented in the tool's docstring as NOT an expected-loss figure.
- **`explain_customer_risk`'s driver list is explicitly labeled `top_global_drivers`**, not "this customer's SHAP values" — this project stores only global mean-|SHAP| feature importance (`outputs/shap_feature_importance.csv`), not a per-customer breakdown, and the tool's docstring and field naming make that distinction explicit rather than blurring it.
- **Association, not causation**, verified programmatically: `test_explain_customer_risk_high_risk_customer` asserts the exact forbidden phrases from the task brief ("will churn because", "causes", "guarantee") never appear in `explain_customer_risk`'s output.

## 7. Regression validation checklist (per task §7)

1. **Syntax checks** — `ast.parse()` over every `dashboard/pages/*.py`, `dashboard/lib/*.py`, `app.py`, and both test files: **OK**.
2. **New tests** — `tests/test_agent_tools.py`: **39/39 passed**.
3. **Existing AppTest/offline validation** — `scratchpad/test_copilot.py`: **34/34 passed** (re-run, unchanged from before this task); `scratchpad/apptest_master_restructure.py`: **no new failures** (same one pre-existing harness limitation as always).
4. **All existing dashboard pages still work** — confirmed via AppTest (all 6) and a live browser walkthrough of Overview and Retention Copilot on a freshly restarted server; Customer 360 was not separately re-verified live this pass because it does not call `copilot_data.py` at all (it builds its profile inline from the raw dataframe, confirmed by grep) and is therefore unaffected by the fix in §5 — its AppTest coverage (gate → load → filter → render) already passed.
5. **No analytical outputs changed** — `find outputs notebooks models src -newer test_cases/AGENT_ARCHITECTURE_PLAN.md -type f` returns nothing.
6. **No notebooks/models/src files changed** — same command, same empty result; also confirmed by construction (no tool call in this task opened any file under `notebooks/`, `models/`, or `src/`).

## 8. Files explicitly confirmed untouched

Every notebook (`01_eda.ipynb` through `12_error_analysis.ipynb`), everything under `src/`, everything under `models/`, every file under `outputs/`, `dashboard/app.py`, `dashboard/lib/theme.py`, `dashboard/lib/components.py`, `dashboard/lib/llm_provider.py`, `dashboard/lib/caveats.py`, and all six `dashboard/pages/*.py` files. Confirmed both by construction (tracked which files this session's tool calls touched) and by the `find -newer` timestamp check in §7.

## 9. Known limitations / what could not be validated

- **No LLM/tool-calling integration exists yet, as instructed.** These tools have not been exercised by an actual LLM picking arguments — only by direct Python calls in the test suite and manual verification. The next task (LLM tool-calling) is where that gap closes.
- **`build_dashboard_deep_link`'s `pending_filter` payload is not consumed by any page yet** (documented in its own docstring) — `priority_customers.py`'s filter widgets are still local/unkeyed, exactly as flagged in `AGENT_ARCHITECTURE_PLAN.md` §H. This tool produces valid, safe data today; wiring a page to read it is separate, future work, correctly out of scope for this task.
- **`search_customers`'s 200-row cap and `get_aggregate_metrics`'s scope were sized by judgment**, not a specific product requirement — reasonable given "top 20"-style example questions, but worth revisiting once real agent usage patterns exist.
- **This is not "production ready."** It is a tested, correct deterministic layer with zero UI or LLM integration. Nothing in this report should be read as validating an end-to-end user-facing feature — that doesn't exist yet.
