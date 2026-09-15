# KKBox Retention Intelligence — Agent Architecture Plan

**Status:** Planning only. No project files were modified, deleted, or created other than this document.
**Date:** 2026-09-10
**Scope:** Architecture proposal for turning the existing 6-page dashboard + Retention Copilot into an agentic Retention Operations Assistant. Nothing in this document has been implemented.

---

## A. Current architecture summary

**App shell.** `dashboard/app.py` defines six pages via `st.Page(...)` and routes them through `st.navigation([...], position="top")` — a native Streamlit top-nav, no sidebar, no custom JS. Each page script calls `theme.apply_page_style()` itself (content emitted in `app.py` before `nav.run()` was found early in this project to not reliably render, so every page is self-contained).

**Pages** (`dashboard/pages/*.py`), each answering one manager question:
1. `overview.py` — "Where should KKBox act?" — risk×value field visualization, top opportunity, Champions callout.
2. `priority_customers.py` — "Who should we save?" — a ranked, filterable work-queue table (search + risk/value/segment `st.multiselect` filters, all **local, unkeyed widgets** — not addressable from another page yet).
3. `customer_value.py` — "Who is worth saving?" — risk×value bubble field, HH-cell callout.
4. `action_center.py` — "What should we do?" — ranked intervention queue by segment.
5. `customer_360.py` — "What should we do for this customer?" — search/filter → row-select → full profile (evidence, action, avoid) → "Ask Retention Copilot →" CTA.
6. `retention_copilot.py` — "Why / how / what next?" — grounded, mostly-deterministic Q&A for one customer or one segment (built two sessions ago; see full description below).

