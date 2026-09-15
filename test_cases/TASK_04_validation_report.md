# Validation Report — Task 04: Retention Copilot as the Flagship AI Product Experience

**Status:** `dashboard/pages/retention_copilot.py` has been redesigned into "Retention
Intelligence," the flagship experience described in the task. `agent.ask()` (Task 03's
orchestrator) is wired directly into the UI — no separate answer path was built. All five other
pages remain functional and were touched only where explicitly permitted (a one-line link label
in `customer_360.py`, a small filter-prefill addition in `priority_customers.py`). Live browser
validation of the full manager workflow (Priority Customers -> Customer 360 -> Retention
Intelligence, customer-context Q&A, deterministic fallback, provenance) is complete.
**Date:** 2026-09-11

---

## 1. Files changed

| File | Change | Why |
|---|---|---|
| `dashboard/pages/retention_copilot.py` | **Rewritten.** New hero, context strip, adaptive suggested prompts, free-text question, empty state, and `agent.ask()`-backed answer rendering. | This task's primary deliverable. |
| `dashboard/lib/agent.py` | **Extended, not rewritten.** `ToolCallRecord` gained a `result: dict` field (the tool's full `{ok,data,error}` payload); new `get_tool_result(response, tool_name)` helper. All 5 construction sites updated. | The UI needs to render structured tool output (e.g. a customer list) without re-querying tools with guessed arguments; Task 03's `AgentResponse` deliberately didn't carry this. Backward-compatible (defaulted field), re-verified against all 29 existing Task 03 tests. |
| `dashboard/lib/theme.py` | **Additive.** New `.context-strip`, `.qa-question`, `.qa-question-text`, `.priority-row` CSS; new `context_strip()` function. | The "who am I grounded to" indicator and Q&A labels needed a home consistent with the existing design system; no existing rule or function was changed. |
| `dashboard/lib/components.py` | **Additive.** New `priority_list()` and `agent_response_block()` functions. | Structured, non-dataframe rendering of agent answers and customer-list results, per the task's explicit requirement. Existing functions (`recommendation_block`, `copilot_answer_block`, `secondary_story`) unchanged. |
| `dashboard/pages/priority_customers.py` | **Minimal, documented touch** (explicitly allowed by the task). Consumes `st.session_state["pending_filter"]` (a convention already anticipated in Task 02's `build_dashboard_deep_link` docstring) to pre-populate the risk/value/segment filters when arriving from a "View all matching customers" link. | Closes the deep-link loop from a Retention Intelligence customer-list answer to the full Priority Customers view. |
| `dashboard/pages/customer_360.py` | **One line.** `st.page_link` label changed from "Ask Retention Copilot about this customer →" to "Ask Retention Intelligence about this customer →". | Rebrand only, to match the renamed flagship page; the handoff mechanism itself (the `cust360_search`/context session-state pattern) is unchanged. |
| `tests/test_retention_intelligence_ui.py` | **New.** 15 tests covering empty state, suggested prompts, free text, customer context, segment context, aggregate queries, customer-list queries, navigation mechanism, Customer 360 handoff, deep-link generation, fallback mode, provenance, missing data, unknown customer, unsupported question. | Required deliverable (task's Testing section). |
| `test_cases/TASK_04_validation_report.md` | **New.** This report. | Required deliverable. |

**Not touched:** `notebooks/`, `models/`, `outputs/`, `src/` (confirmed via `find ... -newer` —
zero results), `dashboard/app.py`, `dashboard/lib/agent_tools.py`, `dashboard/lib/agent_tool_schemas.py`,
`dashboard/lib/llm_provider.py`, `dashboard/lib/copilot_engine.py`, `dashboard/lib/copilot_data.py`,
`dashboard/lib/data.py`, `dashboard/lib/caveats.py`, and `dashboard/pages/overview.py`,
`action_center.py`, `customer_value.py`. No new ML model, no invented metric, no LangChain/
LangGraph/vector database/RAG was introduced.

## 2. UI architecture

Retention Intelligence is a single-page flow with three conceptual areas, built entirely from
Streamlit-native primitives plus the existing `theme.py`/`components.py` system:

1. **Hero/context** — `theme.page_header("AI ASSISTANT", "Retention Intelligence", ...)` (reused,
   not re-invented), followed by a compact search box + segment selector, and — only once a
   customer or segment is in focus — `theme.context_strip()`, a thin tinted rule (not a card) that
   reads "Analysing customer `<id>`" with risk/value/segment badges, or "Segment in focus:
   `<name>`". A "customer wins over segment" precedence rule prevents ambiguous context.
2. **Conversation area** — a 3-column grid of suggested-prompt buttons (adaptive: customer-mode,
   segment-mode, or 6 general examples matching the task's own list) plus one free-text input.
   Clicking a prompt or submitting free text sets `st.session_state["copilot_asked"]`, which
   drives the answer render below. No chat bubbles, no message history — one question, one
   answer, editorial layout.
3. **Evidence/action area** — `components.agent_response_block(response)` renders the answer's
   `Label: value` lines as bolded fields (Recommendation/Why/Evidence/What to do/What to avoid/
   Confidence/Caution, whichever the answer actually produced), a quiet provenance caption, and —
   only when the underlying tool call actually returned customer rows — `components.priority_list()`,
   a 5-row-capped, click-to-open list with a "View all N matching customers →" deep link when more
   exist.

**Empty state:** before any question is asked and no context is set, `theme.empty_state()` renders
"RETENTION INTELLIGENCE" / "Ask a question about customers, risk, value, or retention actions."
with the suggested-prompt grid as the visual centerpiece — never a "no data" message.

**Design constraints honored:** no KPI-card grid, no emoji, no gradients, no chat-bubble UI, no
new JavaScript, no Plotly animation hacks. Navy/neutral/accent palette and existing typographic
scale reused unchanged. "Living" signals are all CSS/Streamlit-native: the context-strip's colored
dot, `st.spinner("Consulting the retention model…")` during `agent.ask()`, hover states on
priority-list "Open →" buttons, and the smooth same-render appearance of the answer block.

## 3. Agent integration

The page never talks to `agent_tools.py` or `llm_provider.py` directly. It builds one
`agent.AgentContext` per question (carrying the already-loaded aggregate DataFrames, the optional
`customer_df`, and `selected_customer_id`/`selected_segment`) and calls `agent.ask(question, ctx)`
— the exact same function Task 03 shipped and tested. Whether that call uses the LLM tool-calling
loop or the deterministic fallback is entirely `agent.py`'s decision; the page only renders
whatever `AgentResponse` comes back, via `components.agent_response_block()`. `agent.get_tool_result()`
is used once, inside `agent_response_block()`, to pull the `search_customers` tool's row data for
the priority list — no tool is called a second time and no arguments are guessed.

**Provenance:** `agent_response_block()` has four branches, matching `AgentResponse`'s own
transparency fields: LLM + tools → "Grounded in N analytical tools."; LLM alone → "AI-synthesized.";
fallback succeeded → "Deterministic answer — AI synthesis not used (`<reason>`)."; fallback
failed/no data → "AI synthesis unavailable (`<reason>`)." No chain-of-thought, no raw tool/JSON
dump is ever shown.

## 4. Manager workflow — validated end to end, live

The task's 13-step workflow was walked in a real browser session (`localhost:8640`, no
`ANTHROPIC_API_KEY` configured — the genuine current environment):

1. Opened Retention Intelligence fresh → empty-state hero + 6 suggested prompts rendered, no
   "No data"/"No query" message.
2. Clicked "How many customers are at elevated risk?" → concise finding rendered directly below
   (headline + supporting evidence + provenance caption), **no stale empty-state hero above it**
   (see §6, ordering-bug fix).
3. Numbers in the answer (970,960 scored, 22,692 High risk, 129,735 elevated, 2,413 high-risk ×
   high-value, ₹2,070,633,834 total HRR, ₹34,870,119 exposure) matched `risk_scoring_summary.json`
   exactly — nothing hard-coded.
4. Loaded customer data via the on-demand "Load customer data" button (~971K rows), confirmed no
   crash and prior answer stayed intact.
5. Navigated to Priority Customers, selected a High-risk/Low-value/Stable-Monitor customer row,
   clicked "Open full profile for `<id>`… in Customer 360 →".
6. Customer 360 opened with that customer's full profile (risk/value/segment badges, evidence,
   recommendation) and the renamed "Ask Retention Intelligence about this customer →" link.
7. Clicked that link → Retention Intelligence opened with the context strip already showing
   "Analysing customer `<id>`" plus HIGH RISK / LOW VALUE / STABLE-MONITOR badges and
   customer-specific suggested prompts ("Why is this customer at risk?", "What should we do for
   this customer?", "Should we offer a discount?", etc.) — **no session-state key or
   implementation detail exposed to the user.**
8. Clicked "Why is this customer at risk?" → the deterministic answer rendered with the full
   Recommendation/Why/Evidence/What to do/What to avoid/Confidence/Caution structure, all
   evidence values specific to that exact customer (Model Risk Score 1.00, Estimated Churn
   Probability 100%, HRR ₹3.5K, 369-day recency vs. a 20-day base average, 20.0% cancellation
   rate vs. 1.4% base), and the honest banner `[AI synthesis unavailable: no AI provider is
   configured for this session — showing the grounded deterministic answer]` plus the matching
   provenance caption at the end. The AI-vs-fallback distinction was never blurred.

This is the one part of the manager workflow that `AppTest` structurally cannot exercise (its
isolated page-run raises `StreamlitPageNotFoundError` on any cross-page `st.page_link`, a known,
already-documented harness limitation — see `test_customer_context`'s own comment in
`tests/test_retention_intelligence_ui.py`), so this live walkthrough is the only real validation
of steps 5-9 of the workflow, and it passed cleanly on first attempt.

## 5. Tests

- `tests/test_agent_tools.py` — **39/39 passed** (unchanged from Task 02, re-run for regression).
- `tests/test_agent_orchestration.py` — **29/29 passed** (unchanged from Task 03; re-run after the
  additive `ToolCallRecord.result` extension to confirm no regression).
- `tests/test_retention_intelligence_ui.py` — **15/15 passed** (new this task): initial empty
  state (+ regression guard that the empty-state title never appears alongside a rendered
  answer), suggested-prompt interaction, free-text question, customer context, segment context,
  aggregate-query numbers cross-checked against `risk_summary`, customer-list query row shape
  (via a mocked `llm_provider.complete_with_tools`), the priority-list navigation mechanism
  (`st.switch_page` + session-state, source-verified), the Customer 360 handoff link, deep-link
  generation, fallback-mode-is-the-real-path, honest provenance captioning, missing customer
  data, unknown customer, unsupported question.
- AppTest sweep across all 6 pages (`overview`, `action_center`, `customer_value`,
  `priority_customers`, `customer_360`, `retention_copilot`): all pass except `overview.py`'s
  pre-existing (not touched this task) cross-page `page_link`, which hits the same known harness
  limitation — not a regression.

**Total: 83/83 automated tests passing**, plus the live browser walkthrough in §4.

The `test_retention_intelligence_ui.py` mocked-LLM tests validate the *shape* of data the UI
depends on (`agent.get_tool_result`, `ToolCallRecord.result`) when a tool-calling loop runs; they
do **not** validate real Anthropic model behavior, since `ANTHROPIC_API_KEY` is genuinely unset in
this environment. This is flagged explicitly, matching the same caveat already established in
`TASK_03_validation_report.md`.

## 6. Bugs found and fixed this task

1. **Empty-state/answer ordering bug** (found via live-browser screenshot, not by the initial
   automated tests). `has_context_or_history` was originally computed *before* the suggested-prompt
   button loop, so on the render immediately after a click it still read the pre-click (empty)
   value of `copilot_asked` — the empty-state hero and the freshly-computed answer both rendered
   in the same view. Fixed by reserving the hero's position with `st.container()` *before* the
   button loop and moving the `has_context_or_history` check and the hero render to *after* the
   button/free-text handling. Verified live (fresh server restart, port 8640) and with a new
   regression assertion in `test_suggested_prompt_interaction`.
2. **Self-caught div-spanning-`st.markdown`-calls bug**, the same class fixed once earlier in this
   project: an open `<div>` in one `st.markdown` call, closed in a separate later call with
   Streamlit widgets rendered in between, does not actually nest those widgets (Streamlit renders
   each `st.markdown` as an independent DOM sibling; the browser auto-closes the orphaned tag).
   Caught by inspection before any test run and fixed by applying the CSS class directly to the
   single self-contained "You asked" `st.markdown` call instead of spanning two calls.
3. `test_customer_context`'s initial assertion (`assert not at.exception`) was corrected to assert
   the specific expected `StreamlitPageNotFoundError` from the new Customer-360 `page_link`, per
   the pre-existing AppTest harness limitation — not an app bug; the identical pattern is
   confirmed working live in §4.

## 7. Responsive validation

Tested at normal desktop width (1536px, this environment's actual screen) and at a narrower
effective width via a 1.5x render-zoom approximation (the sandboxed browser's OS window is fixed
at 1536x864 and the `resize_window` tool's request did not change `window.innerWidth` here, so a
true OS-level resize was not available). At the narrower effective width: Retention Intelligence's
hero, context strip, badges, suggested-prompt grid (labels truncate gracefully with `…`), and the
Q&A answer block all reflowed with **no horizontal page overflow**; Priority Customers' filter row
and dataframe reflowed the same way. This is a reasonable but not fully equivalent substitute for
a true device-width test — noted as a limitation below.

## 8. Known limitations

- Live model behavior (actual LLM tool-calling, multi-turn reasoning, AI-synthesized answers) is
  unverified in this environment — `ANTHROPIC_API_KEY` is not configured. Every live and automated
  check in this report exercises the deterministic fallback path, which is the actual current
  behavior of the deployed app, honestly disclosed to the user via the `[AI synthesis unavailable:
  ...]` banner and the provenance caption.
- True OS-level window resize was not available in this sandboxed browser; responsive validation
  at a narrower width used a render-zoom approximation rather than a genuine viewport resize.
- `overview.py`'s pre-existing cross-page `page_link` still trips the known `AppTest` isolation
  limitation; this predates this task and was not touched.

## 9. Stop condition

Retention Intelligence is a polished flagship experience: `agent.ask()` is wired directly into the
UI, the deterministic fallback works and is honestly disclosed, customer and segment context both
work (including the full Customer 360 handoff), customer-list results render as a compact priority
list with working navigation and a deep link to the full Priority Customers view, provenance is
visible and never overstated, all 83 automated tests pass, the live manager workflow was walked
end to end successfully, and no other page's functionality was broken. No presentation, marketing
site, RAG, or autonomous action was built, per the task's explicit stop condition.
