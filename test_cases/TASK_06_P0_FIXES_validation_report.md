# Validation Report — Task 06: Clear All P0 Product Blockers

**Status:** All five P0 findings from `test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md` are fixed,
tested, and verified live in a fresh, no-`ANTHROPIC_API_KEY` browser session. No redesign, no new
feature, no ML/analytics/notebook change. Scope was held strictly to the five P0s — no P1/P2 item
from the audit was touched.
**Date:** 2026-09-11

---

## 1. P0-1 — Broken default Retention Intelligence prompts

**Finding:** "Who should we contact first?", "Show me high-risk, high-value customers.", and "Why
is this customer at risk?" (no customer selected) all hit the generic "doesn't match a question
this dashboard can answer" refusal in the real, no-API-key deployment.

**Root cause:** `agent._deterministic_fallback()` had no keyword route to `search_customers` at
all (only `get_aggregate_metrics` and `rank_segments_by_priority` were reachable without an LLM),
and no special handling for a customer-shaped question ("this customer") asked with no customer
in context — both fell straight through to the generic unsupported-question message.

**Fix** (`dashboard/lib/agent.py`):
- Two new deterministic routes in `_deterministic_fallback`, each calling the real
  `agent_tools.search_customers` (never a duplicate filter):
  - `_CONTACT_FIRST_KEYWORDS` ("contact first", "who should we contact", "who should we save", …)
    → `search_customers(risk_tier=["High"], sort_by="risk_score_full", ascending=False, limit=10)`
    — the actual priority/customer ranking capability, narrowed to the highest-urgency tier.
  - `_HIGH_RISK_HIGH_VALUE_KEYWORDS` ("high-risk, high-value", "high risk and high value", …) →
    the same tool with `value_tier=["High"]` added — matching Overview's own "Priority Zone"
    (High risk × High value) framing, not a new definition.
  - Both routes check `_need_customer_df(ctx)` first and return an honest "Click 'Load customer
    data' above, then ask again" guidance if the large table isn't loaded yet — never a crash,
    never a silent failure.
  - A new `_format_search_customers_answer()` renders the headline + "so what" closing line only;
    the actual customer rows are rendered by the existing `components.priority_list()` via
    `ToolCallRecord.result` (Task 04's mechanism, untouched).
- A new `_CUSTOMER_REFERENCE_PHRASES` check ("this customer", "that customer") fires when no
  customer/segment context is set: returns *"This question is about a specific customer, but none
  is currently selected. Search for a customer by ID above, or open one from Priority Customers or
  Customer 360, then ask this again."* — `grounded=False`, no tool called, so it can never be
  mistaken for a real evidence-backed answer. This also fixed a **fourth** prompt the audit's
  own live testing hadn't isolated as a separate item but which shares the identical root cause:
  "What should we do about this customer?" with no context.

No hardcoded example customer or answer was introduced anywhere — every route calls a real tool
against real, already-loaded data.

## 2. P0-2 — "Retention Copilot" → "Retention Intelligence"

**Finding:** the top nav said "Retention Copilot" while the page itself said "Retention
Intelligence."

**Root cause:** `dashboard/app.py`'s `st.Page(..., title="Retention Copilot")` was never updated
when the page content was renamed in Task 04.

**Fix** — every genuinely user-facing or AI-output-facing occurrence renamed:
- `dashboard/app.py`: `st.Page(..., title="Retention Intelligence")` (the nav label itself).
- `dashboard/lib/agent_tools.py`: `_DEEP_LINK_PAGES["retention_copilot"]`'s label string
  `"Retention Copilot"` → `"Retention Intelligence"` — this is what any future
  `build_dashboard_deep_link`-driven CTA would actually render as its link text.
- `dashboard/lib/copilot_engine.py`: the LLM system prompt's self-identification, `"You are
  Retention Copilot, ..."` → `"You are Retention Intelligence, ..."` — the identity a
  configured LLM would actually see and could echo back to a manager.

**Deliberately NOT renamed** (per the task's explicit instruction): the internal module
docstrings in `agent.py`, `copilot_data.py`, `copilot_engine.py`, and one code comment in
`retention_copilot.py` that describe *what the existing Copilot engine is* for a future
developer reading the code — none of these are shown to a user or to an LLM, and the task
explicitly said not to blindly rename technical/historical references. `dashboard/pages/
retention_copilot.py`'s filename is also unchanged — it's the technical filename the task said to
leave alone; the page's own visible title has said "Retention Intelligence" since Task 04.

A full `grep -rn "Retention Copilot" dashboard/ --include="*.py"` after this fix returns only
those four internal-comment lines — zero user-facing occurrences remain.

## 3. P0-3 — Currency consistency (NT$ → INR)

**Finding:** the agent's aggregate/business-question and segment-ranking answers displayed raw
`NT$` figures while every other surface in the product displays ₹ (INR, display-only conversion).

**Root cause:** `agent._format_aggregate_answer()` and `agent._format_rank_segments_answer()`
used raw `f"{value:,.0f} NT$"` f-strings instead of the centralized `theme.fmt_currency()` every
other page already uses.

**Fix** (`dashboard/lib/agent.py`):
- Both formatters now call `theme.fmt_currency(...)` — the exact same function, same
  `theme.NTD_TO_INR = 2.62` fixed rate, same `₹` symbol, same K/M/B formatting as Overview,
  Customer Value, Action Center, and Customer 360 already use. **No new exchange-rate constant,
  no duplicated conversion logic** — `agent.py` now imports `theme` and calls its one existing
  function, nothing more.
- The source data (`outputs/*.csv`/`*.json`, all still in NT$) and `agent_tools.py`'s tool
  outputs (still `*_ntd` fields, still raw NT$) are **completely unchanged** — this is a
  render-time-only fix, exactly as required.
- **New disclosure**: `dashboard/pages/retention_copilot.py` previously rendered **no**
  Methodology & limitations expander at all (the only one of the four data-bearing pages missing
  one). Added `caveats.render_caveats(["hrr"])` at the bottom of the page — reusing the existing
  `lib/caveats.py` `_hrr_body()` text verbatim (already used on Customer Value and Action Center),
  which explicitly states: *"Figures are displayed in ₹ (INR) for readability, converted from the
  source data's native NT$ ... at a fixed rate ... This is a constant display-only conversion, not
  a live exchange rate -- every underlying file, model, and calculation remains in NT$."* No new
  caveat text was authored; the existing, already-validated body was reused.

**Verified rendered, not just source-checked** (live browser, §6 below, and automated tests §5):
aggregate answers, segment-ranking answers, and the two new search-customer answers all show ₹
with no `NT$` anywhere in the rendered text. Customer/segment-context answers (via
`copilot_engine.py`) already used `theme.fmt_currency` before this task and are unchanged.

## 4. P0-4 — `search_customers` available without an LLM

**Finding:** `search_customers` — the tool behind the flagship compact priority-list UI
(`components.priority_list`, built in Task 04) — had no deterministic route at all, so it had
never actually rendered in this project's real, no-API-key environment.

**Fix:** this is the same code change as P0-1 §1 above — the two new keyword routes both call
`agent_tools.search_customers(ctx.customer_df, ...)` directly (the real, unmodified Task 02 tool;
9-tool architecture and every existing tool implementation are untouched). Specific requirements
verified:

| Requirement | How verified |
|---|---|
| High-risk query | `test_contact_first_routes_to_search_customers_deterministically` — real data, `risk_tier="High"` only |
| High-value query | covered by the high-risk×high-value route (value_tier alone wasn't a named audit example, so not added as a separate keyword route — see §7 limitations) |
| High-risk + high-value query | `test_high_risk_high_value_routes_to_search_customers_deterministically` — real data, both tiers, cross-checked against `risk_summary`'s own `high_risk_high_value_customers` count (2,413) live in the browser |
| No results | `test_search_customers_route_no_results_handled_gracefully` — direct unit test of `_format_search_customers_answer({"rows": [], ...})` |
| Malformed/unknown criteria | Unaffected — both new routes pass only known-valid literals (`"High"`); `agent_tools.search_customers`'s own malformed-input handling is unchanged and still covered by Task 02's 39-test suite |
| Regex-special-character customer IDs | `test_search_customers_routes_handle_customer_ids_with_regex_special_characters` (automated) + live browser walkthrough (§6) with `eh+OR+CX5dybmVcsmK1c2COYyFQKfD5k19TsHC/PWBM=`, a real `+`/`/`-bearing msno, round-tripped through search → priority list → Customer 360 → Retention Intelligence with no corruption |
| Hands off to Customer 360 | `test_search_customers_results_hand_off_to_customer_360_via_the_proven_mechanism` (automated, confirms the row's msno resolves via `agent_tools.get_customer`) + live click-through via `components.priority_list`'s existing `st.switch_page`/`cust360_search` mechanism (unchanged) |

No fake "AI" response is ever produced — every new route's answer opens with the same
`[AI synthesis unavailable: <reason> -- showing the grounded deterministic answer]` banner and
closes with the same provenance caption as every other fallback answer, per Task 04's established
architecture.

## 5. P0-5 — Overview and Action Center → Retention Intelligence

**Finding:** the two pages a manager is most likely to visit first had no path into the flagship
assistant.

**Fix:**
- `dashboard/pages/overview.py`: one `st.button(f"Ask Retention Intelligence about
  {top_opportunity['priority_group']} →")` directly below the page's single top recommendation
  card. On click: `st.session_state["copilot_segment_choice"] = top_opportunity["priority_group"]`
  then `st.switch_page("pages/retention_copilot.py")`.
- `dashboard/pages/action_center.py`: the identical pattern, tied to the Priority 01 card
  specifically ("the action/priority being examined," per the task's wording) — not added to the
  secondary segments table, to avoid clutter.
- Both reuse the segment selectbox's existing `key="copilot_segment_choice"` binding on
  `retention_copilot.py` — **no new session-state pattern was invented**; pre-seeding
  `st.session_state[key]` before `st.switch_page` is the same class of mechanism already proven
  for `cust360_search` (Priority Customers → Customer 360) and `pending_filter`
  (search-results → Priority Customers).
- Both buttons use plain default (secondary) Streamlit button styling — the same visual weight as
  the existing "Open →" buttons elsewhere in the app, not a primary/highlighted CTA, no banner, no
  new card.
- A small, deliberate ordering choice: Overview's new button was placed **before** its existing
  `st.page_link("pages/priority_customers.py", ...)` call in the script, so the CTA now renders
  directly under "More detail on this recommendation," with "View Priority Customers →"
  immediately below it (see the live screenshot in §6). This was necessary, not cosmetic: the
  pre-existing page_link raises a known, already-documented AppTest-only exception (unrelated to
  this task), and placing the new button after it would have made the button unreachable by any
  automated test, since AppTest halts script execution at the first uncaught exception.

## 6. Live browser validation (fresh server, `ANTHROPIC_API_KEY` genuinely unset)

Killed the previous server, confirmed `ANTHROPIC_API_KEY` absent from the environment
programmatically, and started a **fresh** Streamlit process (`streamlit run app.py --server.port
8650`) to guarantee every changed `lib`/`pages` module was freshly imported, not hot-reloaded.
Clean startup log, no import errors.

Walked the complete required workflow, `Overview → Retention Intelligence → question → evidence →
customer results → Customer 360 → customer-specific Retention Intelligence`, plus the three
previously-broken prompts individually:

1. **Nav bar** now reads "Retention Intelligence" (was "Retention Copilot") — confirmed on every
   page's top nav.
2. **Overview**: the new "Ask Retention Intelligence about At-Risk, Auto-Renew Off →" button
   renders directly under the top recommendation card. Clicked it → landed on Retention
   Intelligence with **"Segment in focus: At-Risk, Auto-Renew Off"** already set and
   segment-specific suggested prompts shown — context correctly preserved, no session-state key
   or implementation detail exposed to the user.
3. **Action Center**: identical CTA present under Priority 01, identical correct handoff verified.
4. **"Who should we contact first?"** (fresh, no context, customer data loaded): rendered
   `Headline: These are the highest-priority customers to contact first, ranked by Model Risk
   Score.` / `Result summary: 22,692 customers match -- the top 5 by Model Risk Score are below.`
   / `Recommended next step: ...`, followed by a real, click-through 5-row priority list (all
   High risk) and a **"View all 22,692 matching customers →"** deep link into Priority Customers
   — this exact UI element had never rendered in this environment before this fix.
5. **"Show me high-risk, high-value customers."**: `Headline: These customers are both High risk
   and High value -- the Priority Zone.` / `Result summary: 2,413 customers match ...` — 2,413
   matches exactly the `high_risk_high_value_customers` figure already shown on Overview/Customer
   Value, confirming consistency, not just non-crashing.
6. **"Why is this customer at risk?"** (no context): rendered the new, honest guidance — *"This
   question is about a specific customer, but none is currently selected. Search for a customer by
   ID above, or open one from Priority Customers or Customer 360, then ask this again."* — clearly
   not a fabricated answer.
7. **Full customer handoff with a regex-special-character ID**: Priority Customers → selected
   `eh+OR+CX5dybmVcsmK1c2COYyFQKfD5k19TsHC/PWBM=` → Customer 360 (full profile rendered correctly,
   ₹5.1K HRR, no corruption of the `+`/`/` characters) → "Ask Retention Intelligence about this
   customer →" → context strip showed the exact same ID with HIGH RISK / MEDIUM VALUE / STABLE
   MONITOR badges → asked "Why is this customer at risk?" → full grounded evidence answer,
   `Evidence: ... Historical Realized Revenue: ₹5.1K) ...` (₹, not NT$), correct fallback banner
   and provenance caption.
8. Confirmed no `NT$` text appeared anywhere across all of the above screens.

## 7. Automated tests

**New regression tests added, one section per file, clearly scoped to Task 06 / P0:**

- `tests/test_agent_tools.py`: +1 test (`test_build_dashboard_deep_link_retention_intelligence_label`) → **40/40 passed**.
- `tests/test_agent_orchestration.py`: +14 tests covering P0-1/P0-3/P0-4/P0-2 at the `agent.ask()`
  level against real data (contact-first routing, high-risk×high-value routing, tool-call
  equivalence with a direct `agent_tools.search_customers` call, regex-special-character IDs,
  no-results handling, missing-customer-data guidance, Customer-360 handoff data shape, the two
  customer-reference-without-context guidance cases, a sanity check that the guidance does NOT
  fire once context is set, INR-not-NT$ assertions on both new formatters, a currency-value
  equality check against `theme.fmt_currency` directly, and the system-prompt naming check) →
  **43/43 passed**.
- `tests/test_retention_intelligence_ui.py`: +11 tests, AppTest-driven against the real page in
  the real no-key environment (all three previously-broken prompts individually, both with and
  without customer data loaded, the three working-without-data prompts, the nav title source
  check, the new methodology-disclosure check, Overview/Action Center render + CTA-presence +
  CTA-source checks) → **25/25 passed**.
- `scratchpad/test_copilot.py` (the original Copilot's own 34-assertion offline suite, re-run for
  regression since `copilot_engine.py`'s system prompt string was touched) → **34/34 passed**,
  unchanged.

**Total: 142/142 automated tests passing**, zero regressions.

Two real AppTest-harness interactions were found and handled correctly during test-writing (not
app bugs): (a) Overview's own pre-existing `st.page_link` now sits after the new button in script
order, so the new button is captured by AppTest before the known, already-documented
`StreamlitPageNotFoundError` limitation fires; (b) the loaded-data "Who should we contact
first?"/"high-risk, high-value" tests correctly hit the exact same, already-documented limitation
via `components.agent_response_block`'s own pre-existing "View all N matching customers →" link —
both are asserted as the specific expected exception, the same established pattern used
throughout this project's test suite, not silently ignored.

## 8. Regression checklist

1. **Syntax check** — `ast.parse()` on every changed file: OK.
2. **`tests/test_agent_tools.py`**: 40/40.
3. **`tests/test_agent_orchestration.py`**: 43/43.
4. **`tests/test_retention_intelligence_ui.py`**: 25/25.
5. **`scratchpad/test_copilot.py`**: 34/34.
6. **AppTest sweep, all 6 pages** (`overview`, `priority_customers`, `customer_value`,
   `action_center`, `customer_360`, `retention_copilot`): all load with no exception except
   Overview's single, pre-existing, already-documented `page_link` limitation (unchanged
   behavior, not a regression).
7. **Live smoke test**: fresh server restart, clean startup log, all six pages visited live with
   no `ANTHROPIC_API_KEY` set.
8. **Monetary values**: every screen visited during live validation showed ₹, never `NT$`.
9. **Stale naming**: `grep -rn "Retention Copilot" dashboard/ --include="*.py"` returns only
   internal, non-user-facing docstrings/comments (4 lines, all in files/positions the task said
   not to touch).
10. **Protected directories**: `find notebooks models outputs src -newer
    test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md -type f` returns nothing — zero changes.

## 9. Files changed

| File | Change |
|---|---|
| `dashboard/app.py` | Nav page title `"Retention Copilot"` → `"Retention Intelligence"` (P0-2) |
| `dashboard/lib/agent.py` | Two new deterministic search routes, customer-reference-without-context guidance, both aggregate/ranking currency formatters routed through `theme.fmt_currency` (P0-1, P0-3, P0-4) |
| `dashboard/lib/agent_tools.py` | Deep-link label for `retention_copilot` → `"Retention Intelligence"` (P0-2) |
| `dashboard/lib/copilot_engine.py` | LLM system-prompt self-identification renamed (P0-2) |
| `dashboard/pages/overview.py` | New context-preserving CTA button into Retention Intelligence; reordered relative to the pre-existing page_link (P0-5) |
| `dashboard/pages/action_center.py` | New context-preserving CTA button into Retention Intelligence, tied to Priority 01 (P0-5) |
| `dashboard/pages/retention_copilot.py` | New `caveats.render_caveats(["hrr"])` methodology disclosure (P0-3) |
| `tests/test_agent_tools.py` | +1 regression test (P0-2) |
| `tests/test_agent_orchestration.py` | +14 regression tests (P0-1, P0-2, P0-3, P0-4) |
| `tests/test_retention_intelligence_ui.py` | +11 regression tests (P0-1, P0-2, P0-3, P0-5) |
| `test_cases/TASK_06_P0_FIXES_validation_report.md` | This report |

**Not touched:** `notebooks/`, `models/`, `outputs/`, `src/`, `dashboard/lib/theme.py` (the
centralized formatting utility was called, never modified), `dashboard/lib/agent_tools.py`'s tool
*implementations* (only the deep-link label string changed), `dashboard/lib/agent_tool_schemas.py`,
`dashboard/lib/llm_provider.py`, `dashboard/lib/copilot_data.py`, `dashboard/lib/components.py`,
`dashboard/lib/caveats.py`, `dashboard/pages/priority_customers.py`, `dashboard/pages/
customer_value.py`, `dashboard/pages/customer_360.py`. No file under `test_cases/` other than this
new report was touched; the issue tracker (`KKBox_Retention_Intelligence_Issue_Tracker.xlsx`) is
unchanged — none of its existing rows map directly to these five P0s (they were identified in
Task 05's free-standing audit, not the tracker), so per instruction no tracker row was added or
modified.

## 10. Known limitations, stated honestly

- **Live LLM tool-selection remains unverified** — `ANTHROPIC_API_KEY` is still not configured in
  this environment. Every fix and every test in this report exercises the deterministic fallback
  path, which is what actually runs for a real user today. This is the same, previously-documented
  limitation carried forward from Tasks 03/04, not a new gap introduced here.
- **Only the two specific phrasings from the audit are newly routed** ("contact first" and
  "high-risk, high-value") — a differently-worded list-style question (e.g., "show me our most
  valuable customers," with no risk qualifier at all) still falls through to the generic refusal
  in fallback mode. This was a deliberate scope decision to fix exactly the audited P0s without
  expanding the deterministic router into a general-purpose NLU system, which the project's own
  architecture plan (`AGENT_ARCHITECTURE_PLAN.md` §K) explicitly argues against.
- **The Overview/Action Center CTA is tied to the single top-priority segment only** (matching the
  audit's "in the context of the action/priority being examined" wording) — it does not offer a
  general, context-free "Ask Retention Intelligence" entry point from those two pages. A manager
  interested in a different segment must still reach it via the top nav or the segment picker on
  Retention Intelligence itself.
- **`search_customers`'s "high-value" (no risk qualifier) case** from the P0-4 requirements list
  is exercised via the tool's own existing, unchanged test coverage (Task 02's 39-test suite), not
  via a new keyword route in `agent.py` — no default suggested prompt or audited P0 finding named
  a "high value only" phrasing, so none was added, consistent with the "do not add new features"
  instruction.
- **A true OS-level browser window resize was not available in this sandbox** (same limitation
  noted in `TASK_04_validation_report.md`) — responsive/narrow-width behavior was not re-tested
  this task since none of the five P0 fixes touch layout or CSS.

## 11. Stop condition

All five P0 findings are fixed, tested (142/142 automated tests passing, zero regressions), and
verified live in the real, no-API-key environment end to end. No P1 item from the audit (aggregate
answer's "so what" line beyond what P0-1's fix already added, tracker status hygiene, Champion
segment framing, nav ordering, etc.) was started. No visual redesign, no new page, no new chart, no
ML/analytics change. Stopping here per instruction.
