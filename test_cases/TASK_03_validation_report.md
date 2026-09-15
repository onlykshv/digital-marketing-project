# Validation Report — Task 03: AI Agent Orchestration Layer

**Status:** The agent orchestration layer (brain + tool-calling + fallback) is implemented and
validated. **No UI was built or changed this task, as instructed.** No page imports any file
added this task yet — that wiring is Task 04's job (see §11 for exactly what's ready).
**Date:** 2026-09-10

---

## 1. Files changed

| File | Change | Why |
|---|---|---|
| `dashboard/lib/llm_provider.py` | **Extended** (not replaced). Added `complete_with_tools()` and `format_tool_result()`. `complete()` (used by `copilot_engine.py`) is untouched. | Multi-turn tool-use support, isolated to this one file per the task's explicit instruction not to couple Anthropic-specific code to business logic. |
| `dashboard/lib/agent_tool_schemas.py` | **New.** The 9 tools' Anthropic tool-use schemas, each with an explicit description of purpose/inputs/outputs/what-not-to-use-it-for. | Required deliverable (§2 of the task). |
| `dashboard/lib/agent.py` | **New.** The orchestrator: `AgentContext`, `AgentResponse`, the strict tool dispatch table, the LLM tool-call loop, the system prompt (grounding rules), and the deterministic fallback. | This task's primary deliverable. |
| `tests/test_agent_orchestration.py` | **New.** 29 tests — 16 required categories plus turn-cap enforcement and schema-completeness checks. | Required deliverable (§9). |
| `test_cases/TASK_03_validation_report.md` | **New.** This report. | Required deliverable. |

