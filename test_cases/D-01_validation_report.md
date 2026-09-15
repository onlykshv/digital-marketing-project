# Validation Report — Ticket D-01: Retention Field visual redesign (Pass 2)

**Status: REVIEW** (unchanged — do not promote to DONE from this report alone; see §7)
**Priority:** CRITICAL | **Category:** Product Design
**Date:** 2026-09-09 (second pass, superseding the first D-01 report)

---

## 0. Why this pass exists

The first D-01 pass changed CSS tokens and header markup but was correctly rejected: "the actual
rendered dashboard does not show a sufficiently meaningful visual redesign." Investigating why
surfaced the real problem — **a root-cause bug, not a design failure**: `app.py` called
`apply_page_style()` and rendered the sidebar brand block *before* `st.navigation(...).run()`.
Content emitted before `nav.run()` is not reliably delivered to the browser (confirmed by an
isolated repro: the exact CSS, byte-for-byte, rendered perfectly in a standalone script — the bug
was specifically about *when* it was being emitted, not the CSS itself). Every screenshot in the
previous session's "visual QA" was, in effect, looking at an unstyled app. That is fixed here
first (§1), and it is the reason this pass is able to show real, visible change where the last one
could not.

## 1. Root-cause fix (blocks everything else — fixed first)

| File | Change |
|---|---|
| `dashboard/app.py` | Removed `apply_page_style()` and the sidebar brand block from before `nav.run()`. Now only holds `st.set_page_config` and the `st.Page`/`st.navigation` wiring. |
| `dashboard/lib/theme.py` | `apply_page_style()` now also renders the sidebar brand block internally (folded in, so one call does both jobs). |
| `dashboard/pages/*.py` (all 5) | Each page now calls `theme.apply_page_style()` itself, as the first thing it does — i.e. as part of the exact script execution `nav.run()` dispatches to, not a separate pre-amble. |

**Verified**: restarted the server fresh, opened a new tab, and the navy sidebar, KKBox brand
block, Inter font, and every custom class rendered correctly on first load — reproduced
consistently across multiple fresh page loads after this change (it had failed consistently
before it, across fresh servers and fresh tabs).

## 2. What was actually redesigned (not just retouched)

### Global
- **New non-card primitive**: `components.recommendation_block` — an oversized headline with a
  left accent rule, no bordered box. Reserved for exactly one "do this" moment per page.
- **New non-card primitive**: `components.secondary_story` — box-free, smaller type, for content
  that should visibly recede next to a recommendation_block.
- **New primitive**: `theme.eyebrow()` — a small uppercase signpost marking a shift in kind of
  content (e.g. "Model explanation" vs. "Business recommendation").
- **Motion**: short entrance fade/slide for headers, recommendation blocks, and cards; a quiet
  shadow-deepen on card hover. Both gated behind `@media (prefers-reduced-motion: no-preference)`
  — fully inert for anyone with that OS/browser preference set. No continuous animation, no
  bouncing/flashing.
- **Dead code removed**: `components.priority_opportunity_card`, `components.quadrant_card`,
  `components.kpi_row`, `components.priority_rank_label`, `data.named_quadrant` — all fully
  replaced by the above and confirmed unused anywhere in the live app before deletion.

### Command Center — the risk x value "field"
The scatter chart now has a genuine field identity: a soft radial glow anchored on the
high-risk/high-value cell (three nested translucent circles, fading outward), plus a halo ring
around that one point. Chart height increased (440 -> 560px) so it dominates the page as asked.
"The biggest actionable opportunity" is now a `recommendation_block` (oversized headline, no box);
Champions is now a `secondary_story` (smaller, no box, visibly a secondary/positive story next to
it) — replacing two equal-weight bordered cards.

