# Validation Report — D-02 / D-03 / D-04 / D-05 / U-01: Master Visual Polish + Customer 360 Pass

**Status: REVIEW** for all five (D-02, D-03, D-04, D-05, U-01) — none marked DONE, per instruction.
**Priority:** CRITICAL | **Category:** Product Design
**Date:** 2026-09-09
**Scope:** One unified visual/product-polish pass across the 6-page architecture established by the
validated Master Product Restructure. Retention Copilot's own content/feature work was explicitly
NOT started this pass (two one-line bug fixes to its search were made — see §9).

---

## 1. Design changes (D-02 / global visual direction)

- **Chart language, applied globally, once**: `theme.apply_page_style()`'s Plotly template now
  carries one shared `axis_style` (restrained gridlines, visible axis line, outward ticks,
  quieter tick/label typography) applied to every `xaxis`/`yaxis` on every chart in the app via
  the template, plus a refined legend (smaller, muted) and a navy chart-title color. This means
  every existing chart — Overview's field, Priority Customers' SHAP bars and threshold chart,
  Customer Value's revenue bar and field bubble chart, Action Center's portfolio scatter — now
  shares one coherent visual language without any chart's own code being touched. Presentation
  only: no trace data, aggregation, or calculation changed.
- **Living Retention Field (D-02/§10)**: added `theme.field_status_badge()` — a small, real DOM
  element ("● PRIORITY ZONE IDENTIFIED — HIGH RISK × HIGH VALUE") with a restrained CSS
  `pulseDot` box-shadow animation (2.4s, respects `prefers-reduced-motion`), placed directly above
  Overview's risk×value chart. Deliberately **not** implemented as motion inside the Plotly SVG
  itself — Plotly's shape/annotation layer has no stable, externally-targetable selector across
  reruns, so animating it via external CSS would be exactly the kind of fragile mechanism the
  brief warned against. This is the documented, safer choice: a beautifully static field (already
  established in the prior D-01 pass) plus one small, robust, purposeful pulse next to it.
- **Micro-interactions (D-05)**: nav-link color/background transitions (already present, now
  explicit `transition:` declarations), button hover (subtle shadow lift), expander-summary hover
  (text turns accent-colored), and `st.page_link` CTA hover (bolder, navy on hover) — all pure
  CSS, all survive Streamlit reruns because they live in `apply_page_style()`'s injected
  stylesheet, re-applied identically every script run. `st.dataframe`'s row hover/selection
  highlight is Streamlit's own built-in behavior (the grid is canvas-rendered via glide-data-grid,
  so it cannot be restyled with custom CSS — documented as a limitation in §11, not attempted).

## 2. Information hierarchy changes (D-03 / layout system)

- **Empty states** (§12 of the brief): added `theme.empty_state()` — eyebrow + title + subtitle,
  always says what to do next. Replaces the old bare `theme.recede()` line on Customer 360's
  "nothing searched yet" state, and is now also used for two states that previously had **no**
  explicit handling at all: "no matches" (filters that return zero rows) and "results shown but no
  row selected yet." All three empty states on Customer 360 now guide the manager instead of
  leaving blank space or an unexplained empty table.
- **Section-break consistency**: added one `theme.divider()` on Action Center before "A separate
  story: growth, not risk," matching the divider-then-eyebrow pattern already used everywhere
  else in the app, so Champions reads as a clearly separated growth story rather than a
  continuation of the intervention queue.
- Overview, Priority Customers, Customer Value, and Action Center's information hierarchy (page
  question → key insight → primary evidence → secondary detail → action) was already established
  by the prior D-01 pass and audited here — no structural changes were needed; they already follow
  the brief's target hierarchy rather than a title-then-KPI-cards layout.

## 3. Customer 360 changes (U-01 — the flagship redesign)

This is the largest change in this pass. Before/after:

| | Before | After |
|---|---|---|
| Search area | Full-width labeled `text_input` + 3 labeled `multiselect` columns = 2 visible control rows | 1 row, 4 columns, collapsed labels + placeholders ("Search by customer ID (msno)…", "Segment", "Risk tier", "Value tier") — reads as one compact search bar |
| Nothing searched | A single grey `recede()` sentence | `empty_state()`: "SEARCH FOR A CUSTOMER" / "Find a customer to open their profile" / explicit next steps, including a line noting the Priority Customers handoff |
| Zero matches | Previously unhandled — fell through to an empty table with no explanation | New `empty_state()`: "NO MATCHES" with concrete next steps |
| Results shown, no row picked | Previously unhandled — page just ended after the download button | New `empty_state()`: "SELECT A CUSTOMER" |
| Supporting behavior table | Always visible under the evidence bullets, competing for attention | Moved into a collapsed `st.expander("Behavior vs. the population (detail)")` — the bullets are the 10-15-second read; the table is there for anyone who wants to go deeper |
| Right column | "Recommended action" → "Why this action?" | Renamed to the brief's own headings: **What should we do?** → **Why this action?** → **What should we avoid?** (new) |
| Section heading | "Find a customer" | "What should we do for this customer?" — matches the page's manager question from the restructure |
| Profile entrance | No distinct treatment | The customer-ID title now carries the `.profile-panel` class, which gets the same short `fieldFadeIn` entrance transition already used for `.dash-header`/`.card`/`.recommendation-block` |