**No other file was touched.** `dashboard/lib/agent_tools.py` (Task 02's deterministic tools), `dashboard/lib/copilot_data.py`, `dashboard/lib/copilot_engine.py`, `dashboard/lib/data.py`, `dashboard/lib/components.py`, `dashboard/lib/theme.py`, `dashboard/lib/caveats.py`, `dashboard/app.py`, and all six `dashboard/pages/*.py` files are unmodified. Confirmed both by construction and by `find dashboard/pages dashboard/app.py -newer test_cases/TASK_02_validation_report.md` returning nothing (§13).

## 2. Architecture implemented

```
question -> agent.ask(question, ctx)
         -> not llm_provider.is_configured()?  -> _deterministic_fallback()  [always available]
         -> configured -> _run_tool_loop():
                LLM (via llm_provider.complete_with_tools) picks a tool + arguments
                     from the 9-tool schema list ONLY
                -> agent.py's _execute_tool(): strict allow-list dispatch, argument
                     validation/resolution (e.g. customer_id -> full record)
                -> agent_tools.py executes the ONE matching deterministic function
                -> the tool's exact {"ok","data","error"} result goes back to the model
                     verbatim, as a tool_result
                -> repeat (bounded at 6 turns) until the model has a final answer
            -> on any ProviderUnavailable during the loop: falls back to the same
               deterministic path, with the failure reason attached (never silent)
         -> returns AgentResponse{answer, tools_used, tool_calls, grounded, used_llm,
            fallback_reason} -- the exact provenance shape requested in §5 of the task,
            extended with `used_llm`/`fallback_reason` for the same transparency
            discipline already shipped in copilot_engine.py's `llm_unavailable_reason`.
```

This matches `AGENT_ARCHITECTURE_PLAN.md`'s proposed architecture (§C) exactly, and realizes the
"CURRENT COPILOT -> Deterministic evidence engine -> NEW AGENT ORCHESTRATOR -> Optional LLM
synthesis" layering the task required: `copilot_engine.py` is not just preserved, it is **called
directly** by `agent.py`'s deterministic fallback (§6) — the new orchestrator's fallback path *is*
the existing Copilot, not a re-implementation of it.

## 3. Tool schemas

All 9 tools from `agent_tools.py` have an Anthropic tool-use schema in `agent_tool_schemas.py`.
Each description states what the tool does, when to use it, valid inputs, what it returns, and
what NOT to use it for (e.g. `get_customer`: "Do NOT use this to search for customers matching
criteria -- use search_customers for that"). A shared terminology reminder is appended to every
schema whose output includes Model Risk Score, Estimated Churn Probability, HRR, or High-Risk
Historical Revenue Exposure, restating the four distinctions in the model-facing text itself, not
just in code comments a model never sees.

**LLM-facing schemas are not identical to `agent_tools.py`'s raw signatures.** Any tool that
needs "a customer" takes a `customer_id` **string** in its schema — never a customer object. This
is a deliberate design choice: `agent.py`'s dispatcher resolves `customer_id -> get_customer()`
internally before calling `recommend_action`/`compare_to_champions` with the resolved dict. The
model can therefore never construct or guess a customer's field values; it can only ever name a
customer by ID and receive back whatever the deterministic layer actually knows about them. This
is Rule 3 ("never invent numerical values") enforced structurally, not just by instruction.

`search_customers`'s schema explicitly separates `min_risk_score`/`max_risk_score` ("NOT a
probability filter") from `min_calibrated_probability`/`max_calibrated_probability` ("This IS the
calibrated probability filter") in the property descriptions themselves — verified by
`test_search_customers_schema_distinguishes_risk_score_from_probability`.

## 4. Grounding rules

All 10 rules from the task are in `agent._SYSTEM_PROMPT` verbatim in spirit, each numbered
exactly as given, plus the four terminology distinctions restated as their own paragraph. The
system prompt also carries the required answer-structure guidance (§4 of the task: customer /
list / business question templates) and explicit tool-selection guidance ("call the MINIMUM
number of tools needed... decide based on the actual question, never a fixed script") so the
model is not hard-coded into the example orchestration sequence from the task brief — it is
told the *pattern*, not a script.

Rule 4 ("never answer a customer-specific question without calling the appropriate tool") is
additionally enforced structurally, not just by instruction: `agent.py` has no code path that
lets an "answer" reach the user without either (a) at least one real tool call in the LLM path,
or (b) the deterministic fallback's own guaranteed tool call. There is no "just answer from
context" shortcut anywhere in this module.

## 5. Tool transparency / provenance

`AgentResponse` carries exactly the shape requested:

```python
AgentResponse(
    answer: str,
    tools_used: list[str],
    tool_calls: list[ToolCallRecord],   # {tool, arguments, ok} -- no raw tool output dumped
    grounded: bool,
    used_llm: bool,
    fallback_reason: str | None,
)
```

No internal chain-of-thought is ever exposed — `tool_calls` records only the tool name, the
arguments sent, and whether it succeeded, never the model's reasoning text between tool calls
(the system prompt also explicitly instructs the model not to narrate its tool-selection
reasoning in the final answer). This structure is what Task 04 will render as a "Based on
customer risk, value and segment data" style provenance line — not built this task, since UI
work is explicitly out of scope.

## 6. Fallback behavior

`llm_provider.is_configured()` is genuinely `False` in this environment (confirmed,
`test_no_api_key_in_this_environment`), so every fallback test in §9 exercises the **real, live**
fallback path, not a simulation of one.

- **Customer/segment context available** (`ctx.selected_customer_id` / `ctx.selected_segment` set
  — mirrors the existing Copilot's "already attached" context): routes directly through
  `copilot_engine.deterministic_customer_answer` / `deterministic_segment_answer` — the exact
  same, already-tested (34/34) code the current Retention Copilot page uses. Not a
  re-implementation; a direct call.
- **No customer/segment context, but the question matches a known shape** ("how many customers
  are at elevated risk", "which segment should we prioritize"): routes to
  `get_aggregate_metrics` / `rank_segments_by_priority` directly, one tool call, real data,
  formatted per the task's business-question structure.
- **Anything else**: an honest "AI synthesis is unavailable for this question (\<reason\>), and it
  doesn't match a question this dashboard can answer deterministically without one" message —
  never a guess, never a pretend-AI answer. Every fallback answer that IS grounded is prefixed
  with `[AI synthesis unavailable: <reason> -- showing the grounded deterministic answer]` so it
  is never mistaken for an AI-synthesized response — the same transparency discipline already
  shipped in `copilot_engine.py`'s `llm_unavailable_reason` fix, now applied one layer up.
- **The current deterministic Retention Copilot page is untouched and still fully functional**
  on its own (confirmed via the unchanged 34-test suite and AppTest, §9/§13) — nothing was
  removed.

## 7. Query routing / safety

- Every tool call passes through `_execute_tool()`, which checks the tool name against a fixed
  Python dict (`_TOOL_DISPATCH`) before calling anything — there is no `getattr`/`eval`/`exec`
  anywhere in this module. A tool name the LLM invents (or a hallucinated/malicious one) returns
  `{"ok": False, "error": "Unknown tool: ..."}` and is never executed
  (`test_unknown_tool_name_is_rejected_not_executed`, `test_unknown_tool_name_in_mocked_loop_does_not_crash`).
- Arguments are validated before dispatch (non-dict arguments rejected; `limit` must be a positive
  int; `customer_id`/`segment` exactly-one-of checks for the two-mode tools) **and** by
  `agent_tools.py` itself underneath (unknown risk tier / segment / sort_by all already return
  explicit errors, per Task 02) — two layers, not one.
- The tool-call loop is bounded at 6 turns (`_MAX_TOOL_LOOP_ITERATIONS`); a model that never stops
  calling tools fails safe with a clear message instead of looping forever
  (`test_tool_loop_turn_cap_is_enforced`).
- No code execution capability exists anywhere in this path — the LLM can only select from the 9
  named tools and supply their declared JSON-Schema arguments.

## 8. Multi-tool questions

The tool-call loop supports any number of sequential tool calls up to the turn cap; nothing in
`agent.py` hard-codes a fixed sequence. `test_multi_tool_question_via_mocked_tool_loop` exercises
the exact example from the task brief ("Find the highest-value customers who are at high risk and
tell me what we should do") via a mocked two-call sequence (`search_customers` then
`recommend_action`) and confirms both calls execute against real data and both succeed. The system
prompt explicitly instructs "call the minimum necessary tools... decide based on the actual
question, never a fixed script" — the sequence is the model's choice at inference time, not
something this codebase scripts.

## 9. Tests

**`tests/test_agent_orchestration.py` — 29/29 passed.** Covers all 16 required categories:

| # | Category | How tested |
|---|---|---|
| 1 | Exact customer question | Real fallback call, `selected_customer_id` set, real data |
| 2 | Unknown customer | Real fallback call with a fabricated ID |
| 3 | High-risk search | Mocked tool-call loop -> real `search_customers` execution |
| 4 | High-risk/high-value search | Mocked loop + independent real-tool re-verification |
| 5 | Aggregate question | Real fallback keyword route, real data |
| 6 | Segment question | Real fallback call, `selected_segment` set |
| 7 | Risk explanation | Mocked loop -> real `explain_customer_risk` execution |
| 8 | Recommended action | Mocked loop -> real `recommend_action` execution |
| 9 | Comparison question | Mocked loop -> real `compare_to_champions` execution |
| 10 | Multi-tool question | Mocked 2-call sequence, both calls real and both succeed |
| 11 | Unsupported question | Real fallback, no context, no keyword match -> honest refusal |
| 12 | Missing API key | Real (`is_configured()` genuinely False in this environment) |
| 13 | Malformed tool arguments | 5 sub-tests: missing required field, negative limit, both-of mutually-exclusive args, non-dict args, unknown segment |
| 14 | Hallucination prevention | Unknown tool name rejected at dispatch; also inside a mocked loop, confirmed not executed and the loop still completes |
| 15 | Causal-language guardrail | Asserts the system prompt's Rule 7 text and bad/good examples are present; asserts `explain_customer_risk`'s schema states "association... never a cause" |
| 16 | Terminology guardrail | Asserts all 4 terminology distinctions appear correctly in the system prompt; asserts `search_customers`' schema separates risk-score from probability filters in the property text itself |

Plus: turn-cap enforcement, tool-dispatch-table-matches-schema-list consistency, and a schema-
completeness check (every tool has a name, a description over 50 characters, and a valid
`input_schema`).

**Existing test suites re-run for regression, per §13:**
- `tests/test_agent_tools.py` (Task 02): **39/39 passed**, unchanged.
- `scratchpad/test_copilot.py` (the existing Retention Copilot's own 34-assertion suite): **34/34
  passed**, unchanged — direct evidence the deterministic fallback's reuse of
  `copilot_engine.py` didn't alter that module's behavior (it wasn't modified at all).
- AppTest (`scratchpad/apptest_master_restructure.py`, all 6 pages): no new failures — the one
  failure present is the same pre-existing, already-documented harness limitation from every prior
  report (Overview's `st.page_link` under `AppTest.from_file()`'s isolated page registry).

## 10. Tests that could not be performed / API-key limitation

**No live Anthropic API call was made or could be made** — `ANTHROPIC_API_KEY` is not set in this
environment (confirmed programmatically, not assumed). This means:
- The LLM tool-loop's mechanics (looping, dispatch, provenance, turn-cap) are fully tested via
  mocked `llm_provider.complete_with_tools` responses (§9, tests 3/4/7/8/9/10/14/turn-cap) — these
  validate `agent.py`'s own code, not the model's actual tool-selection judgment.
- Whether a real Claude model reliably picks the *right* tool(s) for a given free-text question,
  produces well-formed tool-use requests, follows the system prompt's answer-structure and
  grounding rules in genuinely novel phrasing, or handles an ambiguous question sensibly, is
  **unverified** and cannot be verified without a configured key. This is stated plainly per this
  project's established discipline (same honest gap flagged in the original Retention Copilot
  report) rather than presenting mocked-loop tests as if they validated live model behavior.
- `llm_provider.complete_with_tools()`'s actual HTTP/SDK call path (the `try: import anthropic ...
  client.messages.create(...)` block) is therefore also unverified end-to-end — only its
  surrounding error handling (`ProviderUnavailable` on missing key/package) is exercised, the same
  way `complete()`'s equivalent path already was in the original Copilot work.

## 11. Known risks

- **Tool-selection quality is unverified without a real model**, as above — the single biggest
  unknown for Task 04 to watch for once a key is available.
- **The deterministic fallback's keyword routing is intentionally narrow** (customer/segment
  context, "how many"/"churn rate" style aggregate questions, "which segment"/"prioritize" style
  ranking questions) — anything else gets an honest refusal rather than an attempt. This is a
  deliberate scope choice (the task explicitly prefers refusal over unsafe guessing), not an
  oversight, but it means the fallback experience is noticeably less capable than the LLM path —
  expected and by design.
- **`complete_with_tools`'s max-token budget (1024) and the 6-turn loop cap are judgment calls**,
  not derived from a specific requirement — reasonable for the question shapes in this task's
  examples, worth revisiting once real usage exists.
- **The `anthropic` package's tool-use response shape is assumed stable** across the installed
  SDK version (`anthropic>=0.40`, from Task 02) based on its documented interface; this has not
  been exercised against a live response, so a version-specific quirk (e.g. a differently-named
  attribute) would only surface once a key is configured and the path is actually exercised.

## 12. Exact next step for frontend integration (Task 04)

1. In `pages/retention_copilot.py`, import `lib.agent` and add a new "ask anything" free-text
   entry point alongside the existing preset-question buttons (which continue to call
   `copilot_engine.answer_customer_question`/`answer_segment_question` unchanged). Build an
   `agent.AgentContext` from the same dataframes the page already loads via `data.safe_load(...)`,
   with `selected_customer_id`/`selected_segment` set from the page's existing search/dropdown
   state (`st.session_state["cust360_search"]`, the segment picker) — no new session-state key
   needed, reuse what's already there.
2. Call `agent.ask(question, ctx)` and render `AgentResponse.answer` through a new or adapted
   version of `components.copilot_answer_block` (or a plain `st.markdown`, since the answer is
   already structured plain text) — plus a small provenance caption from `tools_used`/`grounded`/
   `used_llm`, matching the transparency-line pattern `components.copilot_answer_block` already
   established for `llm_unavailable_reason`.
3. Set `ANTHROPIC_API_KEY` in the actual deployment environment before claiming the LLM path is
   validated — Task 04 (or whoever configures the environment) should re-run
   `tests/test_agent_orchestration.py`'s mocked tests (still valid) AND do a real, live, manual
   question-asking pass once a key exists, since §10 above is a real, current gap.
4. Consider surfacing `AgentResponse.tool_calls` (the `build_dashboard_deep_link` result
   specifically) as an actual `st.page_link` CTA once the model starts producing them — the tool
   already returns a validated, safe page target; only the rendering is missing.

## 13. Regression protection — checklist

1. **Syntax checks** — `ast.parse()` over every `dashboard/pages/*.py`, `dashboard/lib/*.py`,
   `app.py`, and all three test files: **OK**.
2. **Deterministic agent-tool tests** (`tests/test_agent_tools.py`): **39/39 passed**.
3. **Existing Copilot tests** (`scratchpad/test_copilot.py`): **34/34 passed**.
4. **New agent orchestration tests** (`tests/test_agent_orchestration.py`): **29/29 passed**.
5. **Streamlit/AppTest suite**: no new failures (same one pre-existing harness limitation).
6. **Live smoke test**: server restarted fresh; `/`, `/retention_copilot`, `/priority_customers`
   all return HTTP 200 with a clean startup log (no import errors from the three new/changed
   `lib/` modules, even though nothing imports them yet).
7. **Notebooks unchanged, models unchanged, outputs unchanged, src unchanged**:
   `find outputs notebooks models src -newer test_cases/TASK_02_validation_report.md -type f`
   returns nothing.
8. **Existing dashboard functionality preserved**: `find dashboard/pages dashboard/app.py -newer
   test_cases/TASK_02_validation_report.md -type f` returns nothing — no page file was touched.