### Risk Intelligence
Added `theme.eyebrow("Model explanation")` above the SHAP driver list and
`theme.eyebrow("Business recommendation")` above the segments table — the two kinds of content the
ticket asked to visually separate are now explicitly labeled, not just adjacent. The risk-tier
distribution bar now carries inline percentage labels directly on its segments (Low 87% / Medium
11%) instead of relying solely on a separate stat row below it. Threshold exploration remains
inside its existing collapsed, "Advanced" expander — already secondary, left as-is.

### Customer Value — the "retention paradox" as one field
Replaced the heatmap + metric-toggle + **four separate bordered quadrant cards** with **one**
bubble chart: risk tier x value tier, bubble size = avg. HRR, color = churn rate (green -> amber
-> red), percent-of-base labeled directly on each bubble, and the same halo-ring treatment as
Command Center around the high-risk/high-value cell — one consistent visual language for "risk x
value" across the product. Net container count for this section: 1 chart, down from 1 heatmap + 1
radio + 4 cards.

### Action Center — an intervention queue, not a card grid
Priority 01 is now a full-size `recommendation_block`; Priority 02 is the same component at
`size="small"` (1.5rem title vs. 2.1rem) in a narrower column beneath it — a real, visible size
and weight difference, not just a badge. Champions moved to `secondary_story` under its own
"A separate story: growth, not risk" eyebrow.

### Customer 360 — flagship profile
- Strong identity block: `eyebrow("Customer profile")` + the customer ID at 2rem, followed by
  risk/value/segment badges — no colored box (avoids yet another "dark hero" repeat), but a real
  visual moment via scale and whitespace.
- **Model Risk Score and Estimated Churn Probability are now shown side by side, separately
  labeled**, with an inline caption distinguishing them (and HRR) explicitly: "Model Risk Score
  ranks customers... it is not a probability. Estimated Churn Probability is a separately
  calibrated figure and can be read as one... Historical Realized Revenue is money already
  collected, not a forecast of future value." This required one data change (§3) to surface a
  number that already existed (from ticket A-02) but was not previously loaded on this page.
- "Risk drivers" and "What to do" eyebrows now head the behavior-comparison and recommended-action
  columns respectively, for a clearer hierarchy.
- Search/filter/load behavior is completely unchanged (see §5).

## 3. The one data-layer change, and why it's in-bounds

| File | Change | Why it's a presentation dependency, not new analysis |
|---|---|---|
| `dashboard/lib/data.py` | `load_customer_lookup_data()` now also merges `outputs/calibrated_probabilities.csv` (`msno`, `calibrated_probability`) into the per-customer lookup table. | `calibrated_probability` already exists, fully computed and validated under ticket A-02 — this only makes an existing, already-audited column visible in the one place (Customer 360) the ticket explicitly asks for it. No new calculation, no changed value, no new file. |

**Every other change in this pass is presentation-only** (CSS, chart construction, markup,
component composition) — no model, no model output, no feature engineering, no threshold, no
label, no segment definition, and no calibration logic was touched.

## 4. Analytical regression checks

- **Every number checked against the previously-verified figures and found identical**: Command
  Center (129.7K / 22.7K / 9.0% / ₹5.43B), Risk Intelligence (841.2K/3.6%, 107.0K/36.6%,
  22.7K/80.0%), Customer Value (₹5.43B, ₹91.36M, 316.2K), Action Center (113.8K/41.1%/₹525.22M for
  Priority 01). None of these changed — expected, since no computation was touched.
- **File-modification-time check**: confirmed nothing under `outputs/`, `models/`, `notebooks/`,
  or `src/` changed during this pass — only 9 files under `dashboard/` did (`app.py`, `theme.py`,
  `components.py`, `data.py`, and all 5 `pages/*.py`).
