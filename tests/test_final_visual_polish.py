"""Tests for P2-16 -- "Final Visual Polish"
(task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P2-16).

Two concrete, previously-uncaught visual/display defects were found during this ticket's
screenshot-driven audit of all six pages (documented in task_1/P2-16_validation_report.md) and
fixed -- no new features, no restyling beyond these two fixes:

1. Customer 360's "Tenure" stat and its "Behavior vs. the population" detail table showed the
   literal string "nan days" for any customer with no recorded tenure, instead of the honest
   "not available" fallback this exact field already uses elsewhere in the product
   (copilot_engine.py's build_customer_evidence_lines) -- a raw pandas NaN leaking into the UI.
2. Action Center stacked two uppercase small-caps eyebrow labels directly on top of each other
   ("A separate story: growth, not risk" then secondary_story's own "GROWTH OPPORTUNITY") with
   almost no vertical gap -- a component-reuse inconsistency, since Overview achieves the same
   "growth, not risk" framing with secondary_story's own eyebrow parameter alone, no second,
   redundant outer label.

Runnable standalone (`python tests/test_final_visual_polish.py`) or via pytest.
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

CUSTOMER_360_PAGE = f"{DASHBOARD_DIR}/pages/customer_360.py"
ACTION_CENTER_PAGE = f"{DASHBOARD_DIR}/pages/action_center.py"


# ---------------------------------------------------------------------------
# Fix 1: Customer 360 never shows a raw "nan" for a customer with no recorded tenure.
# ---------------------------------------------------------------------------

def _find_a_customer_with_no_tenure():
    df = data.load_customer_lookup_data()
    no_tenure = df[df["tenure_days_at_cutoff"].isna()]
    assert len(no_tenure) > 0, "this test assumes the real dataset has at least one such customer"
    return no_tenure.iloc[0]["msno"]


# Customer 360's profile section (the stat row AND the "Behavior vs. the population" detail
# table) is gated behind a real dataframe ROW SELECTION event (`event.selection.rows`), which
# AppTest cannot simulate -- the same already-documented harness limitation P1-15's report and
# tests establish for this exact page (see test_integrated_product_qa.py's
# test_customer_360_hrr_caveat_call_is_unchanged_and_still_reachable). Pre-seeding
# `cust360_search` alone populates the search box and filters the results table, but the code
# still stops before the profile section, so a naive AppTest check here would pass vacuously
# (find no "nan" because the fixed lines never ran) rather than actually proving the fix. The fix
# was therefore verified live in the browser (see task_1/P2-16_validation_report.md) and is
# regression-guarded here at the source level -- the same pattern P1-15 already established for
# this identical gate.

def test_customer_360_tenure_fix_applied_to_the_stat_row():
    src = open(CUSTOMER_360_PAGE, encoding="utf-8").read()
    assert '{"label": "Tenure", "value": f"{full[\'tenure_days_at_cutoff\']:.0f} days" if pd.notna(full["tenure_days_at_cutoff"]) else "—"}' in src


def test_customer_360_tenure_fix_applied_to_the_behavior_detail_table():
    src = open(CUSTOMER_360_PAGE, encoding="utf-8").read()
    assert '"This customer": f"{full[\'tenure_days_at_cutoff\']:.0f}" if pd.notna(full["tenure_days_at_cutoff"]) else "not available"' in src


def test_customer_360_tenure_fix_reuses_the_same_pd_notna_guard_already_used_nearby():
    # Regression guard on the fix's own consistency: the exact guard pattern already used two
    # lines above (for calibrated_probability / total_revenue) is now applied to tenure too.
    src = open(CUSTOMER_360_PAGE, encoding="utf-8").read()
    assert 'pd.notna(full["calibrated_probability"])' in src  # the pre-existing, unmodified guard
    assert 'pd.notna(full["tenure_days_at_cutoff"])' in src   # this ticket's fix, same pattern


def test_at_least_one_real_customer_has_no_recorded_tenure():
    # Sanity check that this fix addresses a real, reachable state in the live dataset, not a
    # hypothetical one.
    _find_a_customer_with_no_tenure()


# ---------------------------------------------------------------------------
# Fix 2: Action Center no longer stacks a redundant eyebrow above secondary_story.
# ---------------------------------------------------------------------------

def test_action_center_no_longer_has_the_redundant_stacked_eyebrow():
    src = open(ACTION_CENTER_PAGE, encoding="utf-8").read()
    assert 'theme.eyebrow("A separate story: growth, not risk")' not in src


def test_action_center_growth_opportunity_eyebrow_still_present():
    # The information itself is not lost -- secondary_story's own eyebrow still carries it.
    at = AppTest.from_file(ACTION_CENTER_PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "GROWTH OPPORTUNITY" in text


def test_action_center_champions_section_unaffected_otherwise():
    # Regression guard: only the one redundant label was removed -- the Champions card's title,
    # stats, and objective text are all still present and correct.
    action_plan = data.load_action_plan()
    champions = action_plan[action_plan["priority_group"] == "Engaged Low-Risk (Champions)"].iloc[0]
    at = AppTest.from_file(ACTION_CENTER_PAGE, default_timeout=180)
    at.run()
    text = " ".join(m.value for m in at.markdown)
    assert champions["priority_group"] in text
    assert champions["marketing_objective"] in text


def test_action_center_divider_before_the_growth_section_is_unchanged():
    src = open(ACTION_CENTER_PAGE, encoding="utf-8").read()
    assert "theme.divider()" in src
    divider_pos = src.index("theme.divider()")
    secondary_story_pos = src.index("components.secondary_story(")
    assert divider_pos < secondary_story_pos


# ---------------------------------------------------------------------------
# Cross-cutting: both pages still load cleanly, full demo path unaffected.
# ---------------------------------------------------------------------------

def test_customer_360_and_action_center_still_load_cleanly_on_a_plain_render():
    for page in (CUSTOMER_360_PAGE, ACTION_CENTER_PAGE):
        at = AppTest.from_file(page, default_timeout=180)
        at.run()
        assert not at.exception


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
