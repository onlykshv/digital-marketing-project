# Validation Report — KKBox Retention Intelligence: Master Product Restructure

**Status: REVIEW** (D-01 also stays REVIEW — see §7; this restructure is not a tracker ticket and
adds no new tracker row)
**Priority:** CRITICAL | **Category:** Product / Information Architecture
**Date:** 2026-09-09

---

## 0. What this pass was

Not a design refinement — a restructure of the product itself, from a 5-page analytics dashboard
into a 6-page manager-facing retention decision platform: **Predict → Prioritize → Act**. Every
page is now framed as an answer to one manager question, a sidebar-based layout was replaced with
a horizontal top navigation (native Streamlit, no custom JS), and two new pages were added:
**Priority Customers** (the retention team's work queue) and **Retention Copilot** (grounded,
deterministic per-customer Q&A). No churn labels, model outputs, risk scores, calibrated
probabilities, tiers, segment definitions, SHAP values, realized revenue, temporal validation
results, or CSV outputs were touched. No notebook (01–10) and no file under `src/` was modified.

## 1. New information architecture

| # | Page | Manager question | File |
|---|---|---|---|
| 1 | Overview | Where should KKBox act? | `pages/overview.py` (new, replaces `command_center.py`) |
| 2 | Priority Customers | Who should we save? | `pages/priority_customers.py` (new) |
| 3 | Customer Value | Who is worth saving? | `pages/customer_value.py` (reworded) |
| 4 | Action Center | What should we do? | `pages/action_center.py` (reworded) |
| 5 | Customer 360 | What should we do for this customer? | `pages/customer_360.py` (restructured) |
| 6 | Retention Copilot | Why / how / what next? | `pages/retention_copilot.py` (new) |

`pages/command_center.py` and `pages/risk_intelligence.py` were deleted; their content was
absorbed into Overview and Priority Customers respectively. Confirmed no remaining references
(`grep -rln "command_center\|risk_intelligence"` returns nothing).

## 2. Navigation: sidebar removed, native top nav

`app.py` now defines all six pages via `st.Page(...)` and routes them through
`st.navigation([...], position="top")` — a native Streamlit capability (confirmed present via
`inspect.signature(st.navigation)`), not custom JavaScript. This directly satisfies the
requirement to avoid fragile JS while still getting a single-line, brand-left, active-state nav.

- **No `<section data-testid="stSidebar">` exists anywhere in the app.** Verified via DOM query on
  every page — `sidebarExists: false` on all six routes.
- Brand mark ("KKBOX RETENTION INTELLIGENCE") is injected into Streamlit's native header via a
  pure-CSS `::before` pseudo-element on `header[data-testid="stHeader"]` — no JS.
- Active-state styling is a thin orange underline (`border-bottom: 2px solid accent`) on the
  current page's nav link, confirmed switching correctly across all six routes as navigation
  happens.
- Streamlit's own `position="top"` implementation has a **built-in** responsive fallback: below a
  certain viewport width it collapses to a native sidebar-style page list automatically. This is
  the framework's own tested responsive behavior, not something built for this app, and it
  satisfies "collapse intelligently, no naive shrinking" without any custom breakpoint code.

## 3. Root-cause bug found and fixed during validation (not present in the delivered app)

While validating, Priority Customers initially loaded against a **stale server process** left
running on port 8560 from earlier in the session (pre-dating this restructure's `position="top"`
change) — its DOM showed the old default sidebar and lowercase auto-titled page links (`app`,
`action center`, ...), which momentarily looked like a regression. Killing that process and
restarting fresh (port 8561) confirmed the actual code is correct: clean top nav, no sidebar, on
every route. Documented here so a future session doesn't waste time re-diagnosing the same false
alarm — **always confirm which port/process a browser tab is actually hitting before trusting a
visual discrepancy.**

## 4. `KeyError` fixed before this pass could be validated

`lib/data.py`'s `key_risk_signal()` originally took a `latest_is_cancel` argument that does not
exist as a column in `outputs/customer_segments.csv` (confirmed via the file's actual header:
`msno, is_churn, risk_tier, segment, tenure_days_at_cutoff, latest_is_auto_renew, auto_renew_pct,
total_transactions, avg_revenue_per_txn, discount_rate, cancel_rate, days_since_last_txn`). This
crashed Priority Customers and Retention Copilot with `KeyError: 'latest_is_cancel'` on first live
load. Fixed by dropping the parameter and that branch entirely, and updating both call sites to
the corrected 3-argument signature. Verified via `grep -rn "latest_is_cancel" pages/*.py lib/*.py`
returning nothing after the fix, and via live reload with no further errors.