- Customer 360's newly-displayed `calibrated_probability` values are read, unmodified, from
  `outputs/calibrated_probabilities.csv` (ticket A-02's output) — spot-checked one customer in
  the browser (Model Risk Score 0.96, Estimated Churn Probability 78%), consistent with A-02's
  finding that raw scores run higher than calibrated ones.

## 5. UX / functional checks

1. **Streamlit `AppTest` — all 5 pages, zero exceptions**, including Customer 360's full
   gate → filter → select flow (re-run after every code change in this pass, not just once at
   the end).
2. **Live browser check** at 1536x864 (the requested resolution) — every page opened and
   screenshotted after the root-cause fix.
3. **Customer 360 flow manually exercised in the browser**: loaded data, applied a Risk tier
   filter (High → 22,692 matches), selected a row by its checkbox, confirmed the profile panel
   renders with the correct Model Risk Score / Estimated Churn Probability / HRR / Tenure for that
   specific customer.
4. **Charts confirmed rendering** on all 5 pages: Command Center's field scatter, Risk
   Intelligence's SHAP bars, Customer Value's field bubble chart, Action Center's portfolio
   scatter (inside its expander), all render without error.
5. **Horizontal overflow check** (JS: `document.documentElement.scrollWidth` vs. `clientWidth` at
   1536px viewport) — **0px overflow on all 5 pages**.
6. **Max content width**: `.block-container` is capped at 1280px, centered — already within the
   1200–1280px band asked for; unchanged this pass.

## 6. Acceptance criteria — status

| Requirement | Status |
|---|---|
| 1. Break the repetitive card pattern | ✅ Command Center opportunity/champions, Action Center priorities/champions, and Customer Value's 4 quadrant cards are all now card-free or reduced to one chart |
| 2. Editorial typography | ✅ Oversized page headers (2.6rem), oversized recommendation titles (2.1rem), eyebrow signposts throughout |
| 3. Retention Field visual language | ✅ Field glow + halo on Command Center and Customer Value, shared visual language across both; restrained (no neon/cyberpunk) |
| 4. Command Center hierarchy | ✅ Hero number dominant; field chart enlarged and made the visual anchor; opportunity is a directive, not a card; Champions clearly secondary |
| 5. Risk Intelligence | ✅ SHAP list is the centerpiece; model-explanation vs. business-recommendation now explicitly labeled; tiers read as a labeled distribution; thresholds stay in an "Advanced" expander |
| 6. Customer Value | ✅ Risk x value is one field chart; HRR captioned as "not a forecast"; high-risk/high-value visually haloed |
| 7. Action Center | ✅ Priority 01 visibly dominates Priority 02 (size + weight); reads as a queue; Champions is a separate story |
| 8. Customer 360 | ✅ Strong identity block; Model Risk Score and Estimated Churn Probability shown side by side, separately labeled and captioned; HRR labeled; search/filter/load preserved |
| 9. Motion | ✅ Short entrance transitions + card hover, gated behind `prefers-reduced-motion`; nothing continuous or flashy |
| 10. Responsive composition | ✅ 1280px centered max-width (pre-existing, confirmed still correct); zero horizontal overflow at 1536px |

## 7. Remaining limitations — why this stays REVIEW, not DONE

- **This report's visual observations come from the same automated session that made the
  changes.** A second, independent pair of eyes (the user, or a fresh session) should confirm the
  redesign reads as intended before this moves to DONE — that judgment call belongs to a human,
  not to the agent that built it.
- **Narrower viewports were not tested.** Requirement #10 was checked at the requested 1536x864
  only; behavior below ~1280px width (where the sidebar and centered content start competing for
  space) is unverified.
- **Motion was verified to exist and to be disableable via `prefers-reduced-motion`, but not
  perceptually tuned** — e.g. whether 0.4s is the right entrance duration, or whether it should be
  even more restrained, is a judgment call worth a human look.
- **The `st.dataframe` widget's own internal scrolling behavior** (noted in earlier sessions) is
  unchanged by this pass and can make mouse-driven scrolling past a large table feel non-obvious;
  this is a Streamlit-native widget behavior, not something this pass touched or was asked to fix.
