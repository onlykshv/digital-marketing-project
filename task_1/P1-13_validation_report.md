# P1-13 Validation Report — Five-Minute Demo Flow

**Tracker row:** `task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx`, ID `P1-13`, Stage "Demo / Presentation", Priority P1.
**Status change:** `TODO` → `REVIEW` (this report; not `DONE` — reserved for independent sign-off).

## 1. Exact requirement from the tracker

**Issue:** "A technically strong product can underperform if its value is not obvious quickly."

**Claude Fix Prompt:** "Optimize for a fresh evaluator: business problem → platform value → Retention Intelligence → real portfolio question → cohort/customer → evidence → recommendation → reusable architecture. Make only UI/navigation/context changes needed. No invented claims; no hidden setup."

**Acceptance Criteria:** "Purpose understood within ~60 seconds; hero workflow reached quickly; real customer/cohort demo works from fresh state; claims grounded; tests/browser pass."

## 2. Interpretation and audit

Before writing any code, I read `test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md` in full — this is the original readiness audit this whole P1-07→P1-13 ticket sequence is derived from, and it contains a dedicated "Part 10 — 5-minute demo audit" section that walks the exact demo sequence this ticket is about, live, and names precisely what worked and what didn't at the time it was written.

Cross-checking that audit's findings against the CURRENT code (after P1-07 through P1-12), every one of its P0 findings is already resolved by earlier tickets this session:

