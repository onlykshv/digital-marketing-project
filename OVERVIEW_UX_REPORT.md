# Overview page — UX simplification (2026-10-09)

Narrow, Overview-only change: no changes to the model, data, outputs, thresholds, segments, recommendations or terminology. Nothing committed or pushed.

## Changes
1. **Header:** shorter title on the Overview (scoped to `st-key-ov_head`); the subtitle is now one line: "971.0K KKBOX subscribers, scored for how likely they are to leave."
2. **KPIs and funnel merged:** the three stat cards (Customers analyzed → Showing risk signals → Save first) are now a single left-to-right row, each with a thin bar showing its true share of customers. The separate four-row funnel panel is gone, so each number appears once. "Highest risk" (22.7K) is still shown as the middle card's note. The third card's note is no longer red, so all three cards share the same hierarchy.
3. **"Start here" is the main section:** a full-width panel with the recommendation on the left and the actions on the right.
4. **One primary button:** "View At-Risk, Auto-Renew Off customers in Priority Customers →" (the full label now wraps instead of being cut off).
5. **Competing buttons demoted, not removed:**
   - "Ask Retention Intelligence…" → a link-style (tertiary) button under the primary one.
   - "Review the 2.4K high-risk, high-value customers →" → a secondary button inside the collapsed "How these groups are defined" section.
6. **Secondary content collapsed:** the group definitions and the high-risk/high-value sentence sit in "How these groups are defined"; "Methodology & limitations" is unchanged and still collapsed. The "Next step" row is unchanged.

## Files modified
- `dashboard/pages/overview.py`: layout.
- `dashboard/lib/theme.py`: the `.ri-funnel` styles (used only by the Overview) rewritten; new styles scoped to `st-key-ov_head` and `st-key-rp_start`. No other page uses these.
- `tests/test_ui_refurbishment.py`: the funnel test now expects 3 bars drawn to true share (was 4).
- `tests/test_five_minute_demo_flow.py`: an outdated comment updated; 3 new tests (exactly one primary button and it carries the segment filter; competing buttons demoted but still present; zone drill-down and definitions inside the collapsed section).

## Tests
`python -m pytest tests -q`: **301 passed** (298 before + 3 new).

## Browser QA (performed)
- At 1536-wide and at a true 1366×768 viewport (the 1366 check used a fixed-size frame because the window couldn't be resized): header, three cards, recommendation and primary button all fit in the first screen (primary button bottom ≈ 478 px). No horizontal scroll and no clipped text found.
- The "How these groups are defined" section opens and closes correctly; its content is not clipped.
- Primary button → Priority Customers with "Filter carried over · Segment: At-Risk, Auto-Renew Off" (113,820 customers).
- Ask Retention Intelligence link → Retention Intelligence with "Segment in focus: At-Risk, Auto-Renew Off".
- Zone button → Priority Customers with "Risk tier: High · Value tier: High".
- No error messages shown on any of these pages.
