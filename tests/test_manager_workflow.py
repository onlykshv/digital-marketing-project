"""Tests for P1-08 -- "Manager Command Workflow"
(task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-08).

Scope: the cross-page journey Overview -> Priority Customers -> Customer 360 ->
Retention Intelligence reads as one coherent workflow, not six separate screens. Three of the
four legs of that journey already worked (verified live in Task 06 / P1-07's own validation
reports); this file's new tests cover the one gap P1-08 found and fixed -- Overview's link into
Priority Customers did not carry the page's own "portfolio signal" (the biggest actionable
opportunity segment) as a starting filter -- plus regression coverage proving the other legs
still work unchanged.

Same two-part structure as every other test file in this project:
1. AppTest-driven tests against the real, current, no-API-key environment.
2. Source-level checks for the parts of a cross-page handoff (`st.switch_page` after setting
   session state) that AppTest's isolated single-page harness cannot itself follow -- see the
   inline comments at each site for the specific, already-documented harness limitation.

Runnable standalone (`python tests/test_manager_workflow.py`) or via pytest.
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
PRIORITY_CUSTOMERS_PAGE = f"{DASHBOARD_DIR}/pages/priority_customers.py"


def _real_top_opportunity_segment() -> str:
    action_plan = data.load_action_plan()
    return data.priority_opportunities(action_plan, top_n=1).iloc[0]["priority_group"]


# ---------------------------------------------------------------------------
# 1. Portfolio signal -> cohort: Overview's link into Priority Customers must carry the page's
# own "biggest actionable opportunity" segment as a starting filter, not the generic default view.
# ---------------------------------------------------------------------------

def test_overview_view_priority_customers_button_names_the_real_top_opportunity_segment():
    segment = _real_top_opportunity_segment()
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert f"View {segment} customers in Priority Customers →" in labels


def test_overview_priority_customers_button_source_carries_the_segment_filter():
    # AppTest.from_file() runs a page in isolation, outside app.py's st.navigation() page
    # registry, so clicking a button that calls st.switch_page() raises StreamlitPageNotFoundError
    # on this harness -- the same, already-documented limitation every prior task's report notes
    # for every other cross-page handoff in this app (not a bug; confirmed working live in the
    # browser -- see task_1/P1-08_validation_report.md). Verified at the source level instead.
    src = open(OVERVIEW_PAGE, encoding="utf-8").read()
    assert 'st.session_state["pending_filter"] = {"segment": [top_opportunity["priority_group"]]}' in src
    assert 'st.switch_page("pages/priority_customers.py")' in src


def test_overview_no_longer_raises_an_exception_on_a_plain_render():
    # Regression-positive check: the page's one static st.page_link into Priority Customers (which
    # unconditionally raised the harness's known exception on every AppTest run, per every prior
    # task's report) is now a button that only calls st.switch_page when actually clicked -- so a
    # plain, no-interaction render must be exception-free.
    at = AppTest.from_file(OVERVIEW_PAGE, default_timeout=180)
    at.run()
    assert not at.exception


def test_priority_customers_applies_a_segment_filter_carried_from_overview():
    # Directly proves the consuming side of the mechanism: seeding session_state exactly as the
    # new Overview button does, before Priority Customers' own first render, must produce a
    # pre-filtered Segment multiselect -- not just "no crash".
    segment = _real_top_opportunity_segment()
    at = AppTest.from_file(PRIORITY_CUSTOMERS_PAGE, default_timeout=180)
    at.session_state["pending_filter"] = {"segment": [segment]}
    at.run()
    assert not at.exception
    seg_widget = next(w for w in at.multiselect if w.label == "Segment")
    assert seg_widget.value == [segment]
    text = " ".join(c.value for c in at.caption)
    assert "customers match these filters" in text


def test_priority_customers_pending_filter_is_consumed_once_not_left_stale():
    # The exact same session-state slot other deep links (search-results, Action Center, the
    # segment take-action button) already rely on being popped, not merely read -- proved here by
    # reusing the SAME session across two reruns: the filter must apply on the render it arrives
    # with, then disappear on the very next rerun of that same session, never silently reapplying
    # itself on an unrelated later interaction (e.g. clearing the search box).
    segment = _real_top_opportunity_segment()
    at = AppTest.from_file(PRIORITY_CUSTOMERS_PAGE, default_timeout=180)
    at.session_state["pending_filter"] = {"segment": [segment]}
    at.run()
    seg_widget = next(w for w in at.multiselect if w.label == "Segment")
    assert seg_widget.value == [segment]
    assert "pending_filter" not in at.session_state

    search_widget = next(w for w in at.text_input if w.label == "Search by Customer ID")
    search_widget.set_value("").run()
    seg_widget_after = next(w for w in at.multiselect if w.label == "Segment")
    assert seg_widget_after.value != [segment]  # back to the page's own default, not stale


# ---------------------------------------------------------------------------
# 2. Regression: the rest of the named P1-08 chain (cohort -> customer -> assistant) was already
# working (Task 06 / P1-07) and must still work unchanged.
# ---------------------------------------------------------------------------

def test_priority_customers_row_selection_still_hands_off_to_customer_360():
    src = open(PRIORITY_CUSTOMERS_PAGE, encoding="utf-8").read()
    assert 'st.session_state["cust360_search"] = picked["msno"]' in src
    assert '"pages/customer_360.py"' in src


def test_customer_360_still_links_to_retention_intelligence():
    src = open(f"{DASHBOARD_DIR}/pages/customer_360.py", encoding="utf-8").read()
    assert 'st.page_link("pages/retention_copilot.py"' in src
    assert "Ask Retention Intelligence about this customer" in src


def test_all_six_pages_still_load_without_a_new_exception():
    # Full sweep -- proves this task's one code change didn't regress any other page. The only
    # tolerated exception is Priority Customers' own st.page_link, which only appears (and only
    # raises, on this harness) once a row is actually selected -- not exercised by a plain render,
    # so every page here is expected to be clean.
    for name in ["overview", "priority_customers", "customer_value", "action_center", "customer_360", "retention_copilot"]:
        at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/{name}.py", default_timeout=180)
        at.run()
        assert not at.exception, f"{name}.py raised an unexpected exception: {at.exception}"


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
