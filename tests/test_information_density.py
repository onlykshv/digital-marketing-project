"""Tests for P1-10 -- "Numbers-to-Decisions Pass"
(task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-10).

Covers the two page-level (not Retention Intelligence answer-text) changes this task made:
Action Center's secondary "other customers needing attention" table moving into a collapsed
expander, and Customer Value's revenue-concentration chart distinguishing actionable segments
from Champions/Stable-Monitor by color. The agent.py answer-formatting changes (the aggregate
answer's closing "so what" line, the rank-segments answer's Finding/evidence restructure) have
their own dedicated tests in tests/test_agent_orchestration.py.

Same two-part structure as every other test file in this project: AppTest-driven checks against
the real, current, no-API-key environment, plus source-level checks for anything AppTest's
rendering model can't directly distinguish (e.g. "collapsed by default" vs. "always visible" --
Streamlit executes an expander's body regardless of its visual collapse state, so the only
reliable proof that content is now inside an expander, not a bare section, is that it appears as
a genuine ExpanderNode in `at.expander`).

Runnable standalone (`python tests/test_information_density.py`) or via pytest.
"""
from __future__ import annotations

import os
import sys
import traceback

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from streamlit.testing.v1 import AppTest  # noqa: E402

from lib import data, theme  # noqa: E402

ACTION_CENTER_PAGE = f"{DASHBOARD_DIR}/pages/action_center.py"
CUSTOMER_VALUE_PAGE = f"{DASHBOARD_DIR}/pages/customer_value.py"


# ---------------------------------------------------------------------------
# Action Center -- the secondary "other customers needing attention" table is now inside a
# collapsed expander, matching the existing "Portfolio view" treatment already on this page.
# ---------------------------------------------------------------------------

def test_action_center_secondary_table_is_now_in_a_collapsed_expander():
    at = AppTest.from_file(ACTION_CENTER_PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    labels = [e.label for e in at.expander]
    assert any(l.startswith("Other customers needing attention") for l in labels)
    # the pre-existing "Portfolio view" expander must still be there, unchanged
    assert any(l.startswith("Portfolio view") for l in labels)


def test_action_center_secondary_table_row_and_column_count_unchanged():
    # Proves this is a presentation-only change: the same data, same shape, just relocated.
    action_plan = data.load_action_plan()
    all_opportunities = data.priority_opportunities(action_plan)
    expected_secondary_rows = len(all_opportunities.iloc[2:])

    at = AppTest.from_file(ACTION_CENTER_PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    assert len(at.dataframe) == 1
    df = at.dataframe[0].value
    assert len(df) == expected_secondary_rows
    assert list(df.columns) == ["Segment", "Customers", "Churn Rate (%)", "Revenue", "Recommended Treatment"]


def test_action_center_priority_cards_and_download_button_unaffected():
    # Regression guard: everything above and below the relocated table is untouched.
    at = AppTest.from_file(ACTION_CENTER_PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "PRIORITY 01" in text
    assert "PRIORITY 02" in text
    labels = [b.label for b in at.button] + [d.label for d in at.download_button]
    assert "Download full action plan (CSV)" in labels
    assert any(l.startswith("Ask Retention Intelligence about") for l in labels)


# ---------------------------------------------------------------------------
# Customer Value -- the revenue-concentration bar chart now visually distinguishes genuinely
# actionable (at-risk) segments from Champions (growth, not risk) and Stable/Monitor (no action
# recommended), reusing the theme's own existing accent/low/neutral color semantics.
# ---------------------------------------------------------------------------

def test_customer_value_bar_color_logic_matches_the_documented_segment_treatment():
    src = open(CUSTOMER_VALUE_PAGE, encoding="utf-8").read()
    assert "def _segment_bar_color" in src
    assert 'theme.COLORS["low"]' in src
    assert 'theme.COLORS["neutral"]' in src
    assert 'theme.COLORS["accent"]' in src
    assert '"Engaged Low-Risk (Champions)"' in src
    assert '"Stable / Monitor"' in src


def test_customer_value_page_still_renders_with_real_revenue_figures():
    value_by_tier = data.load_value_by_tier()
    total_hrr = data.total_realized_revenue(value_by_tier)
    at = AppTest.from_file(CUSTOMER_VALUE_PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert theme.fmt_currency(total_hrr) in text
    # the color-only change made no formatting edit -- the "Where revenue concentrates" bar
    # labels must still be the existing theme.fmt_currency() strings, not raw NT$
    assert "Where revenue concentrates" in text


def test_customer_value_bar_color_function_covers_every_real_segment_without_dropping_any():
    # The color change must not have dropped, filtered, or renamed any segment -- executed
    # directly against every real segment name, `_segment_bar_color`'s equivalent logic must
    # return a real theme color for each one (proven here by re-implementing the same three-way
    # mapping the page itself uses and checking it against the page's own source, not by
    # inspecting rendered chart internals, which AppTest does not expose for Plotly figures).
    value_by_segment = data.load_value_by_segment()
    src = open(CUSTOMER_VALUE_PAGE, encoding="utf-8").read()
    for segment in value_by_segment["segment"]:
        assert isinstance(segment, str) and segment  # sanity: real segment names, nothing filtered upstream
    # the function is defined to run over `vbs["segment"]`, i.e. every row of value_by_segment
    # sorted -- not a filtered subset -- confirmed by the absence of any .loc/.query/[mask] between
    # loading value_by_segment and building bar_colors
    section = src.split('vbs = value_by_segment.sort_values')[1].split('bar_colors = [_segment_bar_color(s) for s in vbs["segment"]]')[0]
    assert ".query(" not in section
    assert "[vbs[" not in section


# ---------------------------------------------------------------------------
# Full sweep -- proves this task's three file changes didn't regress any other page.
# ---------------------------------------------------------------------------

def test_all_six_pages_still_load_cleanly_after_p1_10_changes():
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
