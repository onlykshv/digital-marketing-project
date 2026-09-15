# Validation Report — P1-07: Retention Intelligence Hero Experience

**Status: REVIEW** (not DONE — per instruction, DONE is reserved for after independent sign-off).
**Tracker:** `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, row P1-07.
**Date:** 2026-09-11

---

## 0. Method

Before changing anything: re-read `test_cases/TASK_04_validation_report.md`,
`test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md`, `test_cases/TASK_06_P0_FIXES_validation_report.md`,
and the current, post-Task-06 state of `dashboard/lib/agent.py`, `dashboard/lib/components.py`,
`dashboard/lib/theme.py`, and `dashboard/pages/retention_copilot.py` in full. P1-07's row in the
tracker (`task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`) was read in full —
its Issue, Claude Fix Prompt, and Acceptance Criteria columns are quoted where relevant below.

This report distinguishes **implementation facts** (what the code now does, verifiable by reading
it), **observed test results** (what actually ran and what it actually printed), **limitations**
(honestly-stated gaps, including tooling constraints in this environment), and **design judgment**
(a call I made and the reasoning behind it, which a reviewer may reasonably weigh differently).

---

## 1. Concrete UX problems identified before writing any code

Per instruction 4 ("do not assume a visual change is automatically an improvement — identify
concrete UX problems first"), the following were the actual, specific gaps found by reading the
current implementation and cross-referencing `TASK_05_PRODUCT_READINESS_AUDIT.md`:

1. **No orienting signal before a question is asked.** The page had no equivalent of Overview's
   "here's the current state" framing — a manager landed on a header and an empty search box,
   with no visible sign the assistant was already grounded in anything, until they picked a
   context or asked a question. This is the literal first step of the target mental flow ("WHAT
   IS HAPPENING") and it was structurally absent in general mode.
2. **The data-loading mechanism dominated the first screen.** A full-width `st.info` box plus a
   `type="primary"` button, both about internal infrastructure ("~971K rows... loaded once for
   this session"), rendered directly under the header, before any context or question — the
   single most "this is a data-loading utility" moment on the page, ahead of anything that reads
   as a decision-support product.
3. **Segment context had no "take action" link; customer context did.** Confirmed by reading the
   code: `if cust_ctx: ... st.page_link("pages/customer_360.py", ...)`, but
   `elif segment_choice: theme.context_strip(...)` and nothing else. A manager asking a
   segment-level question had no click-through to the actual customers in that segment — an
   asymmetry `TASK_05_PRODUCT_READINESS_AUDIT.md` §12 (P1 #8) had already flagged as a real gap in
   "Links into Customer 360 and Priority Customers."
4. **General-mode suggested questions offered two buttons that can never work as clicked.**
   "Why is this customer at risk?" and "What should we do about this customer?" were present as
   default buttons in general mode (no customer selected), where — even after Task 06's fix — they
   can only ever produce a "please select a customer" guidance message, never a real evidence-
   backed answer. Presenting them as equal-weight, clickable "suggested questions" alongside four
   that genuinely work is a false equivalence that undermines "the flow should make this obvious
   within seconds."
5. **No visual distinction between Finding, Evidence, and Confidence/Caution.** Every labeled
   line in an answer (`components.agent_response_block`) rendered with identical bold-label
   styling — the one-sentence recommendation/headline had no more visual weight than a caution
   footnote. P1-07's own acceptance criteria explicitly requires "evidence/actions distinct."
6. **A real, if currently narrow, honesty gap in `agent.py`.** `_deterministic_fallback`'s
   customer-context branch said "I couldn't find that customer in the scored customer base." even
   when the actual reason a lookup couldn't happen was that customer-level data hadn't been
   loaded yet (`ctx.customer_df is None`) — a different fact, incorrectly presented as the
   guardrail's required not-found string. Not reachable through the live page today (the page
   only ever sets `selected_customer_id` once `customer_df` is already loaded), but reachable
   through `agent.ask()` directly (exactly what one of Task 06's own tests exercises), and
   therefore a real correctness issue in the public function, not a hypothetical one.

Everything else the task's checklist asks to audit — free-text experience, empty-state copy,
customer/segment badge treatment, the "You asked" / answer distinction, provenance captions — was
re-read and judged **already correct**: clear, honest, grounded, and consistent with the rest of
the product. None of it was changed. Per instruction ("if something is already correct, leave it
alone"), the diff below is scoped to the six problems above only.

---

## 2. What changed, and why each change was necessary

### 2.1 `dashboard/lib/agent.py`

- **Fixed problem #6.** `_deterministic_fallback`'s customer-context branch now checks
  `ctx.customer_df is None` first and returns the same honest "hasn't been loaded yet" guidance
  already used elsewhere (factored into one shared constant, `_LOAD_DATA_GUIDANCE`, so the wording
  is identical everywhere the condition can arise — it previously existed as two separately-typed
  copies from Task 06). The genuine not-found path (`cust_result["ok"] is False` with data
  actually loaded) is completely unchanged and still returns the exact required string "I
  couldn't find that customer in the scored customer base."
- No tool, schema, dispatch table, or terminology logic was touched. `agent_tools.py`,
  `agent_tool_schemas.py`, and `llm_provider.py` are untouched.

### 2.2 `dashboard/lib/components.py`

- **Fixed problem #5.** `agent_response_block` now classifies each labeled line into one of three
  tiers by its existing, already-known label name (never by parsing/re-deriving anything new):
  - **Finding** (`Recommendation:` / `Headline:`) — rendered larger, bold, navy — the one thing to
    read at a glance.
  - **Evidence/Action** (`Evidence:`, `Why:`, `What to do:`, `What to avoid:`, `Result summary:`,
    `Recommended next step:`, and any other labeled line) — unchanged, normal bold-label text.
  - **Confidence/Caution** (`Confidence/basis:`, `Confidence:`, `Caution:`) — now rendered via
    `st.caption` — present, readable, but visually subordinate to the finding and the evidence.
  - This is **deliberately bounded**: it classifies by the small set of labels `agent.py` already,
    consistently produces across every answer shape (customer, segment, aggregate, search-list,
    segment-ranking) — it does not introduce a new answer template, a new data structure, or a
    second way to build an answer. The full "Finding → Evidence → Why it matters → Recommended
    action → Confidence/limitations → Next step" template unification is explicitly P1-11's job
    (`task_1`'s own tracker row, "Evidence → Recommendation Presentation") — going further here
    would duplicate that ticket's scope, so this stops at "visually distinct," not "redesigned."
- `priority_list`, `recommendation_block`, `copilot_answer_block`, `secondary_story` — all
  unchanged.

### 2.3 `dashboard/pages/retention_copilot.py`

- **Fixed problem #1.** A `context_slot = st.container()` is now reserved immediately under the
  header (the same deferred-fill pattern already established and proven for the empty-state slot
  in this exact file since Task 04 — not a new mechanism). It is filled, later in the script, once
  `cust_ctx`/`segment_choice` are known, with one of three states:
  - customer in focus → unchanged content (badges + "Open full profile in Customer 360 →").
  - segment in focus → unchanged context strip, **plus the new take-action button** (§2.3, next
    bullet).
  - **general (nothing selected) → new.** A context strip reading "Grounded in the full scored
    base · `<N>` customers · `<N>` High risk · `<pct>` churn" — the exact same `risk_summary`
    fields (`n_customers_scored`, `risk_tiers`, `actual_churn_rate`) Overview already reads via
    the identical `{t["tier"]: t for t in risk_summary["risk_tiers"]}` pattern, formatted with the
    same `theme.fmt_count`/`theme.fmt_pct` functions — no new calculation, no new data load,
    reusing the aggregate data this page was already loading unconditionally.
- **Fixed problem #3.** When a segment is in focus, a new button —
  `f"View {segment_choice} customers in Priority Customers →"` — sets
  `st.session_state["pending_filter"] = {"segment": [segment_choice]}` and calls
  `st.switch_page("pages/priority_customers.py")`. This is the *exact* `pending_filter` mechanism
  Task 06 already built and proved for the Overview/Action Center CTAs and for
  `agent_response_block`'s own "View all N matching customers" link — no new deep-link
  infrastructure was introduced.
- **Fixed problem #2.** The data-loading block is now a plain `theme.recede(...)` note next to a
  default (not primary) button, in a `[3, 1]` column split — same trigger, same effect
  (`st.session_state["lookup_loaded"] = True; st.rerun()`), same button label ("Load customer
  data"), only quieter and shorter copy (the "~971K rows" figure was dropped — a manager doesn't
  need the row count to understand "this loads once and then customer questions work").
- **Fixed problem #4.** General-mode suggested questions are now two labeled groups
  (`theme.eyebrow("See what's happening")` / `theme.eyebrow("Find who needs attention")`, reusing
  the existing eyebrow primitive, not a new component) covering the four questions that always
  work without a customer selected. "Why is this customer at risk?" / "What should we do about
  this customer?" are no longer offered as general-mode buttons; a plain `theme.recede(...)` line
  underneath ("Search for a customer above, or pick a segment, to ask why a specific one is at
  risk or what to do about it") replaces them. **Capability is unchanged** — `agent.py`'s guidance
  path for exactly this phrasing (added in Task 06, untouched here) still answers it honestly if a
  manager types it as free text; only what's *suggested* as a first click changed. Customer-mode
  and segment-mode suggested-question lists are **byte-identical to before** — they were already
  correct.
- The critical ordering invariant from Task 04 — `empty_state_slot` reserved *before* any button
  click is handled, so a same-render click never shows a stale empty state next to its own answer
  — is preserved exactly; the only change around it is that it now guards two rendering branches
  (customer/segment's flat button grid vs. general mode's two groups) instead of one.
- No change to the customer-search resolution logic, the `copilot_context_id` staleness-clearing
  logic, the free-text input, the answer-invocation block, or the bottom methodology disclosure
  (`caveats.render_caveats(["hrr"])`, added in Task 06) — all read, judged correct, left alone.

---

## 3. Files changed

| File | Nature of change |
|---|---|
| `dashboard/lib/agent.py` | One honesty fix (customer-context + no-data-loaded branch); one text-constant factor-out (`_LOAD_DATA_GUIDANCE`) with no behavior change to the two sites already using it |
| `dashboard/lib/components.py` | `agent_response_block` gained a 3-tier Finding/Evidence/Confidence rendering split; everything else in the file is unchanged |
| `dashboard/pages/retention_copilot.py` | Restructured: deferred context slot (always-present grounding), de-emphasized load-data gate, segment take-action button, general-mode question grouping |
| `tests/test_retention_intelligence_ui.py` | 2 existing tests updated to match corrected/changed behavior; 9 new regression tests added (§5) |

## 4. Files deliberately NOT changed

- `dashboard/lib/agent_tools.py`, `dashboard/lib/agent_tool_schemas.py`, `dashboard/lib/llm_provider.py`
  — no tool, schema, or provider logic was touched; the deterministic grounding architecture is
  identical to Task 06's state.
- `dashboard/lib/copilot_engine.py`, `dashboard/lib/copilot_data.py`, `dashboard/lib/data.py`,
  `dashboard/lib/caveats.py` — read, unaffected by any P1-07 change.
- `dashboard/lib/theme.py` — every primitive used (`context_strip`, `eyebrow`, `recede`,
  `fmt_count`, `fmt_pct`, `badge`) already existed; none needed a new CSS class or a new function.
- `dashboard/pages/overview.py`, `dashboard/pages/action_center.py`, `dashboard/pages/customer_360.py`,
  `dashboard/pages/priority_customers.py`, `dashboard/pages/customer_value.py` — none touched;
  their P0-5/P0-2 CTAs and handoffs from Task 06 are consumed by P1-07's new segment button, not
  modified by it.
- `notebooks/`, `models/`, `outputs/`, `src/` — zero changes, confirmed (§6.10).
- `tests/test_agent_tools.py`, `tests/test_agent_orchestration.py` — no new P1-07-specific test was
  needed in these files; the one behavior change in `agent.py` (§2.1) is a text-content change
  already covered by the existing search-route "not loaded" tests' shared constant, and is
  additionally covered by the updated test in `test_retention_intelligence_ui.py` (§5).

---

## 5. Tests executed and exact results

All commands run from the project root, this session, after every code change described above.

```
python tests/test_agent_tools.py               -> 40 passed, 0 failed
python tests/test_agent_orchestration.py        -> 43 passed, 0 failed
python tests/test_retention_intelligence_ui.py  -> 33 passed, 0 failed
python scratchpad/test_copilot.py (original 34-assertion offline suite) -> 34 passed, 0 failed
```

**Total: 150/150 automated tests passing.** (40 + 43 + 33 + 34; the first three numbers are exact
counts printed by each suite's own runner in this session's terminal output, not estimates.)

**New tests added to `tests/test_retention_intelligence_ui.py` for this task** (9 new, plus 2
existing tests updated):

- `test_general_mode_shows_a_grounding_indicator_with_real_numbers` — asserts the new general-mode
  context strip is present and its numbers match `theme.fmt_count`/`risk_summary` exactly (not
  just "some text").
- `test_segment_mode_grounding_indicator_has_a_take_action_link` — clicks the segment selectbox,
  asserts the new button's exact label is present.
- `test_segment_take_action_button_sets_the_real_pending_filter_mechanism` — source-level check
  that it uses the real `pending_filter`/`st.switch_page` mechanism, not a new one.
- `test_customer_mode_still_has_its_existing_customer_360_link` — regression guard that
  restructuring into a deferred slot didn't drop the pre-existing customer link.
- `test_general_mode_suggested_questions_are_grouped_by_flow_step` — asserts both eyebrow labels
  and all four working buttons are present.
- `test_load_customer_data_gate_still_works_and_is_de_emphasized` — asserts the old "~971K rows"
  copy is gone, the gate still functions (button click actually loads data and a customer search
  actually resolves afterward, not just "no exception").
- `test_customer_scoped_questions_no_longer_offered_as_general_mode_buttons` — asserts the two
  buttons are gone from general mode AND that free-text can still ask the same questions and get
  the same honest guidance (capability preserved, only the suggested-button surface changed).
- `test_answer_finding_line_is_rendered_with_stronger_emphasis_than_evidence` — uses
  `AppTest.from_function` to render `components.agent_response_block` directly against a
  synthetic (but realistically-labeled) `AgentResponse`-shaped object, and asserts the Finding
  line's distinct styling and the Caution line's `st.caption` rendering are both present.
- `test_missing_customer_data_handled_gracefully` (updated, not new) — now asserts the honest
  "hasn't been loaded yet" text and explicitly asserts "couldn't find" is **absent** (previously
  it loosely accepted either wording).
- `test_remaining_default_prompts_always_work_with_no_data_loaded` (updated) — narrowed to the two
  prompts that are still buttons in general mode, since the other two are intentionally no longer
  buttons there (covered instead by the new
  `test_customer_scoped_questions_no_longer_offered_as_general_mode_buttons`).

**AppTest sweep, all 6 pages**, run fresh after all changes:

```
overview             EXC: StreamlitPageNotFoundError (pre-existing, already-documented harness
                      limitation -- Overview's own st.page_link, unrelated to and unchanged by
                      this task; confirmed identical on the unmodified Overview page before this
                      task started)
