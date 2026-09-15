# Validation Report — P1-08: Manager Command Workflow

**Status: REVIEW** (not DONE — reserved for independent sign-off).
**Tracker:** `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, row P1-08.
**Date:** 2026-09-11

---

## 1. Exact requirement addressed

From the tracker, row P1-08:

- **Issue:** "The six pages can still feel like separate screens instead of one retention
  operation workflow."
- **Claude Fix Prompt:** "Create a coherent Overview → Priority Customers → Customer 360 →
  Retention Intelligence journey. Preserve deep links and context, prevent stale session state,
  reuse existing tools/data, and avoid duplicated analytical logic. Validate fresh navigation,
  handoffs and refresh."
- **Acceptance Criteria:** "Portfolio signal leads to cohort; cohort leads to customer; customer
  leads to assistant; context survives handoffs; no stale state; browser + full tests pass."

This report addresses exactly that four-page chain. Per instruction, scope was held to what the
acceptance criteria literally names — Action Center (one of the six pages, but not named in this
specific chain) was deliberately not touched; see §4.

---

## 2. Audit — what was actually broken (not assumed from the tracker)

Per instruction ("do not assume the tracker accurately describes the current implementation"),
each leg of the named chain was read from the current code, not inferred:

| Leg | Mechanism found | Working? |
|---|---|---|
| **Portfolio signal → cohort** (Overview → Priority Customers) | `st.page_link("pages/priority_customers.py", label="View Priority Customers →", icon=None)` — a **plain, static link carrying no filter context at all** | **No.** Clicking it from under "THE BIGGEST ACTIONABLE OPPORTUNITY: At-Risk, Auto-Renew Off" dropped the manager into Priority Customers' generic default view (Risk tier High+Medium, no segment) — not the cohort the signal was actually about. |
| **Cohort → customer** (Priority Customers → Customer 360) | Row selection sets `st.session_state["cust360_search"] = picked["msno"]`, then renders `st.page_link("pages/customer_360.py", label=f"Open full profile for {msno}… in Customer 360 →")` | **Yes**, already correct — re-verified live and via the full AppTest sweep (§6). |
| **Customer → assistant** (Customer 360 → Retention Intelligence) | `st.page_link("pages/retention_copilot.py", label="Ask Retention Intelligence about this customer →")`, reading the same shared `cust360_search` key | **Yes**, already correct — unchanged since Task 04, re-verified live (§6). |
| **Context survives handoffs** | The shared `cust360_search` / `pending_filter` / `copilot_segment_choice` session-state keys, already established across Tasks 04–06 and P1-07 | **Yes** for the three legs that already worked. **No** for the one broken leg (there was no context to carry in the first place). |
| **No stale state** | `pending_filter` is popped (consumed once) on every read, established in Task 04/06 | Mechanism itself was already correct; needed to be **reused**, not reinvented, for the new leg. |

**The one concrete, fixable gap:** Overview's link into Priority Customers did not carry the
page's own headline "portfolio signal" — the biggest actionable opportunity segment — as a
starting filter. That is the entire implementation scope of this task.

No other gap was found in the named chain. The three already-working legs were **not modified.**

---

## 3. Implementation summary

**`dashboard/pages/overview.py`** — the static `st.page_link("pages/priority_customers.py",
label="View Priority Customers →", icon=None)` was replaced with:

```python
if st.button(f"View {top_opportunity['priority_group']} customers in Priority Customers →", key="view_priority_customers_overview"):
    st.session_state["pending_filter"] = {"segment": [top_opportunity["priority_group"]]}
    st.switch_page("pages/priority_customers.py")