**"What should we avoid?"** is new and grounded exactly the way the brief requires: added
`data.AVOID_BY_SEGMENT`, a plain-English inverse restatement of each segment's already-validated
`marketing_objective` / `intervention_intensity` (e.g. for At-Risk, Auto-Renew Off: *"Don't lead
with a discount -- the framework's highest-leverage response here is a low-cost auto-renew nudge,
not a price concession"*). It is a segment-level framework restatement, never a new claim about
the specific customer, and only renders when the segment has a mapped entry.

**Preserved, verified not regressed** (see §7-9): search, all three filters, the HRR range
expander, row selection → profile, the Priority Customers → Customer 360 cross-page handoff, the
`Retention Copilot` shared search state, on-demand lazy loading (`Load customer data` gate), and
`st.cache_data` caching.

**A real, pre-existing bug was found and fixed while validating this redesign** — see §9.

## 4. Chart-system changes (D-04)

Already covered in §1 — one template-level change (`theme.py`'s `axis_style`) rather than
per-chart edits, so it applies uniformly to Overview, Priority Customers, Customer Value, and
Action Center without touching any chart's own code, data, or calculation. Verified visually: all
four pages' charts render with the same restrained gridline/tick/legend treatment.

## 5. Interaction changes (D-05)

Covered in §1. Summary of what was added, all CSS-only, no JavaScript:
- Nav link hover/active transitions (explicit `transition:` timing, ~160ms)
- Button hover (shadow lift, ~150ms)
- Expander summary hover (accent color, ~150ms)
- `st.page_link` CTA hover (bolder + color shift)
- Profile-panel and empty-state entrance fades (reuse the existing `fieldFadeIn` keyframe, gated
  behind `prefers-reduced-motion: no-preference`)
- Field status badge pulse (Overview only, gated behind `prefers-reduced-motion`)

## 6. Responsive behavior

- **1536×864 (desktop target)**: verified live on a fresh server across all 6 routes — see §8.
- **Horizontal overflow**: checked via `scrollWidth` vs `clientWidth` on `[data-testid="stMain"]`
  on Overview, Priority Customers, Customer Value, Action Center, Customer 360 (including with a
  full profile open), and Retention Copilot — **no overflow on any page**.
- **Narrow viewport**: as documented in the prior Master Restructure report, this sandbox's
  browser-resize tool does not reliably change the rendered viewport, so a true narrow-width
  screenshot could not be captured this pass either. What remains true and was re-confirmed: no
  page depends exclusively on hover (the top-nav items, buttons, and page-links are all real
  clickable/tappable elements; hover only adds a cosmetic transition on top of an already-usable
  default state), and Streamlit's native `position="top"` navigation has its own responsive
  fallback to a sidebar-style list below a width threshold, independent of anything built here.

## 7. AppTest results

Ran the same six-page suite used to validate the Master Restructure
(`apptest_master_restructure.py`, scratchpad) against this pass's code, twice — once before and
once after the search-regex fix in §9, to confirm the fix didn't regress anything:

- `action_center`, `customer_value`, `priority_customers`: **OK, no exception** both times.
- `customer_360`: gate → load → filter (Segment = Champions) → dataframe renders: **OK, no
  exception** both times. (`select_rows` is not supported by this AppTest version — a harness
  limitation, not tested via AppTest; covered instead by the live-browser walkthrough in §8.)
- `retention_copilot`: gate → load → empty search: **OK, no exception** both times.
- `overview`: raises `StreamlitPageNotFoundError` on its `st.page_link` call — **expected harness
  limitation** (same one documented in the Master Restructure report): `AppTest.from_file()` runs
  a single page script outside `app.py`'s `st.navigation()` page registry, and `st.page_link` can
  only resolve pages registered through that call. Confirmed **not** a real-app bug via live
  browser (§8).

## 8. Live-browser results

Full walkthrough on a freshly started server (killed all prior processes first, confirmed no
stale-process false alarms this time), viewed in Chrome via `claude-in-chrome`:

- **Overview**: field status badge with pulsing dot renders correctly above the risk×value field;
  chart gridlines visibly lighter/more restrained; "View Priority Customers →" CTA present and
  correctly styled.
- **Priority Customers**: unchanged content, confirmed inheriting the new chart/nav/button styling
  with no regression; work-queue table, filters, and the "Open full profile in Customer 360 →"
  handoff link all render.
- **Customer Value**: field bubble chart renders with the new axis styling; HH-cell halo intact.
- **Action Center**: new divider before the Champions growth story renders as a clean section
  break.
- **Customer 360 (flagship)**: verified end-to-end —
  - Compact one-row search bar with collapsed labels, confirmed visually much shorter than before.
  - "SEARCH FOR A CUSTOMER" empty state renders before any query.
  - Searching surfaces "SELECT A CUSTOMER" once results are shown but nothing picked.
  - Selecting a row opens the full profile: badges, 4-stat header, "Why is this customer at
    risk?" bullets with the behavior table correctly collapsed into an expander, "What should we
    do? / Why this action? / What should we avoid?" all render on the right in that order.
  - **Priority Customers → Customer 360 cross-page handoff re-tested end-to-end** with a real
    customer ID containing regex-special characters (`eh+OR+CX5dybmVcsmK1c2COYyFQKfD5k19TsHC/PWBM=`)
    — this is what surfaced the bug fixed in §9; after the fix, confirmed working correctly
    (search box shows the prefilled ID, table filters to exactly 1 match, row selection opens the
    correct profile).
- **Retention Copilot**: confirmed untouched content still renders correctly (page file was not
  edited this pass beyond the one-line regex fix in §9), inheriting the new global nav/button/chart
  styling automatically.
- **Horizontal overflow**: `scrollWidth`/`clientWidth` checked and equal (no overflow) on all 6
  routes, including Customer 360 with a full profile open.

## 9. A real, pre-existing bug found and fixed during this pass

While re-testing the Priority Customers → Customer 360 handoff with a genuine customer ID
(`eh+OR+CX5dybmVcsmK1c2COYyFQKfD5k19TsHC/PWBM=`), the search returned **zero matches** despite the
ID being correct and correctly prefilled into the search box. Root cause: `pandas.Series.str.contains()`
defaults to `regex=True`, and base64-derived customer IDs routinely contain regex-special characters
(`+`, `/`). A `+` in the search string is interpreted as a regex quantifier rather than a literal
character, so it silently fails to match. This bug **predates this pass** (the line was unchanged
from the original implementation) and was not caught earlier because prior tests either used a
short alphabetic query ("AAA") or hand-picked a row for local, in-page selection rather than
re-exercising the actual base64 ID over a cross-page handoff. It was only surfaced now because the
new "no matches" empty state made a silent failure visible instead of an unexplained blank table.

**Fix**: added `regex=False` to all three identical `.str.contains(search, case=False, na=False)`
call sites — `pages/customer_360.py`, `pages/priority_customers.py`, and `pages/retention_copilot.py`
(the last one only because it shares the exact same `cust360_search` session-state value and
pattern; this was a one-line correctness fix, not new Retention Copilot feature work). Re-tested
end-to-end after the fix — confirmed working (§8). This directly protects the "no regression in
customer selection" requirement from §15 of the brief, and would otherwise have silently broken
the handoff for an unpredictable subset of real customer IDs depending on which regex-special
characters happened to appear in them.

## 10. Before/after visual observations

- Overview: same strong hierarchy as the D-01 baseline, now with a small, purposeful "living"
  signal (pulsing priority-zone badge) and visibly calmer chart gridlines.
- Customer 360 is the clearest before/after: previously a large "Find a customer" search form
  with two rows of labeled controls and a lot of surrounding whitespace before any content, then
  (after selection) a profile whose most useful comparison table competed for attention with the
  evidence bullets, and no guidance at all in the "no results" or "no row selected" states. Now:
  one compact search row, three distinct guided empty states, and a profile that reads
  top-to-bottom as a single narrative — who, why at risk, what to do, why, what to avoid — with
  supporting detail intentionally tucked into an expander rather than always on screen.
- Action Center's Champions section now has a visible section break instead of blending into the
  intervention queue above it.

## 11. Remaining limitations

- **Narrow-viewport screenshots**: still not capturable in this sandbox (see §6) — same limitation
  documented in the Master Restructure report. Recommend a manual check in a real browser window
  before shipping if pixel-exact narrow-width appearance matters.
- **Dataframe row hover/selection styling**: Streamlit's `st.dataframe` (glide-data-grid) renders
  to canvas, so its row hover cannot be restyled with custom CSS beyond what Streamlit already
  provides natively. Not attempted, to avoid a fragile hack against an internal implementation
  detail that could break on a Streamlit version bump.
- **Retention Copilot itself was not redesigned this pass**, per the explicit instruction. Its two
  one-line search fixes in §9 are bug fixes to functionality it already had (shared with Customer
  360), not new feature work.
- The pre-existing segment-vs-risk-tier divergence and the occasional `NaN`/`nan days` tenure value
  documented in the prior Master Restructure report are unchanged and still present (both are
  underlying data/segmentation characteristics, out of scope to alter).

## 12. Files changed / added — and analytical files confirmed untouched

| File | Change | Why |
|---|---|---|
| `dashboard/lib/theme.py` | Added `axis_style` to the shared Plotly template; added CSS for micro-interactions (nav/button/expander/page-link hover), empty states, field-status badge + pulse, `.profile-panel` entrance class; added `empty_state()` and `field_status_badge()` helper functions | One coherent chart language (D-04) and interaction system (D-05), reusable everywhere instead of per-page CSS |
| `dashboard/lib/data.py` | Added `AVOID_BY_SEGMENT` dict | Grounds Customer 360's new "What should we avoid?" section in the existing action framework, no new claims |
| `dashboard/pages/overview.py` | Added one `theme.field_status_badge()` call | Living Retention Field (D-02/§10) |
| `dashboard/pages/action_center.py` | Added one `theme.divider()` call | Section-break consistency (D-03) |
| `dashboard/pages/customer_360.py` | Rewritten (flagship redesign) | U-01 |
| `dashboard/pages/priority_customers.py` | One-line `regex=False` fix on its own search | Same latent correctness bug as §9 |
| `dashboard/pages/retention_copilot.py` | One-line `regex=False` fix on its own search | Same latent correctness bug as §9; shares `cust360_search` state with Customer 360 |
| `test_cases/D-02_D-03_D-04_D-05_U-01_validation_report.md` | New | This report |

**Not touched, confirmed by construction** (no tool call this pass opened, read, or wrote any of
these): every notebook under `notebooks/` (01-10), everything under `src/`, every file under
`outputs/` (all `*.csv`/`*.json`), everything under `models/`, and `dashboard/lib/components.py`
and `dashboard/lib/caveats.py` (read for context, not modified). No churn label, model file,
prediction, risk score, calibrated probability, threshold, feature, SHAP value, segment
definition, Historical Realized Revenue figure, or temporal validation result was changed by this
pass — every visual change is presentation-layer only.

## 13. Status and next steps

D-02, D-03, D-04, D-05, and U-01 all remain **REVIEW** — none promoted to DONE, per instruction.
Retention Copilot's own dedicated implementation was explicitly not started this pass (its two
touches were pre-existing bug fixes, documented in §9, not new feature work). Stopping here for
review, as instructed.