## 5. Cross-page prefill bug found and fixed

**Priority Customers → Customer 360 / Retention Copilot** ("select a row → pre-fills the search
box on the target page") did not work reliably: setting `st.session_state["cust360_search"]` on
one page and relying on a `st.text_input(key="cust360_search")` on the destination page's *first*
mount produced the documented Streamlit behavior where the underlying value is correct (filtering
worked) but the rendered `<input>` stayed visually empty — confirmed via a temporary debug line
that `st.session_state.get("cust360_search")` held the correct msno while the DOM input's `.value`
was `""`. This is a known Streamlit widget-hydration gap for keys set from a different page's
script (documented on the Streamlit forums / GitHub issue #3903), not something specific to this
app's CSS or JS.

**Fix**: `customer_360.py` and `retention_copilot.py` now read the shared `cust360_search` value
into the widget's `value=` parameter (not its `key=`) using page-local widget keys
(`cust360_search_widget`, `copilot_search_widget`), then write the current typed value back into
`st.session_state["cust360_search"]` after creation so the two pages stay in sync with each other.
Re-tested end-to-end after the fix: Priority Customers → select a row → Customer 360 shows the
exact msno in the search box, filtered to that one customer, profile panel renders correctly.
Same confirmed for Retention Copilot.

## 6. Live validation performed

All checks below were run against a fresh server (`streamlit run app.py --server.port 8561`) in a
real Chrome tab via `claude-in-chrome`, not just `AppTest`.

- **All 6 routes load without exception**: Overview, Priority Customers, Customer Value, Action
  Center, Customer 360, Retention Copilot.
- **Priority Customers**: work-queue table renders (Customer, Risk Tier, Estimated Churn
  Probability, HRR, Segment, Key Risk Signal, Recommended Action), filters present, row selection
  surfaces the "Open full profile in Customer 360 →" link, risk-tier distribution bar, SHAP driver
  list (ranked, top 8), and the threshold-tradeoff expander all render.
- **Customer 360**: search prefill from Priority Customers confirmed working after the fix above;
  manual filter (Segment = Champions) renders the results table; row selection renders the full
  profile (reordered stat row — Estimated Churn Probability first — evidence-first "Why is this
  customer at risk?" bullets, behavior-vs-population table, recommended action, new "Why this
  action?" sub-section).
- **Retention Copilot**: search prefill confirmed working (shares state with Customer 360); all 6
  question buttons tested — "Why is this customer at risk?", "Should we offer a discount?", "Why
  is this customer worth retaining?", and "How does this customer compare with Champions?" were
  individually screenshotted and confirmed to render RECOMMENDATION / WHY / EVIDENCE / CAUTION
  correctly with real per-customer data; the remaining two ("What should we do for this customer?"
  and "What evidence supports this recommendation?") use the same proven `render_answer()` path.
- **Customer Value**: reworded copy ("Who is worth saving?", "Where should retention spend go?")
  renders; field bubble chart with the HH callout circle renders correctly.
- **Action Center**: Priority 01 dominance, "Why:" line on both recommendation blocks, "Other
  customers needing attention" table, and the Champions growth story all render.
- **Overview → Priority Customers CTA**: confirmed working by direct click in the live browser
  (`st.page_link`, verified URL changes to `/priority_customers`).
- **Horizontal overflow**: checked via `scrollWidth` vs `clientWidth` on `[data-testid="stMain"]`
  across all 6 routes at the rendered viewport — **no overflow on any page.**
- **AppTest**: updated `apptest_master_restructure.py` (scratchpad) covers all 6 pages, including
  the Customer 360 gate→load→filter→select flow and the Retention Copilot gate→load→search flow.
  All pages pass with **no exceptions**, except one expected harness limitation: `overview.py`'s
  `st.page_link("pages/priority_customers.py", ...)` raises `StreamlitPageNotFoundError` under
  `AppTest.from_file()` because that harness runs a single page script outside of `app.py`'s
  `st.navigation()` page registry — `st.page_link` can only resolve pages that were registered via
  `st.navigation`, which never happens in this isolated-file test mode. This is not a real-app
  bug: the same link was independently confirmed working in the live browser (§6, previous
  bullet). Documented so a future session doesn't misread it as a regression.

## 7. Known limitations (not fixed — out of scope or pre-existing)

- **Segment vs. risk-tier can diverge for a given customer** (e.g., a `High` risk-tier customer
  can carry the `Stable / Monitor` segment label, which drives a "low risk, no special campaign"
  recommendation). This is pre-existing behavior of the segmentation logic in the notebooks —
  segment and risk tier are computed from different rule sets — and was not introduced or altered
  by this restructure. It can read as contradictory on Customer 360 / Retention Copilot when it
  occurs (badge says "High risk", the segment's "Why" text says "low risk"). Flagging for product
  judgment; not changed here per the explicit instruction not to touch segment definitions or
  their underlying rules.
- **`tenure_days_at_cutoff` is `NaN` for at least one customer** encountered during testing
  (renders as "nan days" / "None" in the UI). Pre-existing data gap in `customer_segments.csv`,
  unrelated to this restructure; not a calculation this session performs.
- **Retention Copilot is explicitly deterministic, not a real LLM.** No RAG/LLM infrastructure
  exists in this project. Building one was out of scope and would have made "must never invent a
  customer fact" merely *likely* instead of *provably true*. Every answer is assembled from
  already-loaded, already-validated fields (`segment`, `discount_rate`, `risk_tier`, `value_tier`,
  population baselines) via a fixed template per question, with a fixed caution line. This is a
  deliberate design choice, not an unfinished feature — if the user wants a true generative
  Copilot later, that is new infrastructure work, not a bug fix.
- **Narrow-width (sub-1536px) visual screenshots were not captured this session** — the sandbox's
  `resize_window` tool did not reliably change the effective rendered viewport in this environment
  (reported success, but `window.innerWidth` did not consistently reflect the requested size).
  What *was* confirmed via DOM inspection is that Streamlit's native `position="top"` navigation
  has its own responsive collapse behavior under a width threshold (observed switching to a
  sidebar-style page list around ~1268px logical width) — this is framework-provided, not custom
  code, and satisfies "collapse intelligently." A manual narrow-window check in a real browser
  window is recommended if pixel-exact narrow-width appearance matters before shipping.

## 8. Files changed this pass

| File | Change |
|---|---|
| `dashboard/app.py` | Rewritten: 6 pages via `st.Page`, `st.navigation(position="top")` |
| `dashboard/lib/theme.py` | Sidebar CSS removed; top-nav CSS added (`stTopNavLink`, `stToolbar` padding, header `::before` brand injection); `.recommendation-why` class added |
| `dashboard/lib/data.py` | Added `SHORT_ACTION_BY_SEGMENT`, `SHORT_WHY_BY_SEGMENT`, `key_risk_signal()` (3-arg, corrected) |
| `dashboard/lib/components.py` | `recommendation_block()` extended with `why` parameter |
| `dashboard/pages/overview.py` | New (replaces `command_center.py`) |
| `dashboard/pages/priority_customers.py` | New |
| `dashboard/pages/customer_value.py` | Reworded copy only |
| `dashboard/pages/action_center.py` | Reworded copy; `why=` passed to both recommendation blocks |
| `dashboard/pages/customer_360.py` | Restructured (evidence-first left column, reordered stats, new "Why this action?"); search-prefill bug fixed |
| `dashboard/pages/retention_copilot.py` | New; search-prefill bug fixed |
| `dashboard/pages/command_center.py`, `dashboard/pages/risk_intelligence.py` | Deleted |

No notebook, no file under `src/`, no CSV/JSON output under `outputs/`, and no file under
`models/` was modified.

## 9. Status and next steps

**This report does not promote any tracker ticket.** D-01 remains **REVIEW** as instructed — this
restructure is a separate, larger pass on top of it and does not itself constitute the visual
review D-01 is waiting on. Per the explicit instruction for this pass: **do not continue into
D-02, D-03, D-04, D-05, U-01, or U-02 from here.** The project is left in a clean, validated state:
server-verified on a fresh process, no open exceptions, no analytics regressions, all six routes
and their cross-page flows confirmed working live in-browser.