priority_customers    OK
customer_value        OK
action_center          OK
customer_360          OK
retention_copilot     OK
```

No new AppTest failure was introduced anywhere.

---

## 6. Browser flows tested (live, real interaction — not claimed without being performed)

A fresh Streamlit server was started (`streamlit run app.py --server.port 8660`), with
`ANTHROPIC_API_KEY` confirmed absent from the environment (`python -c "import os;
print('ANTHROPIC_API_KEY' in os.environ)"` → `False`) immediately before starting it, and a clean
startup log with no import errors.

1. **Fresh-session empty state** — opened `/retention_copilot` cold: header → "Grounded in the
   full scored base · 971.0K customers · 22.7K High risk · 9.0% churn" (new) → de-emphasized
   load-data note → empty-state hero → "See what's happening" / "Find who needs attention" groups
   (new). Confirmed live.
2. **Segment context** — selected "At-Risk Veteran," confirmed the context strip updated and the
   new **"View At-Risk Veteran customers in Priority Customers →"** button appeared. Clicked it →
   landed on Priority Customers with Segment = At-Risk Veteran actually applied ("6,261 customers
   match these filters"). Confirmed live, end to end.
3. **Finding/Evidence/Confidence tiering** — asked "What should we do with this segment?" (At-Risk,
   Auto-Renew Off): the recommendation line rendered visibly larger/bolder/navy; "Why"/"Evidence"/
   "What to do"/"What to avoid" rendered as normal bold-label text; "Confidence/basis" and
   "Caution" both rendered as muted captions. Confirmed live for a segment answer, and separately
   confirmed live for a customer-context answer ("Why is this customer at risk?" → "Key risk
   signal: Inactive 30+ days." rendered as the large Finding line).
4. **Full required workflow** — Overview → clicked "Ask Retention Intelligence about At-Risk,
   Auto-Renew Off →" → landed on Retention Intelligence with that segment already in focus →
   switched to general mode → asked "Show me high-risk, high-value customers." (after loading
   customer data) → got the Finding headline, 2,413-match count (independently matches the number
   already shown on Overview/Customer Value), and a real 5-row priority list → clicked "Open →" on
   a row → landed on Customer 360 with that exact customer pre-selected, full profile rendered
   correctly (₹8.4K HRR, no `NT$` anywhere) → clicked "Ask Retention Intelligence about this
   customer →" → landed back on Retention Intelligence with that same customer in focus (context
   strip + badges) → asked "Why is this customer at risk?" → correct, grounded, customer-specific
   evidence answer. Every hop in the required
   `Overview → Retention Intelligence → question → evidence → customer results → Customer 360 →
   customer-specific Retention Intelligence` chain was walked live and worked.
5. **Free-text guidance for the now-removed general-mode buttons** — confirmed via automated test
   (§5) rather than re-walked live a second time in the browser, since the underlying mechanism
   (the free-text input → `agent.ask()`) is identical to every other free-text flow already walked
   live in this and prior sessions.
6. **Stale session-state check** — switched context repeatedly (segment → general → customer) in
   the same live session; the existing `copilot_context_id` staleness-clearing logic (unchanged by
   this task) correctly cleared the previous answer every time a genuinely different context was
   selected — no stale answer was observed attached to the wrong context.
7. **Desktop layout / overflow** — confirmed no document-level horizontal overflow at normal
   desktop width (`document.documentElement.scrollWidth === document.documentElement.clientWidth`
   throughout). A narrower-width approximation via render-zoom (the same technique used in
   `TASK_04_validation_report.md` and `TASK_06_P0_FIXES_validation_report.md`, since a true OS
   window resize is not available in this sandbox — see §7) showed no page-level horizontal
   scrollbar either. One visual observation, not a regression, is recorded honestly in §7.

**Known, pre-existing, unrelated rendering quirk observed during this session (not a P1-07
issue):** on a fresh page load in this sandboxed browser, the top nav intermittently renders as a
plain lowercase left-side list ("app / action center / customer 360 / ...") before hydrating into
the real pill-style top nav. This was observed on **both** `retention_copilot` and the completely
untouched `overview` page in the same session, confirming it is a pre-existing Streamlit/sandbox
rendering characteristic (already documented in multiple prior task reports in this project) and
not something this task introduced. Page content below the nav was correct and fully interactive
regardless.

---

## 7. Bugs discovered

1. **The honesty bug in `_deterministic_fallback`** (§1 problem #6, §2.1 fix) — a real, if
   narrowly-reachable, instance of the guardrail's required "couldn't find" string being used for
   a different underlying fact ("not loaded yet"). Found by re-reading the code while auditing
   "Confidence/limitations/provenance" per the task's checklist, not by a test failure.
2. **Two P0-6-era test cases silently assumed the old six-button general-mode grid** — not a
   product bug, but discovered while restructuring: `test_missing_customer_data_handled_gracefully`
   accepted either of two different underlying facts as "close enough," which is exactly the kind
   of looseness that let bug #1 go undetected until now. Tightened (§5).

No other functional bugs were found. No regression was found in any of the 150 automated tests or
any of the seven live browser flows in §6.

## 8. Bugs fixed

Both items in §7 are fixed: the honesty bug in `agent.py` (§2.1), and the loosened test that had
been tolerating it (§5, `test_missing_customer_data_handled_gracefully`).

---

## 9. Remaining limitations (stated honestly)

- **No live LLM path was tested.** `ANTHROPIC_API_KEY` is not configured in this environment
  (confirmed programmatically before starting the server). Every fix and every live browser flow
  in this report exercises the deterministic fallback path — the actual, real behavior a user gets
  today. No LLM-synthesized answer was fabricated or claimed. This is the same, previously-
  documented, carried-forward limitation from Tasks 03/04/06, not a new gap.
- **The context strip's badge row (customer-context case) was not re-tested for narrow-width
  wrapping behavior in depth.** It is pre-existing, unchanged-by-this-task code; a brief
  render-zoom check showed no document-level overflow, but a full narrow-viewport visual audit of
  every badge/label combination was not performed, since it is out of this ticket's scope (no
  content or layout change was made to that specific element) and would duplicate work more
  properly owned by a dedicated visual-polish pass (P2-16 in the tracker).
- **A true OS-level browser window resize is not available in this sandbox** (same limitation
  noted in Tasks 04 and 06's reports) — the narrower-width check in §6.7 used a render-zoom
  approximation, not a genuine device-width test.
- **The Finding/Evidence/Confidence tiering is intentionally bounded**, not a full redesign of the
  answer template — see §2.2. A reviewer working on P1-11 should treat this as a foundation to
  extend, not a finished, final presentation.
- The general-mode "See what's happening" / "Find who needs attention" grouping and the removal of
  the two customer-scoped buttons from general mode is a **design judgment**, not a mechanically
  forced change — a reasonable reviewer could instead prefer keeping all six buttons and relying
  solely on the honest guidance message (Task 06's fix) to handle the customer-scoped ones. The
  reasoning for removing them here (false equivalence with four buttons that always work) is
  stated in §1 problem #4; it is a judgment call about UX clarity, not a bug fix.

---

## 10. Confirmation that P1-08 and later tasks were NOT started

No file under `dashboard/`, `tests/`, `test_cases/`, or `task_1/` other than the ones listed in
§3 was created or modified. No cross-page navigation restructuring beyond the one segment
take-action button (which reuses P0-5's existing mechanism, not a new one) was attempted. No
assistant "identity/personality" treatment (P1-09), no page-by-page numbers-density pass beyond
Retention Intelligence itself (P1-10), no LLM hardening work (P1-12), no demo-flow-specific
changes (P1-13), no reusable-architecture documentation (P1-14), and no integrated final QA pass
(P1-15) was performed. Work stopped at the boundary of P1-07's own scope as read from the tracker.

---

## 11. Tracker update

`task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, row **P1-07** only: Status
changed from `TODO` to `REVIEW`. All other rows (P1-08 through P2-16) left at `TODO`, unchanged.