```

This is the **exact same mechanism** already established and proven in Task 04 (search-results →
Priority Customers) and Task 06 (Action Center / Retention Intelligence segment CTAs → Priority
Customers): the `pending_filter` session-state convention, consumed once (popped) by
`priority_customers.py`'s own existing, unmodified code. No new session-state key, no new
filtering logic, no new deep-link function was introduced — `top_opportunity` was already loaded
and in scope on this page (used one line above, for the existing "Ask Retention Intelligence about
{segment}" button).

That is the **entire code change**. No other file's logic was touched.

---

## 4. Files changed / deliberately not changed

### Changed

| File | Change |
|---|---|
| `dashboard/pages/overview.py` | One static `st.page_link` replaced with one filter-carrying button, reusing the existing `pending_filter` mechanism (§3) |
| `tests/test_manager_workflow.py` | **New.** 8 tests for this task (§5) |
| `tests/test_retention_intelligence_ui.py` | One existing test updated (§5) — its assertion had encoded the *old*, broken behavior as expected |
| `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx` | Row P1-08 status: `TODO` → `REVIEW` |

### Deliberately NOT changed

- **`dashboard/pages/priority_customers.py`** — its `pending_filter` consumption logic already
  correctly handles a segment-only filter (proven by Task 06's own tests and re-proven here,
  §5); it needed to be *reused*, not modified. Touching it would have risked exactly the
  "duplicated analytical logic" the task explicitly forbids.
- **`dashboard/pages/customer_360.py`, `dashboard/pages/retention_copilot.py`** — both legs they
  own (`cust360_search` handoffs) were already correct; read in full, unmodified.
- **`dashboard/pages/action_center.py`** — Action Center is one of "the six pages" named in the
  Issue's framing, but it is **not** part of the specific chain the Claude Fix Prompt and
  Acceptance Criteria name ("Overview → Priority Customers → Customer 360 → Retention
  Intelligence"). It already has its own "Ask Retention Intelligence about {segment}" CTA (Task
  06) and was not found to have a broken leg *in the named chain*. Extending Action Center's own
  cross-links further is out of this ticket's literal scope; not started here.
- **`dashboard/lib/agent.py`, `dashboard/lib/agent_tools.py`, `dashboard/lib/agent_tool_schemas.py`,
  `dashboard/lib/llm_provider.py`, `dashboard/lib/copilot_engine.py`, `dashboard/lib/copilot_data.py`,
  `dashboard/lib/data.py`, `dashboard/lib/components.py`, `dashboard/lib/theme.py`,
  `dashboard/lib/caveats.py`** — no tool, schema, terminology, or presentation logic was touched;
  P1-08 is a pure cross-page navigation fix.
- `notebooks/`, `models/`, `outputs/`, `src/` — zero changes (confirmed, §6).

---

## 5. UX / product rationale

Per the product standard in this task's brief: a manager reading Overview's "biggest actionable
opportunity" card learns *which* segment matters most and *why* — but the only click available
from that card led to a **different, unrelated view** (the generic work queue, unfiltered by that
same segment). That is precisely "feels like a separate screen" rather than "one retention
operation workflow": the signal and the action it should lead to were disconnected. The fix makes
the link's own label state exactly what it now does ("View At-Risk, Auto-Renew Off customers in
Priority Customers →") and makes clicking it land the manager on precisely the cohort the signal
was about — closing the "identify who needs attention" step of the target flow (`identify who
needs attention → explain why → quantify what is at stake → recommend what to do → allow the team
to investigate`) with an actual, working click-through, not just a card describing a number.

---

## 6. Tests added and complete test results

**`tests/test_manager_workflow.py`** — new file, 8 tests, all exercising the real, current,
no-API-key environment (no mocking anywhere in this file):

1. `test_overview_view_priority_customers_button_names_the_real_top_opportunity_segment` — the
   button's label matches the *actual* current top-opportunity segment computed from real data
   (`data.priority_opportunities`), not a hardcoded string.
2. `test_overview_priority_customers_button_source_carries_the_segment_filter` — source-level
   check that the exact `pending_filter`/`switch_page` calls are present (AppTest's isolated
   single-page harness cannot itself follow a `switch_page` — the same well-documented limitation
   noted in every prior task's report).
3. `test_overview_no_longer_raises_an_exception_on_a_plain_render` — a genuine, positive
   side-effect: Overview's old static `page_link` unconditionally hit the known AppTest harness
   limitation on *every* plain render (documented in every prior report); the new button only
   calls `switch_page` when clicked, so a plain render is now exception-free.
4. `test_priority_customers_applies_a_segment_filter_carried_from_overview` — seeds
   `pending_filter` exactly as the new button does, confirms the Segment multiselect's value and
   the rendered match-count caption both reflect it.
5. `test_priority_customers_pending_filter_is_consumed_once_not_left_stale` — proves, on the
   *same* session across two reruns, that the filter applies once and then reverts to the page's
   own default on the next unrelated interaction (directly verifying the "no stale state"
   acceptance criterion, not just asserting "no crash").
6. `test_priority_customers_row_selection_still_hands_off_to_customer_360` — regression guard for
   the unmodified "cohort → customer" leg.
7. `test_customer_360_still_links_to_retention_intelligence` — regression guard for the unmodified
   "customer → assistant" leg.
8. `test_all_six_pages_still_load_without_a_new_exception` — full sweep, all six pages.

**One existing test updated**, `tests/test_retention_intelligence_ui.py`'s
`test_overview_and_action_center_still_render_without_exception` — it had asserted Overview
*always* raises exactly one specific exception on a plain render (true of the old, broken static
link; no longer true, and no longer *should* be true, of the fixed button). Updated to assert zero
exceptions, matching the corrected behavior.

**Exact results, this session, after every change:**

```
python tests/test_agent_tools.py               -> 40 passed, 0 failed
python tests/test_agent_orchestration.py        -> 43 passed, 0 failed
python tests/test_retention_intelligence_ui.py  -> 33 passed, 0 failed
python tests/test_manager_workflow.py           ->  8 passed, 0 failed
python scratchpad/test_copilot.py (original 34-assertion offline suite) -> 34 passed, 0 failed
```

**Total: 158/158 automated tests passing.**

---

## 7. Browser workflow tested (live, real interaction)

A fresh Streamlit server was started (`streamlit run app.py --server.port 8670`), with
`ANTHROPIC_API_KEY` confirmed absent from the environment immediately before starting it
(`python -c "import os; print('ANTHROPIC_API_KEY' in os.environ)"` → `False`), and a clean startup
log with no import errors.

**The complete named chain was walked live, start to finish:**

1. Opened `/overview` fresh. Scrolled to "THE BIGGEST ACTIONABLE OPPORTUNITY: At-Risk, Auto-Renew
   Off" — confirmed the new **"View At-Risk, Auto-Renew Off customers in Priority Customers →"**
   button renders directly below the existing "Ask Retention Intelligence about..." button.
2. Clicked it → landed on Priority Customers with **Segment = At-Risk, Auto-Renew Off already
   applied** (Risk tier still its own default, High + Medium) → caption read **"113,820 customers
   match these filters"** — an exact match to the "113.8K customers" figure Overview's own card
   already showed for that same segment, confirming the cohort is genuinely the signal's cohort,
   not an approximation.
3. Every visible row in the (scrolled) table showed `Segment: At-Risk, Auto-Renew Off` — the
   filter was real, not cosmetic.
4. Selected a customer row → "Open full profile for `<id>`… in Customer 360 →" appeared → clicked
   it → landed on Customer 360 with that exact customer pre-selected (after the page's own,
   separate, pre-existing data-load gate) → full profile rendered correctly (HIGH RISK / HIGH
   VALUE / At-Risk Veteran badges, ₹8.4K HRR, no `NT$` anywhere).
5. Clicked "Ask Retention Intelligence about this customer →" → landed on Retention Intelligence
   with that same customer already in focus (context strip + badges, correct).
6. **No stale state, confirmed live**: navigated to Priority Customers a second time via the plain
   top-nav link (not a deep link) — the Segment filter showed its own default ("Choose options" —
   empty), and the match count reverted to the full 129,735-customer High+Medium default view, not
   the leftover 113,820-customer filtered view from step 2.

This is the exact, complete
`Overview → Priority Customers → Customer 360 → Retention Intelligence` chain the acceptance
criteria describes, walked live, with every leg (the three pre-existing ones and the one new fix)
confirmed working.

---

## 8. No-API-key behavior

Confirmed throughout §7 — every step of the live walkthrough ran with `ANTHROPIC_API_KEY` absent
from the environment. This task made no change to `agent.py`, `llm_provider.py`, or any tool —
the deterministic fallback path is untouched and was not re-tested beyond what §7 already
exercises implicitly (Customer 360 and Retention Intelligence both render grounded, correct
content with no LLM configured, exactly as before).

---

## 9. Regressions checked

- **Full automated suite**: 158/158 passing (§6) — includes every pre-existing test from Tasks
  02–07, none skipped or removed except the one intentionally corrected assertion (§6).
- **Navigation**: top nav, all six pages, confirmed loading via the full AppTest sweep
  (`test_all_six_pages_still_load_without_a_new_exception`) and live spot-checks in §7.
- **Deep links**: the `pending_filter` mechanism's other two existing producers (Action Center's
  and Retention Intelligence's own segment CTAs, and the search-results "View all N matching
  customers" link) were not touched and are unaffected — they write to the exact same
  session-state key this task's new button also writes to, with no collision risk since only one
  navigation happens at a time.
- **Session state**: `cust360_search`, `copilot_segment_choice`, `copilot_context_id`,
  `lookup_loaded` — none touched by this task's one-file change; all confirmed still behaving
  correctly in the live walkthrough (§7).
- **Terminology**: Model Risk Score / Estimated Churn Probability / HRR / High-Risk Historical
  Revenue Exposure — none of this task's changes touch any text that uses these terms; unaffected.
- **Currency formatting**: confirmed ₹ (not `NT$`) throughout the live walkthrough (§7 step 4);
  this task did not touch any currency-formatting code path.
- **Customer/segment context**: both context types confirmed working correctly and independently
  in the live walkthrough; no cross-contamination observed.

---

## 10. Known limitations

- **Action Center was not connected further into this chain.** It already has a working CTA into
  Retention Intelligence (Task 06); it has no CTA into Priority Customers or Customer 360. This
  was a deliberate scope decision (§4), not an oversight — the acceptance criteria's chain does
  not name Action Center, and the task instructions explicitly warn against redesigning beyond
  what's asked. If a future ticket wants Action Center folded into the same coherent journey, the
  identical `pending_filter` pattern used here would apply directly.
- **Priority Customers' row-selection interaction remains two clicks** (select the row, then click
  the resulting "Open full profile…" link) rather than one. This was considered and deliberately
  left unchanged: it is a pre-existing, already-validated (Tasks 04–07), functioning mechanism,
  and Streamlit's `st.dataframe` selection API has no native "click a row to navigate directly"
  affordance the way `components.priority_list`'s per-row buttons do — converting Priority
  Customers' actual work-queue table to per-row buttons would be a materially larger UI change
  than this ticket's literal scope ("smallest coherent implementation").
- No true OS-level browser window resize was available in this sandbox for a narrow-width check;
  this task made no layout or CSS change, so none was attempted (consistent with the "smallest
  coherent implementation" instruction — nothing here touches density or responsive layout).

---

## 11. Explicit statement that P1-09 was NOT started

No file related to "Assistant Identity & Personality" (P1-09's tracker row) was created or
modified. No naming/voice/visual-identity treatment of the assistant was added. Only
`dashboard/pages/overview.py`, `tests/test_manager_workflow.py`,
`tests/test_retention_intelligence_ui.py`, and the tracker's P1-08 status cell were changed. Work
stopped at the boundary of P1-08's own scope as read from the tracker.
