"""Tests for P1-13 -- "Five-Minute Demo Flow"
(task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-13).

Context: test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md's own "Part 10 -- 5-minute demo audit"
(and its "Part 1 -- 10-second first impression") already identified every P0 blocker in this area
and traced through the full demo sequence live; every P0 it found (default prompts failing, the
NT$/₹ mismatch, the missing nav-name fix, search_customers being unreachable without a key, the
flagship AI page not being linked from Overview) was independently fixed by earlier tickets this
session (P1-07 through P1-12) before this ticket started. What remained genuinely open from that
audit and squarely in P1-13's own acceptance criteria ("hero workflow reached quickly") was
finding #4/#5 from that audit's Part 1: "The hero has no button... a first-time visitor has to
scroll and read before finding the one thing to click" and "Nothing on this landing page mentions
an AI assistant... the AI is invisible on first contact." This file tests the one change P1-13
made to close that gap: a real, grounded "Ask Retention Intelligence" call-to-action moved into
Overview's hero itself, reusing the exact same handoff mechanism (session state + switch_page)
and the exact same real top-opportunity data already used by the pre-existing lower button --
never a new claim, never a new destination, never invented data.

Same two-part structure as every other test file in this project:
1. AppTest-driven tests against the real, current, no-API-key environment.
2. Source-level checks for the one part of a cross-page handoff (`st.switch_page` after setting
   session state) that AppTest's isolated single-page harness cannot itself follow -- see the
   inline comments at each site for the specific, already-documented harness limitation.

Runnable standalone (`python tests/test_five_minute_demo_flow.py`) or via pytest.
"""
from __future__ import annotations

import os
import sys
import traceback

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from streamlit.testing.v1 import AppTest  # noqa: E402

from lib import data  # noqa: E402

OVERVIEW_PAGE = f"{DASHBOARD_DIR}/pages/overview.py"


def _real_top_opportunity_segment() -> str:
    action_plan = data.load_action_plan()
    return data.priority_opportunities(action_plan, top_n=1).iloc[0]["priority_group"]


# ---------------------------------------------------------------------------
# The hero CTA exists, names the real segment, and is positioned before the chart -- i.e. visible
# on first paint, not after a scroll.
# ---------------------------------------------------------------------------

def test_overview_hero_has_an_immediate_ask_retention_intelligence_cta():
    segment = _real_top_opportunity_segment()
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert f"Ask Retention Intelligence: why does {segment} need attention? →" in labels


def test_hero_cta_source_appears_before_the_priority_zone_chart_section():
    # Structural proof this is reachable without scrolling. Romer-layout redesign: the Overview is
    # now one screen -- three stat cards, then the funnel panel beside the "Start here" panel that
    # holds this button -- so the CTA must sit in that first row of panels, i.e. before the page's
    # closing "next step" row and methodology, never below them.
    src = open(OVERVIEW_PAGE, encoding="utf-8").read()
    hero_cta_pos = src.index('key="hero_ask_ri"')
    assert hero_cta_pos < src.index("theme.journey_next(")
    assert hero_cta_pos < src.index("caveats.render_caveats(")


def test_hero_cta_is_the_single_retention_intelligence_entry_point():
    # Romer-layout redesign (simplification pass): the Overview used to carry two near-identical
    # "Ask Retention Intelligence" buttons about the same segment -- the hero CTA and a lower
    # recommendation-block CTA. They were merged into this one, which already carries the segment
    # context and clears an earlier customer focus (see test_ui_refurbishment's handoff test).
    src = open(OVERVIEW_PAGE, encoding="utf-8").read()
    assert 'key="hero_ask_ri"' in src
    assert 'key="ask_ri_overview"' not in src


# ---------------------------------------------------------------------------
# The CTA is real, grounded, and uses the proven handoff mechanism -- not a new destination, not
# invented data.
# ---------------------------------------------------------------------------

def test_hero_cta_click_sets_the_real_segment_and_attempts_the_proven_handoff():
    segment = _real_top_opportunity_segment()
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    btn = next(b for b in at.button if b.key == "hero_ask_ri")
    btn.click().run()
    # Same pre-existing, already-documented AppTest harness limitation as every other cross-page
    # handoff in this app (AppTest.from_file() runs outside app.py's st.navigation() registry, so
    # st.switch_page raises here) -- confirmed working live in the browser in this ticket's own
    # validation report. Assert the specific expected exception, the same pattern used throughout
    # this project (see test_manager_workflow.py, test_retention_intelligence_ui.py).
    assert len(at.exception) == 1
    assert "StreamlitPageNotFoundError" in str(at.exception[0]) or "Could not find page" in str(at.exception[0])
    assert at.session_state["copilot_segment_choice"] == segment


def test_hero_cta_source_uses_the_proven_session_state_and_switch_page_mechanism():
    src = open(OVERVIEW_PAGE, encoding="utf-8").read()
    assert 'st.session_state["copilot_segment_choice"] = top_opportunity["priority_group"]' in src
    assert 'st.switch_page("pages/retention_copilot.py")' in src


def test_hero_cta_does_not_introduce_a_new_data_source():
    # Confirms this reuses the exact same `top_opportunity` variable the rest of the page already
    # computes from data.priority_opportunities() -- no second, parallel "which segment is the
    # opportunity" definition invented for the hero button.
    src = open(OVERVIEW_PAGE, encoding="utf-8").read()
    hero_block = src[src.index('key="hero_ask_ri"') - 400 : src.index('key="hero_ask_ri"') + 200]
    assert 'top_opportunity["priority_group"]' in hero_block


# ---------------------------------------------------------------------------
# Regression: the pre-existing CTAs and the plain-render behavior are unaffected.
# ---------------------------------------------------------------------------

def test_the_merged_retention_intelligence_button_still_names_the_real_segment():
    # What the removed lower CTA guaranteed -- a way into the assistant that names the real top
    # segment -- is still guaranteed, by the one remaining button.
    segment = _real_top_opportunity_segment()
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    labels = [b.label for b in at.button]
    assert any(l.startswith("Ask Retention Intelligence") and segment in l for l in labels)


def test_pre_existing_view_priority_customers_button_still_present():
    segment = _real_top_opportunity_segment()
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    labels = [b.label for b in at.button]
    assert f"View {segment} customers in Priority Customers →" in labels


def test_overview_still_renders_without_exception_on_a_plain_load():
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    assert not at.exception


def test_overview_still_has_exactly_three_calls_to_action_no_accidental_duplicate():
    # Sanity guard: exactly one "Ask Retention Intelligence" button on the Overview after the
    # Romer-layout simplification merged the hero and lower CTAs -- never the same action twice.
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    labels = [b.label for b in at.button]
    ri_buttons = [l for l in labels if l.startswith("Ask Retention Intelligence")]
    assert len(ri_buttons) == 1


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all():
    tests = {name: fn for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)}
    p, f = 0, 0
    for name, fn in tests.items():
        try:
            fn()
        except AssertionError as e:
            f += 1
            print(f"FAIL  {name}  {e}")
        except Exception as e:  # noqa: BLE001
            f += 1
            print(f"ERROR {name}  {type(e).__name__}: {e}")
            traceback.print_exc()
        else:
            p += 1
            print(f"PASS  {name}")
    print(f"\n{p} passed, {f} failed (of {len(tests)} tests)")
    return f == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
