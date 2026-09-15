# P1-11 Validation Report — Structured Decision Answers

**Tracker row:** `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, ID `P1-11`, Stage "UX / AI", Priority P1.
**Status change:** `TODO` → `REVIEW` (this report; not `DONE` — reserved for independent sign-off).

## 1. Exact requirement from the tracker

**Issue:** "The strongest differentiator — grounded decision support — should be visually obvious."

**Claude Fix Prompt:** "Present responses as Finding → Evidence → Why it matters → Recommended action → Confidence/limitations → Next step where applicable. Use existing structured tool results and deterministic answer path. Do not re-query, invent facts, claim causality, or call Model Risk Score a probability. Keep customer/cohort links working."

**Acceptance Criteria:** "Evidence and action are distinct; uncertainty is honest; terminology guardrails remain; next-step links work; representative edge cases pass."

## 2. Interpretation

Before touching code, I audited `agent.py`, `copilot_engine.py`, `components.py`, `agent_tools.py`, and `retention_copilot.py` to establish what structure each of Retention Intelligence's answer types *already* had, rather than assuming a blank slate:

| Answer type | Formatter | Pre-P1-11 structure |
|---|---|---|
| Customer / Segment | `agent._render_copilot_answer` (wraps `copilot_engine.CopilotAnswer`) | Recommendation → Why → Evidence → What to do → What to avoid → Confidence/basis → Caution |
| Aggregate ("how many at elevated risk") | `agent._format_aggregate_answer` | Headline → 4 stat lines → Recommended next step (P1-10) |
| Segment ranking ("which segment needs attention") | `agent._format_rank_segments_answer` | Headline (with the action folded into the same sentence) → Also worth attention → Recommended next step (P1-10) |
| Search list ("contact first" / "high-risk high-value") | `agent._format_search_customers_answer` | Headline → Result summary → Recommended next step |

So every answer type already had *some* structure (from Tasks 06/P1-10), but none had a genuine, distinct "Why it matters" / "Recommended action" / "Confidence/limitations" split — evidence, interpretation, and action were frequently fused into one sentence (most visibly in the rank-segments Headline, which embedded `"Recommended: {action}."` directly in the Finding line — exactly what the acceptance criterion "evidence and action are distinct" calls out). P1-11's job was to fix that fusion and fill the two genuinely missing sections (Why it matters, Confidence/limitations) — not to invent a new answer-rendering system.

I determined, per answer type, which of the six sections are genuinely supported by existing data (see §5) and omitted the rest rather than manufacturing content — most notably, the aggregate ("how many customers at elevated risk") answer has no single "Recommended action" (the action framework operates at segment/customer level), so that section is absent from it entirely.

## 3. Files changed

- `dashboard/lib/agent.py` — reordered/restructured all four deterministic answer formatters (`_render_copilot_answer`, `_format_aggregate_answer`, `_format_rank_segments_answer`, `_format_search_customers_answer`); rewrote the LLM system prompt's "Answer structure" section to describe the same six-part structure for the (currently unreachable, no-API-key) LLM path.
- `dashboard/lib/components.py` — added `"confidence/limitations"` to `_MUTED_LABELS` (one line), so the new merged Confidence/limitations line gets the same muted-caption treatment `Confidence/basis`/`Caution` already had.
- `tests/test_agent_orchestration.py` — updated one P1-10 test's line-count cap (a deliberate, documented consequence of splitting the action out of the Finding line); added 15 new P1-11 regression tests.
- `tests/test_retention_intelligence_ui.py` — updated one P1-09 test's boundary marker (the "not an expected loss" phrase moved from a markdown line into the new muted Confidence/limitations caption); added 6 new P1-11 regression tests.

## 4. Files deliberately NOT changed

- `agent_tools.py`, `copilot_engine.py`, `copilot_data.py`, `data.py` — no tool result shape, evidence bundle, or business logic changed. Every fact used in the restructured answers already existed in these files' return values; P1-11 only reordered/relabeled how `agent.py` renders them.
- `retention_copilot.py` — the page's context strip, search/segment controls, suggested-prompt buttons, and the customer/segment link mechanisms are untouched. The only change reachable from this page is the text `agent.ask()` returns.
- `notebooks/`, `models/`, `outputs/`, `src/` — confirmed untouched (`find notebooks models outputs src -newermt "2026-09-11 16:30:00"` → 0 files).
- `components.copilot_answer_block` — a pre-existing, currently-unused function (referenced only in a docstring comment, called by no page or test). Left alone; restructuring it would be scope creep onto dead code.
- No calculation, threshold, segmentation, or revenue logic touched anywhere.

## 5. Implementation summary — per answer type, what changed and why

**Customer & segment answers (`_render_copilot_answer`).** Reordered from `Recommendation → Why → Evidence → What to do → What to avoid → Confidence/basis → Caution` to `Recommendation(Finding) → Evidence → Why it matters(Why) → Recommended action(What to do) → Avoid(What to avoid) → Confidence/limitations(Confidence/basis + Caution merged)`. Every field already existed on `CopilotAnswer`; only the emission order and two labels changed ("Why:" → "Why it matters:", "What to do:" → "Recommended action:"; "Confidence/basis:" and "Caution:" merged into one "Confidence/limitations:" line). **No "Next step" line was added here** — this is a deliberate, documented decision (see the docstring on `_render_copilot_answer` and the dedicated regression test `test_customer_and_segment_answers_have_no_manufactured_next_step_line`): the genuinely applicable next step for a customer or segment answer — "Open full profile in Customer 360" / "View {segment} customers in Priority Customers" — is already a persistent, always-visible link rendered directly above every answer on this page (`retention_copilot.py`'s `context_slot`). Repeating it as a text line inside the answer body would point to no new destination; the task's own instruction ("where applicable" / "do not manufacture empty sections") argues directly against duplicating it.

**Aggregate answer (`_format_aggregate_answer`).** Added two new sections between the existing stat lines and the existing "Recommended next step" line: a "Why it matters" line computing the high-risk population's share of the base (by count) and its share of total realized revenue — both are simple ratios of numbers already present in the same tool result (`agent_tools.get_aggregate_metrics`), not a new query or an invented fact, and worded as a neutral comparison rather than asserting a direction, since which way the ratio falls is itself a fact this function must not assume — and a "Confidence/limitations" line stating the exposure-figure caveat (moved out of the stat line it used to be appended to) plus the Model Risk Score guardrail. **No "Recommended action" section** — a business-wide aggregate question has no single action in the action framework; that section is genuinely not applicable and is omitted rather than manufactured.

**Segment-ranking answer (`_format_rank_segments_answer`).** The recommended action — previously folded into the same sentence as the Finding ("...₹525.22M at stake. Recommended: Re-engage.") — is now its own "Recommended action:" line, directly satisfying "evidence and action are distinct." Added "Why it matters" (reusing, verbatim in spirit, the exact justification `copilot_engine.deterministic_segment_answer`'s `which_segment_priority` branch already gives for this same ranking — not a new interpretation invented for this formatter) and "Confidence/limitations" (this ranking is realized revenue, not a churn-prevention forecast).

**Search-list answers (`_format_search_customers_answer`, used by "Who should we contact first?" and "Show me high-risk, high-value customers.").** Added a "Why it matters" line (why this filter combination was chosen — a real, grounded reason per call site, not generic filler), a "Recommended action" line, and a "Confidence/limitations" line. The "Recommended action" line deliberately does **not** state a single action — a result list can span multiple segments with different recommended treatments — it instead points at each row's own `recommended_action` field, which `components.priority_list` already renders per customer in the table directly below the answer. Stating one combined action would either be wrong for some rows or would silently re-derive something already present in the tool result, both of which the task explicitly prohibits.

**LLM system prompt (`agent._SYSTEM_PROMPT`).** The "Answer structure" paragraph (previously three separate per-question-type templates) was rewritten into one explicit six-part structure matching the deterministic formatters above, with an explicit instruction to skip a section rather than manufacture one. This path is not reachable in this environment (no `ANTHROPIC_API_KEY`) and so could not be live-tested end-to-end, but keeping it consistent with the deterministic path is required so the two paths don't diverge in structure if a key is added later. RULE 1–11 and the Terminology section were left byte-identical (verified by test).

## 6. Tests added

**`tests/test_agent_orchestration.py`** — 15 new tests: customer and segment answers follow the six-part order (`Recommendation < Evidence < Why it matters < Recommended action < Confidence/limitations`, via `str.index`); customer/segment answers carry no manufactured "Next step" line; the aggregate answer's Why-it-matters/Confidence-limitations/Recommended-next-step ordering, and that it has no "Recommended action:" section; the rank-segments answer keeps the action out of the Finding line; both search-list answer variants (contact-first, high-risk-high-value) have the full ordering and preserve their existing headline substrings ("contact first" / "priority zone"); the search-list "Recommended action" points at the per-row data, not an invented single action; a terminology guardrail scanning all restructured answers for any phrase mislabeling Model Risk Score as a probability; a causal-language guardrail scanning the same answers for banned phrases; a regression proving the search-customers → Customer 360 handoff data is untouched; the system prompt states the new six-part structure; the system prompt's RULE 1–11 and Terminology block are byte-identical to before; and the tool dispatch table is unaffected.

**`tests/test_retention_intelligence_ui.py`** — 6 new tests, exercised via `AppTest` against the real page: the Confidence/limitations line renders in the muted caption tier (not the main markdown flow); the aggregate answer's Why-it-matters/Recommended-next-step ordering renders correctly on the live page; the segment answer's full structure (Finding styling, Evidence/Why-it-matters/Recommended-action bold-label lines, Confidence/limitations caption) renders in the correct order, and the segment's "View ... in Priority Customers" link is still present; the search-customer answer's structure renders and the priority list with its "Open →" handoffs still works; a source-level regression confirming every cross-page link mechanism (Customer 360 page_link, `pending_filter`, `cust360_search`) is untouched.

**One existing test updated per this project's established practice** (update, don't weaken, when a test fails because behavior genuinely improved): `test_rank_segments_answer_caps_prose_and_points_to_action_center`'s line-count cap moved from 3 to 6 lines, with a comment explaining this is the direct, intended consequence of splitting the action out of the Finding line. `test_identity_change_did_not_alter_grounded_answer_content`'s currency-check boundary marker moved from `"not an expected loss"` (now inside a caption, no longer in `at.markdown` output) to the end of the answer's last markdown-rendered line, preserving the test's original intent (scope the "no raw NT$" check to the answer, not the page's own currency disclosure) under the new rendering.

## 7. Complete test results (this run, fresh)

```
tests/test_agent_tools.py               40 passed, 0 failed
tests/test_agent_orchestration.py       70 passed, 0 failed   (56 pre-existing + 14 new P1-11)
tests/test_retention_intelligence_ui.py 44 passed, 0 failed   (38 pre-existing + 6 new P1-11)
tests/test_manager_workflow.py           8 passed, 0 failed
tests/test_information_density.py        7 passed, 0 failed
----------------------------------------------------------------
TOTAL                                   169 passed, 0 failed
```

All P1-07/08/09/10 tests still pass, unmodified except the two documented, deliberate updates in §6.

## 8. Live browser validation

Fresh Streamlit server started on port 8691 (a different port from any prior session's server, to guarantee a clean process). `ANTHROPIC_API_KEY` confirmed absent (`'ANTHROPIC_API_KEY' in os.environ` → `False`). Startup log clean, no import errors.

- **Aggregate answer** (`/retention_copilot`, "How many customers are at elevated risk?"): screenshot confirmed the exact designed hierarchy — bold/large Finding ("970,960 customers scored, 9.0% overall churn rate."), the four stat lines, a bold "Why it matters:" line ("High-risk customers are 2.3% of the scored base by count and hold 1.7% of total realized revenue — the 2,413 customers who are both High risk and High value..."), a visibly muted/greyed "Confidence/limitations:" caption line, and a bold "Recommended next step:" line — all in that order.
- **Segment-ranking answer** ("Which segment needs attention?"): confirmed the Finding line no longer contains the recommended action ("At-Risk, Auto-Renew Off is the top retention priority — 113,820 customers, 41.1% churn, ₹525.22M at stake."), followed by "Also worth attention:", a separate bold "Recommended action: Re-engage." line, "Why it matters:" (reusing the existing ranking justification), and the muted "Confidence/limitations:" caption.
- **Search-list answer** ("Who should we contact first?", customer data loaded): confirmed the full structure (Headline → Result summary → Why it matters → Recommended action → muted Confidence/limitations → Recommended next step), and that the priority list of real customer rows with "Open →" handoffs still renders immediately below, unaffected.
- **Customer-360 → Retention Intelligence → back handoff, end to end**: clicked "Open →" on a search-list row → landed on Customer 360 with the customer pre-selected (the exact `cust360_search` mechanism) → selected the row to open the profile → clicked "Ask Retention Intelligence about this customer →" → landed back on Retention Intelligence with the same customer already in focus → clicked "Why is this customer at risk?" → confirmed the customer answer's full six-part structure rendered correctly: bold Finding ("Key risk signal: Inactive 30+ days."), "**Evidence:**" line (Risk tier, Model Risk Score, Estimated Churn Probability, Value tier, Segment, Auto-renew, Recency, Cancellation/Discount rate vs. base averages), "**Why it matters:**", "**Recommended action:** Monitor only", "**Avoid:** Avoid proactive outreach...", and the muted "Confidence/limitations:" caption explicitly stating "Model Risk Score is not a calibrated probability; Estimated Churn Probability is the calibrated figure and is what's used above." No "Next step" line present, as designed.

## 9. No-API-key validation

Confirmed via the automated suite (`test_no_api_key_in_this_environment`, and every P1-11 test exercises the real `agent.ask(...)` deterministic-fallback path with no key present) and via live browser interaction (the `[AI synthesis unavailable: no AI provider is configured for this session — showing the grounded deterministic answer]` banner, and the "Deterministic answer — AI synthesis not used" caption, observed on every answer type tested in §8).

## 10. Terminology / causality guardrail checks

- Verified live: the customer answer's Confidence/limitations line states "Model Risk Score is not a calibrated probability; Estimated Churn Probability is the calibrated figure" — for a customer where Model Risk Score (1.00) and Estimated Churn Probability (100%) happen to coincide numerically, the two are still never conflated in the rendered text.
- `test_no_answer_mislabels_model_risk_score_as_a_probability` scans the actual restructured text of all six deterministic answer types (not just the system prompt) for any phrase equating Model Risk Score with a probability; all pass.
- `test_why_it_matters_and_evidence_never_use_causal_language` scans the same answers for banned causal phrases ("this caused", "causes churn", "will reduce churn", "guarantees", "will save").
- Terminology distinctions (Model Risk Score / Estimated Churn Probability / HRR / High-Risk Historical Revenue Exposure) are never renamed or reinterpreted — P1-11 only reordered where existing, already-correct sentences using these terms appear in the answer, never rewrote the sentences' factual content.
- RULE 1–11 and the system prompt's Terminology section verified byte-identical to their pre-P1-11 text.

## 11. Link / handoff validation

- Source-level regression (`test_customer_360_and_priority_customers_source_level_links_unaffected_by_p1_11`, `test_search_customers_link_and_customer_360_handoff_unaffected_by_answer_restructure`): the Customer 360 `page_link`, the `pending_filter` segment-to-Priority-Customers mechanism, and the `cust360_search` / `st.switch_page` search-result handoff are all byte-identical to before P1-11.
- Live end-to-end validation in §8 walked the full loop: Retention Intelligence search-list result → Customer 360 → Retention Intelligence (customer context) → a customer-specific answer — every link fired correctly.
- Existing P1-07/08/09/10 link/handoff tests (Overview → Priority Customers, Action Center → Retention Intelligence, segment → Priority Customers, Priority Customers → Customer 360) all still pass unmodified.

## 12. UX / product rationale

The product's core differentiator is that every answer is grounded, evidence-first decision support — not a chatbot restating numbers. Before P1-11, that discipline existed in the *data* (every fact was already real and sourced) but not consistently in the *shape* of the answer: the rank-segments Finding line fused what happened with what to do about it, and neither the aggregate nor the search-list answers ever explained why the numbers mattered or stated their own limitations. Splitting Finding from Evidence from Interpretation from Action from Caveat from Next-step — using this project's own existing visual-tiering mechanism (`components.agent_response_block`'s Finding/Evidence/Confidence label matching, unchanged) rather than inventing a new one — makes the "grounded decision support" claim visually verifiable in seconds: the boldest text is always the finding, the greyest text is always the honest caveat, and the action is never hidden inside the headline sentence.

## 13. Known limitations

- The LLM system prompt's six-part structure could not be live-tested end-to-end (no `ANTHROPIC_API_KEY` in this environment) — only its presence and byte-identical guardrails were verified statically. If a provider is configured later, this should be spot-checked against a real response.
- Customer/segment answers deliberately have no per-answer "Next step" line (see §5's rationale) — if a future ticket removes or relocates the persistent context-strip link, this decision should be revisited.
- The aggregate answer's "Why it matters" percentage comparison is a simple, static two-number ratio; it does not adapt its wording to which direction the ratio falls (it is phrased as a neutral factual comparison specifically so it stays true either way), so it is not a general insight-generation mechanism — it is scoped exactly to this one aggregate question.
- The search-list answers' "Why it matters" text is written per call site (contact-first vs. high-risk-high-value), not derived generically from the filter arguments — a new search-shaped route added in a future ticket would need its own `why=` text, not fall back to a default.

## 14. Confirmation

P1-12 and all later tickets (P1-12 through P2-16) were **not** started or touched. Tracker verified via read-back: only the P1-11 row's Status cell will be changed, from `TODO` to `REVIEW`, immediately after this report is written.