**Shared library** (`dashboard/lib/`):
- `data.py` — the single read layer over `outputs/*.csv` / `outputs/*.json`. 13 loader functions (`st.cache_data`), each `_require()`-guarded against a missing file; plus derived-metric helpers (`total_realized_revenue`, `high_risk_historical_revenue_exposure`, `priority_opportunities`, `customers_requiring_intervention`, `highest_value_segment`, `high_value_customer_count`), segment-copy dicts (`SHORT_ACTION_BY_SEGMENT`, `SHORT_WHY_BY_SEGMENT`, `AVOID_BY_SEGMENT`), `feature_display_name()`, and `key_risk_signal()`.
- `copilot_data.py` — deterministic, exact-ID retrieval for the Copilot: `get_customer_context()`, `get_population_baselines()`, `get_segment_context()`, `get_champions_context()`, `get_top_drivers()`. Returns small structured dicts, never a dataframe.
- `copilot_engine.py` — evidence-bundle assembly, all deterministic answer templates (`deterministic_customer_answer`, `deterministic_segment_answer`), keyword-based intent classifiers (`classify_customer_intent`, `classify_segment_intent`), the LLM system prompt + strict structured-response parser (`_parse_llm_response`), and the two public entrypoints (`answer_customer_question`, `answer_segment_question`).
- `llm_provider.py` — the **only** file that imports the `anthropic` SDK. `is_configured()` / `complete()`. Any failure (no key, no package, network, bad response) raises one caught exception type (`ProviderUnavailable`); never propagates to a page.
- `components.py` — `recommendation_block`, `secondary_story`, `copilot_answer_block` (renders a `CopilotAnswer` in the fixed RECOMMENDATION/WHY/EVIDENCE/WHAT TO DO/WHAT TO AVOID/CONFIDENCE-BASIS/CAUTION structure, with a transparency line when AI synthesis wasn't used).
- `theme.py` — the whole visual system: CSS injection, a shared Plotly template (one axis/legend/gridline style for every chart in the app), typography/spacing primitives, currency formatting (`fmt_currency`, `to_inr`/`from_inr` — fixed-rate NT$→₹ display conversion only), and micro-interaction CSS.
- `caveats.py` — curated, already-validated methodology text (calibration, temporal validation, HRR definition, revenue-exposure definition, threshold rationale, causality) rendered in a "Methodology & limitations" expander on relevant pages.

**Analytical pipeline** (upstream of the dashboard, not touched by it): `notebooks/01_eda.ipynb` → `12_error_analysis.ipynb` produce every file the dashboard reads. `src/` (`build_dataset.py`, `members_features.py`, `transactions_features.py`, `config.py`) is the feature-engineering pipeline behind those notebooks — cutoff-guarded to `2017-02-28` (`src/config.py: CUTOFF_DATE`). `models/` holds trained artifacts (XGBoost, random forest, logistic baselines, calibration diagnostics); the dashboard reads only `models/model_comparison_final.csv`, never a `.joblib` file directly.

**Session-state cross-page pattern** (the one mechanism that already lets pages talk to each other): `st.session_state["cust360_search"]` is set by Priority Customers on row-select and read by Customer 360 and Retention Copilot as a widget's `value=` (not `key=`, to sidestep a documented Streamlit widget-hydration gap — see below). `st.session_state["lookup_loaded"]` gates the one-time load of the 971K-row customer table, shared across Customer 360 and Retention Copilot.

**Existing tests and validation infrastructure.** There is **no formal pytest suite in the repo** — `find . -iname "test_*.py"` returns nothing. Validation has instead been done, every pass, via: (1) ephemeral `streamlit.testing.v1.AppTest` scripts and a deterministic offline assertion script (`scratchpad/test_copilot.py`, 34 assertions) kept in Claude's scratchpad, not committed; (2) a live browser walkthrough via `claude-in-chrome` on a freshly restarted server; (3) a written validation report per pass under `test_cases/*.md`. This is a real gap for a 3-day build — see §L and §M.

## B. Existing capabilities we can reuse directly (no rebuild)

- **All 13 `data.py` loaders** and its derived-metric functions — the aggregate-metrics tool layer is largely already written, just not exposed as agent-callable functions.
- **`copilot_data.py`'s exact-match retrieval discipline** — customer lookup is `df[df["msno"] == msno]`, never fuzzy/semantic; segment lookup joins `marketing_action_plan.csv` (all 7 segments) with `segment_summary.csv` (6 of 7 — Stable/Monitor absent, already handled as "not available," never guessed).
- **`copilot_engine.py`'s whole guardrail pattern**: evidence-bundle-only LLM input, fixed terminology enforcement in the system prompt, a strict parser that rejects any LLM response missing a required section (falls back to deterministic), and — as of the latest fix — a visible `llm_unavailable_reason` on every fallback answer instead of a silent one.
- **`llm_provider.py`'s provider isolation** — extend, don't replace, when adding tool-use.
- **`components.copilot_answer_block`** for single-customer/segment answers.
- **The session-state deep-link pattern** (`cust360_search`) — proven twice (Priority Customers→Customer 360, Customer 360→Copilot) and the exact model to generalize for agent-driven navigation.
- **The validation pattern itself** (offline assertions + AppTest + live browser + written report) — reuse the shape, not the specific scripts.

## C. Proposed agent architecture

```
Manager's question (typed free text, or a preset button)
        |
        v
   Router
   - Deterministic keyword classifier (already exists: classify_customer_intent /
     classify_segment_intent) tries first for the known question shapes.
   - If an LLM provider is configured AND the question doesn't cleanly match a known
     intent, ask the LLM to pick ONE tool + structured arguments (Anthropic tool-use /
     function-calling — not free-form prompting that the app then tries to parse).
        |
        v
   Tool execution (deterministic Python only, §D)
   - Every tool is a plain function over an already-loaded, already-cached dataframe or
     small JSON file. No tool ever calls the LLM. No tool ever writes anything.
   - Every tool result includes a `source` field naming the exact file/function it came
     from (extends the existing SOURCE_* constants in copilot_engine.py).
        |
        v
   Result shaping
   - List-shaped results (customer search, top-N) -> a compact dataframe, capped at a
     fixed row limit, columns pre-selected -- never the full 971K-row frame, never sent
     to an LLM in full.
   - Single-entity results (one customer, one segment, one aggregate number) -> the
     existing structured evidence-bundle shape copilot_engine.py already uses.
        |
        v
   Optional LLM synthesis (same guardrails as today, extended to tool results)
   - If configured: narrate the structured result in business language, under the same
     strict system prompt (fixed terminology, no causal language, cite only given facts).
   - If not configured, or the call/parse fails: render the structured result directly --
     a table stays a table, an evidence bundle renders through copilot_answer_block.
     Never blocked, never silently degraded (per the transparency fix already shipped).
        |
        v
   UI render
   - Table -> st.dataframe with row-select, matching Priority Customers' existing pattern.
   - Single answer -> components.copilot_answer_block (existing).
   - Navigation intent -> a deep-link CTA (st.page_link) into the relevant page,
     pre-filtered via the generalized session-state pattern (§H).
```

The critical design constraint: **the LLM's only job is (1) picking a tool + arguments, and (2) optionally narrating an already-computed, already-correct result.** It is never asked to compute a number, remember a fact across turns, or produce a customer-list itself. This is a direct extension of what `copilot_engine.py` already does for the two intents it currently supports — this plan generalizes that pattern from "answer one templated question about one customer/segment" to "call one of N tools with structured arguments."

## D. Exact recommended tool list

All tools operate on data already loaded via `data.py`'s cached loaders — no new file I/O, no new dataset. "Exists" = the retrieval logic is already written somewhere in the codebase and needs extraction/generalization into a standalone callable; "New" = genuinely new code.

| # | Tool name | Status | Purpose | Inputs | Outputs | Source of truth |
|---|---|---|---|---|---|---|
| 1 | `search_customers` | **New** (logic exists inline in `priority_customers.py` / `customer_360.py`, never extracted as a reusable function) | Answers "top 20 high-risk high-value," "customers we should worry about," "safe customers for upsell," "high-risk customers with significant revenue" | `risk_tier: list[str] \| None`, `value_tier: list[str] \| None`, `segment: list[str] \| None`, `min_hrr_ntd: float \| None`, `sort_by: Literal["risk_score_full","calibrated_probability","total_revenue"]`, `limit: int` (capped, e.g. 50) | List of compact dicts: `msno, risk_tier, value_tier, segment, calibrated_probability, risk_score_full, total_revenue` | `data.load_customer_lookup_data()` (same cached frame every page already uses) |
| 2 | `get_customer` | **Exists** — `copilot_data.get_customer_context()` | "Why is customer X at risk," "what should we do about customer X" — single-customer facts | `msno: str` (exact match only) | Structured dict or `None` | `outputs/customer_segments.csv` + `risk_scoring_predictions.csv` + `customer_value_tiers.csv` + `calibrated_probabilities.csv` (the same merge `load_customer_lookup_data()` does) |
| 3 | `explain_customer_risk` | **Exists** — `copilot_engine.deterministic_customer_answer("why_at_risk", ...)` + `copilot_data.get_top_drivers()` | "Explain why this customer is high risk" | `msno: str` | Recommendation/why/evidence bundle citing the customer's own values + the model's top global SHAP drivers | `outputs/shap_feature_importance.csv` + customer context |
| 4 | `recommend_action` | **Exists** — `copilot_engine.deterministic_customer_answer("what_to_do", ...)` | "What should we do about customer X" | `msno: str` | `objective, intervention_intensity, why, what_to_avoid` | `outputs/marketing_action_plan.csv` + `data.SHORT_WHY_BY_SEGMENT` / `AVOID_BY_SEGMENT` |
| 5 | `get_segment` | **Exists** — `copilot_data.get_segment_context()` | "Which segment needs attention," "tell me about segment X" | `segment: str` (one of the 7 validated names) | Segment stats dict, with behavioral medians explicitly `None` when absent (Stable/Monitor) | `outputs/marketing_action_plan.csv` + `outputs/segment_summary.csv` |
| 6 | `rank_segments_by_priority` | **Exists**, inline only — `copilot_engine.deterministic_segment_answer("which_segment_priority", ...)` and `data.priority_opportunities()` | "Which segment should we prioritize" | `top_n: int \| None` | Segments ranked by Historical Realized Revenue at stake, excluding Champions/Stable | `outputs/marketing_action_plan.csv` |
| 7 | `get_aggregate_metrics` | **New** (thin wrapper; every underlying number already exists as a function) | "How many customers are at elevated risk," base-rate questions | none, or `tier: str \| None` | `n_customers_scored, overall_churn_rate, n_by_tier, realized_revenue_base, high_risk_revenue_exposure` | `outputs/risk_scoring_summary.json` via `data.load_risk_summary`, `data.total_realized_revenue`, `data.high_risk_historical_revenue_exposure`, `data.customers_requiring_intervention` |
| 8 | `compare_to_champions` | **Exists** — `copilot_data.get_champions_context()` + `copilot_engine`'s `"compare_champions"` intent | "How does this customer compare with Champions" | `msno: str` | Comparison dict | `outputs/marketing_action_plan.csv` + `outputs/value_by_segment.csv` |
| 9 | `build_dashboard_deep_link` | **New** | "Take me to the customers matching this query" / any navigation intent | `target_page: Literal["priority_customers","customer_360","action_center","customer_value"]`, `filters: dict` (risk_tier/value_tier/segment/msno as applicable) | A session-state payload + `st.page_link` target the UI layer applies before rendering the CTA | Not a data source — pure UI-state plumbing (§H) |

Two tools are explicitly **not** included: no "predict for a new customer" tool (the model only scores customers already in the scored base — there is no live scoring path in this project) and no "send campaign" / write-back tool (§K).

## E. What should be deterministic vs. LLM-generated

**Always deterministic, never delegated to the LLM:**
- Every number shown anywhere (counts, percentages, currency, scores). A tool computes it; the LLM may only repeat it verbatim.
- Which customer a `msno` resolves to (exact-match only, per §F).
- Segment definitions, the action-framework mapping, and terminology (Model Risk Score / Estimated Churn Probability / HRR / High-Risk Historical Revenue Exposure — §below).
- The guardrail/caution text.
- The fallback path when no LLM is configured or a call fails (already built; extend, don't rebuild).

**LLM's job, and only this:**
- Map a free-text question to one tool + its arguments (intent + slot-filling), when the existing keyword classifier doesn't already confidently match.
- Narrate an already-computed structured result into a short business-language paragraph, under the existing strict system prompt.
- Nothing else. No multi-step autonomous planning, no chaining of more than one tool call per turn in the initial build (§J, §K).

## F. How customer-level grounding should work

Extend the exact pattern `copilot_data.py` already established, unchanged in spirit:
1. Customer identity is resolved by **exact `msno` equality**, never substring/fuzzy/semantic search, for any tool that targets one customer. (`search_customers`, the one tool that legitimately filters/ranks many customers, uses column-value filtering — still deterministic, still never invents a row.)
2. A tool that finds nothing returns `None` / an empty list — the router renders the existing required message ("I couldn't find that customer in the scored customer base.") — never a guess.
3. Every field in a tool's output dict is a real column from a named source file; a field that's genuinely unavailable (e.g., `discount_rate` missing, or a segment absent from `segment_summary.csv`) is `None` and rendered as "not available," per the `_fmt_rate()` fix already shipped — never silently defaulted to 0 or omitted without explanation.
4. The LLM is handed the tool's **output dict**, never the source dataframe, never another customer's data, never chat history containing another customer's facts (the stale-context bug fixed in the last Copilot pass is the concrete precedent for why this matters — context must be cleared on every customer/segment switch).

## G. How the agent should handle unsupported questions

Reuse, don't reinvent, the three-tier failure language already established in `copilot_engine.py`:
- **No matching customer/segment:** the existing exact required strings ("I couldn't find that customer in the scored customer base.").
- **No matching tool / ambiguous intent:** the existing "unknown" intent clarification message pattern ("I can answer questions about X, Y, Z — try rephrasing"), extended to name the new tool categories.
- **A field needed to answer isn't in the evidence bundle:** "Insufficient evidence in the available customer data" (customer) / "not available for this segment" (segment) — already the system prompt's explicit instruction, already enforced by the deterministic templates.

A question that would require a tool this project doesn't have (e.g., "will this customer actually renew if we call them") must get the same honest refusal already used for "what happens if we do nothing" — no causal forecast, no invented capability.

## H. How the agent should hand users into existing dashboard pages

Generalize the `cust360_search` pattern rather than inventing a new mechanism:
1. Add a small number of **named, keyed** session-state slots that pages read on load if present — e.g., `st.session_state["priority_customers_pending_filter"] = {"risk_tier": ["High"], "value_tier": ["High"], "sort_by": "total_revenue"}`. This requires converting Priority Customers' currently-unkeyed `st.multiselect` filters to keyed widgets that read an initial `value=` sourced from this slot (the exact same `value=` vs. `key=` fix already applied to `cust360_search` to work around the Streamlit widget-hydration gap documented in the Master Restructure report).
2. `build_dashboard_deep_link` (§D) writes to the appropriate slot and returns a ready-made `st.page_link(...)` the UI renders as a CTA, e.g. "Open these 14 customers in Priority Customers →" — matching the exact visual/interaction pattern already proven for the two existing cross-page CTAs.
3. Consume the slot **once** on the target page (pop it after reading) so a manually-cleared filter on that page doesn't keep getting silently overridden.

## I. Recommended frontend experience

**Do not add a 7th page.** Retention Copilot already owns "ask a question about this customer/segment"; the agentic layer is a natural extension of that page, not a separate surface. Concretely:
- Keep the existing customer-mode / segment-mode split and their preset question buttons unchanged.
- Add one more mode, entered automatically when a question doesn't resolve to a single customer or segment: **query mode** — the free-text box already on the page, now also routable to `search_customers` / `get_aggregate_metrics` / `rank_segments_by_priority`. Results render as a table (Priority-Customers-style, row-selectable) above a one-line CTA ("Open in Priority Customers →") when the result is a customer list; as `copilot_answer_block` when it's a single fact or ranking.
- This is a genuinely small UI change: the page already has the free-text input and the answer-rendering component; it needs a table-rendering branch and the new deep-link CTA, not a redesign.

## J. Minimal implementation scope for a 3-day build

- **Day 1 — deterministic tool layer (no LLM changes yet).** Extract `search_customers` and `get_aggregate_metrics` as real functions in `copilot_data.py`; extract `rank_segments_by_priority` out of `copilot_engine.py`'s inline branch into a standalone, directly-testable function. Write offline tests for all three (exact-value assertions, same style as the existing 34-test suite) before touching the UI at all.
- **Day 2 — routing + LLM tool-use.** Extend `llm_provider.py` with a tool-use-capable `complete_with_tools()` (Anthropic tool-use / function-calling), keeping `complete()` and every existing guardrail untouched. Wire the router: try the existing keyword classifiers first; fall back to LLM tool-selection only if configured and no keyword match. No LLM key exists in this environment today, so this path needs `ANTHROPIC_API_KEY` before it can be live-tested end-to-end — document that honestly rather than claiming a test that didn't happen (same discipline as the last Copilot report).
- **Day 3 — UI + deep-links + validation.** Add query mode to `retention_copilot.py` (table rendering + CTA), generalize the session-state deep-link slot for Priority Customers, re-run the full offline suite + AppTest + a live browser walkthrough of every example question in the brief, write the validation report.

Everything beyond this (multi-step tool chaining, conversational memory, additional tools) is explicitly out of scope for the 3-day build.

## K. What NOT to build

- No vector database / RAG over the 971K customer rows — already decided against in the prior Copilot pass, still correct; exact-match + structured filtering covers every example question in the brief.
- No multi-turn conversational memory persisted across questions or across sessions — each question resolves independently from the current customer/segment context, exactly as today.
- No write-back / action-taking tools (sending a campaign, changing a record, exporting to a CRM) — this is a read-only intelligence layer over an already-validated analytical pipeline, not an execution system.
- No new model training, no new thresholds, no new segment definitions — the agent orchestrates the existing engine, it does not extend it.
- No autonomous multi-step planning (the LLM chaining several tool calls on its own before responding) in the initial build — one tool call per question keeps behavior predictable and testable; revisit only if a real question in practice genuinely needs it.
- No generic open-domain chatbot behavior — a question outside the tool set gets the existing honest refusal, never a best-effort freeform answer.
- No renaming or reinterpreting Model Risk Score, Estimated Churn Probability, HRR, or High-Risk Historical Revenue Exposure (see below) — the agent must use the same four terms with the same meanings everywhere it narrates a result.

## L. Risks / failure modes

- **LLM picks the wrong tool or hallucinates an argument** (e.g., fabricates a `msno` that looks plausible). Mitigation: exact-match lookup already returns `None`/empty for anything not genuinely present — a hallucinated ID simply produces the existing "not found" message, never fabricated data. This is the single most important property to preserve.
- **Ambiguous questions route inconsistently between the keyword classifier and LLM tool-selection**, producing different answers to near-identical phrasings across sessions (with vs. without a key configured). Mitigation: always try the deterministic classifier first; only escalate to the LLM when it doesn't match; log/surface which path was used (extend the existing `used_llm` / `llm_unavailable_reason` fields to cover tool-selection, not just synthesis).
- **Large result sets balloon LLM token usage or leak more customer detail into the prompt than needed.** Mitigation: `search_customers` is capped (e.g. 50 rows) and pre-projected to a fixed small column set before it's ever eligible for LLM narration; the same discipline already applied to the single-customer evidence bundle.
- **Terminology drift during LLM narration** (calling Model Risk Score a probability, calling HRR a lifetime value, implying causality). Mitigation: same system-prompt rules and strict parser already built and tested (34/34) for the existing two intents — apply unchanged to tool-result narration, not a new set of rules.
- **No formal test suite exists in the repo** — every validation pass to date has lived in an ephemeral scratchpad script. For a feature this central (an agent that can be asked almost anything), that's a real risk of regressions going undetected between sessions. Mitigation: this build should be the one that finally commits a real test file into `dashboard/` (or a top-level `tests/`) rather than continuing the scratchpad pattern — flagged here as a recommendation, not yet acted on.
- **The `st.multiselect` deep-link generalization (§H) repeats a known Streamlit gotcha** (value=/key= widget-hydration gap) — must follow the exact same `value=` sourcing pattern already proven for `cust360_search`, not the naive `key=`-only approach that silently failed twice already this project.
- **No `ANTHROPIC_API_KEY` currently exists in this environment.** Every LLM-dependent piece of this plan (tool-selection, narration) can be built and unit-tested for its fallback path, but not live-tested end-to-end with a real completion until a key is configured — same honest limitation already documented for the existing Copilot.

## M. Recommended implementation order

1. Extract `search_customers`, `get_aggregate_metrics`, `rank_segments_by_priority` as standalone, tested functions — no UI, no LLM changes.
2. Add offline tests for all three (exact-value assertions against the real output files, same style as the existing 34-test suite) — this is the point where a real test file should finally land in the repo instead of the scratchpad.
3. Generalize the session-state deep-link slot pattern for one page (Priority Customers) and prove it end-to-end with a manual CTA before wiring the LLM to it.
4. Extend `llm_provider.py` with tool-use support, behind the same `is_configured()` gate, with the same silent-failure-is-never-allowed discipline as the transparency fix already shipped.
5. Wire the router (keyword-first, LLM-fallback) and the three new tools into `retention_copilot.py`'s existing free-text path.
6. Add table rendering + CTA to the Copilot page for list-shaped results.
7. Full validation pass: offline suite, AppTest, live browser walkthrough of every example question in the brief, written report — and only then consider promoting any tracker status.

---

## Terminology — explicitly preserved, not reinterpreted

| Term | What it is | Column / source | What it is NOT |
|---|---|---|---|
| **Model Risk Score** | Raw XGBoost `predict_proba` output | `risk_score_full` in `outputs/risk_scoring_predictions.csv` | Not a probability — inflated by `scale_pos_weight` class-imbalance correction during training; ranking-only |
| **Estimated Churn Probability** | The calibrated figure | `calibrated_probability` in `outputs/calibrated_probabilities.csv` (notebook `10_probability_calibration.ipynb`) | The only one of these four safe to read as a literal probability |
| **Historical Realized Revenue (HRR)** | Money already collected from a customer | `total_revenue` in `outputs/customer_value_tiers.csv` | Not CLV, not Lifetime Value, not a Future Revenue forecast — no projection, no discounting |
| **High-Risk Historical Revenue Exposure** | Sum of HRR held by customers in the High risk tier, each counted at 100% weight | `data.high_risk_historical_revenue_exposure()` over `outputs/risk_value_matrix.csv` | Not a probability-weighted expected loss (`P(churn) × revenue`) — a headcount exposure sum |

Every tool in §D that returns one of these four values must label it with its exact name above, in every UI surface and every LLM-narrated sentence — no exceptions, no synonyms.