| Audit finding (original) | Status now |
|---|---|
| 3 of 6 default Retention Intelligence prompts fail with no API key | Fixed (P1-07/P0-4 — `search_customers` reachable deterministically; the guaranteed-to-fail customer question removed from default buttons) |
| Nav label still says "Retention Copilot" | Fixed (confirmed "Retention Intelligence" everywhere, tested) |
| AI answers show NT$ while the rest of the product shows ₹ | Fixed (P0-3, reverified repeatedly this session) |
| `search_customers` / the priority-list UI unreachable without a key | Fixed (P1-07 — this session's own live testing confirmed the priority list renders with no key configured) |
| Flagship AI page not linked from Overview or Action Center | Fixed (P1-07/08 added "Ask Retention Intelligence about {segment}" CTAs to both) |
| Aggregate answer has no closing recommendation | Fixed (P1-10) |
| Action Center has no forward link | Fixed (it links to Retention Intelligence) |

What remained genuinely open, and squarely inside P1-13's own acceptance criteria, was the audit's **Part 1 — "10-second first impression," findings #4 and #5**:

> "4. What is the most important thing I can do here? Genuinely ambiguous. **The hero has no button.** The only actionable link on the entire page ('View Priority Customers →') appears after scrolling past the chart and the segment cards — a first-time visitor has to scroll and read before finding the one thing to click."
>
> "5. Is the AI assistant clearly the hero? **No.** Nothing on this landing page — the page a manager sees first — mentions an AI assistant, links to one, or hints one exists."

I verified this was still true in the current code: `dashboard/pages/overview.py`'s only route into Retention Intelligence (the "Ask Retention Intelligence about {segment} →" button added by P1-07) sits inside the `recommendation_block` section, which comes AFTER the hero, the insight text, the stat row, and the full priority-zone Plotly chart — i.e. below the fold on a typical screen. This is exactly "hero workflow reached quickly" failing today, and it is the one concrete, still-open gap P1-13 needed to close.

Everything else the audit's demo sequence (§11) relies on — Overview's chart and opportunity card, "View Priority Customers →", Priority Customers' real work queue, Customer 360's profile, "Ask Retention Intelligence about this customer →", the segment/customer question buttons, the evidence-then-recommendation answer structure (now the full P1-11 six-part structure), and the Model Risk Score / Estimated Churn Probability terminology discipline — already worked, and still works (re-verified live, see §6). **This ticket therefore made exactly one change.**

## 3. Files changed

- `dashboard/pages/overview.py` — one addition: an "Ask Retention Intelligence" call-to-action placed immediately after the hero header, before the priority-zone chart.
- `tests/test_five_minute_demo_flow.py` — new file, 10 tests.

No other file was touched. `notebooks/`, `models/`, `outputs/`, `src/`, and every other dashboard page are unmodified (confirmed via `find ... -newermt`).

## 4. Exact implementation

Added directly after the existing `theme.hero_header(...)` call in `overview.py`, before `theme.insight(...)`:

```python
if st.button(
    f"Ask Retention Intelligence: why does {top_opportunity['priority_group']} need attention? →",
    key="hero_ask_ri", type="primary",
):
    st.session_state["copilot_segment_choice"] = top_opportunity["priority_group"]
    st.switch_page("pages/retention_copilot.py")
```

This is **not a new capability** — it is the exact same handoff mechanism (`copilot_segment_choice` session state + `st.switch_page`) the pre-existing, lower "Ask Retention Intelligence about {segment} →" button already used, applied to the exact same `top_opportunity` variable the rest of the page already computes from `data.priority_opportunities(action_plan, top_n=1)` — no new data source, no new session-state convention, no invented claim about what the button does. Only its position moved: it is now the first interactive element on the page, immediately below the hero's own headline number, so a fresh evaluator sees the AI assistant is the product's headline feature without scrolling past the chart first (directly answering the audit's findings #4 and #5). `type="primary"` reuses the same Streamlit primary-button styling already established elsewhere in this product (`customer_360.py`'s "Load customer data" button), not a new visual language.

The pre-existing lower CTA ("Ask Retention Intelligence about {segment} →", next to the full recommendation card) and the "View {segment} customers in Priority Customers →" button were both left exactly as they were — the hero CTA is additive, not a replacement, so the page still offers both an immediate first-glance route into the AI and the fuller, evidence-attached route further down for a reader who scrolls.

## 5. Tests added

`tests/test_five_minute_demo_flow.py` — 10 tests: the hero CTA exists and names the real, current top-opportunity segment (not hardcoded); its source position is structurally before the chart section (proving it's reachable without scrolling) and before the pre-existing lower CTA (proving it's an addition, not a reordering); clicking it sets the real segment into `copilot_segment_choice` and attempts the proven `switch_page` handoff (same AppTest-harness-limitation pattern used throughout this project — the specific expected exception is asserted, not treated as a crash); the source uses the exact same session-state key and switch_page call the rest of the app already relies on; the button's segment reference is proven to come from the same `top_opportunity` variable, not a second parallel data source; both pre-existing CTAs ("Ask Retention Intelligence about {segment}" and "View {segment} customers in Priority Customers") are confirmed still present, unchanged; a plain render of the page still produces zero exceptions; and a sanity count confirms exactly two distinctly-labeled "Ask Retention Intelligence" buttons exist (the new hero one plus the original) — never an accidental duplicate of the same action.

## 6. Complete test results (this run, fresh)

```
tests/test_agent_tools.py                40 passed, 0 failed
tests/test_agent_orchestration.py       100 passed, 0 failed
tests/test_retention_intelligence_ui.py  44 passed, 0 failed
tests/test_manager_workflow.py            8 passed, 0 failed
tests/test_information_density.py         7 passed, 0 failed
tests/test_five_minute_demo_flow.py      10 passed, 0 failed   (new this task)
-------------------------------------------------------------------
TOTAL                                   209 passed, 0 failed
```

All pre-existing tests pass unmodified — this ticket required no test updates, only additions.

## 7. Live browser validation

Fresh Streamlit server started on port 8693. `ANTHROPIC_API_KEY` confirmed absent. Server log clean, no import errors.

- Navigated to the app's root URL (the genuine first-contact experience, no prior session state). Screenshot confirmed: the hero ("129.7K customers need attention...") is immediately followed by a prominent orange primary button — "Ask Retention Intelligence: why does At-Risk, Auto-Renew Off need attention? →" — visible without any scrolling, directly above the "Instead of treating the entire customer base equally..." explainer text.
- Clicked the button: landed on Retention Intelligence with "Segment in focus: At-Risk, Auto-Renew Off" already attached (the real, current top-opportunity segment, matching the hero's own number), the "View At-Risk, Auto-Renew Off customers in Priority Customers →" link present, and the segment-specific suggested questions ("Tell me about...", "Why is this segment important?", "What should we do with this segment") already showing — confirming the hero workflow is reached in exactly one click from a completely fresh page load, with real, grounded data, not a placeholder.
- The deeper legs of the demo sequence (segment/customer question → full evidence-then-recommendation answer, Priority Customers → Customer 360 → Retention Intelligence handoff, the no-API-key deterministic fallback banner) were already live-verified multiple times earlier this session (P1-11, P1-12 validation reports) and were not re-walked in full here to avoid redundant, repetitive browser actions — those reports remain the record of that verification, and nothing in this ticket touched any of the code paths they cover.

## 8. Claims grounded

The new button's label names a real segment (`top_opportunity["priority_group"]`, recomputed from live data on every page load) and performs exactly the action its label states (opens Retention Intelligence with that segment attached) — no invented capability, no promised feature that doesn't exist. No copy elsewhere on the page was changed, so no new claim of any kind was introduced beyond "you can ask Retention Intelligence about this" — which was already true and already demonstrated elsewhere on the same page before this ticket.

## 9. Known limitations

- This ticket deliberately did not touch the hero's own eyebrow copy ("OVERVIEW · WHERE SHOULD KKBOX ACT?"), which the original audit flagged as reading like "KKBox's internal tool" rather than "a retention-intelligence platform currently instantiated on KKBox's data" (audit finding #6). The audit itself characterizes this as "genuinely superficial, not structural" and lower priority than the missing-CTA problem this ticket fixed; a future ticket could revisit it if desired.
- The audit's own "Part 11 — Prioritized findings" P1/P2 items #7 (Overview/Action Center priority cards being word-for-word duplicates), #9 (top-nav order not matching the natural Priority Customers → Customer 360 chain), and #11–13 (the native Streamlit "Deploy" button, the first-paint brand-mark flash, a dedicated Methodology page) were not addressed — none of them are named in P1-13's own acceptance criteria, and the audit itself marks them lower priority or "not prioritized."
- No new "reusable architecture" UI element was added. The tracker's fix prompt lists "reusable architecture" as a step in the ideal demo narrative, but this is already communicated implicitly and honestly by the existing "Grounded in N analytical tools" / "Deterministic answer" captions on every Retention Intelligence answer (visible proof of a consistent tool-based system, not a one-off script per question type) — adding a dedicated "architecture" page or section was judged to be new scope beyond "UI/navigation/context changes," not something P1-13's acceptance criteria specifically requires.

## 10. Confirmation

P1-14 and all later tickets were not started as part of this ticket's own implementation. Per the separate continuation directive covering this ticket sequence, work proceeds automatically to P1-14 immediately after this ticket is marked `REVIEW` — documented in its own separate validation report.
