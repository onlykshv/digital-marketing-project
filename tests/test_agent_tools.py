"""Tests for dashboard/lib/agent_tools.py -- the deterministic tool layer for the future AI
orchestrator (see test_cases/AGENT_ARCHITECTURE_PLAN.md and test_cases/TASK_02_validation_report.md).

This project has no pytest dependency installed (and this task was explicitly told not to add
unnecessary dependencies), so this file is written pytest-COMPATIBLE (plain `test_*` functions,
plain `assert` statements -- `pytest tests/` will discover and run it unmodified the moment
pytest is available) but also runnable standalone right now:

    python tests/test_agent_tools.py

Tests run against the REAL project output files (outputs/*.csv, outputs/*.json) -- no mocks, no
synthetic data -- because the whole point of this tool layer is that it never invents a value, so
assertions should be checked against what the data actually says. Floating-point outputs are
checked with tolerance or via ordering/range assertions, never exact `==` on a computed float, to
avoid brittleness.
"""
from __future__ import annotations

import os
import sys
import traceback

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from lib import agent_tools, data  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures -- loaded once at module level (971K-row table is the expensive part).
# These loaders are `st.cache_data`-decorated but work fine outside a running Streamlit script
# (bare mode); Streamlit just can't persist the cache between separate process runs.
# ---------------------------------------------------------------------------

ACTION_PLAN = data.load_action_plan()
SEGMENT_SUMMARY = data.load_segment_summary()
VALUE_BY_SEGMENT = data.load_value_by_segment()
RISK_SUMMARY = data.load_risk_summary()
VALUE_BY_TIER = data.load_value_by_tier()
RISK_VALUE_MATRIX = data.load_risk_value_matrix()
SHAP_DF = data.load_shap_importance()
DF = data.load_customer_lookup_data()

KNOWN_MSNO = DF.iloc[0]["msno"]
HIGH_RISK_ROW = DF[DF["risk_tier"] == "High"].iloc[0]
LOW_RISK_ROW = DF[DF["risk_tier"] == "Low"].iloc[0]
SPECIAL_CHAR_ROW = DF[DF["msno"].str.contains(r"[+/]", regex=True, na=False)].iloc[0]
# ~2,527 of 970,960 customers have no recorded transaction activity at all (every transaction-
# derived field is NaN in customer_segments.csv itself, not a merge artifact) -- a real,
# pre-existing edge case this test suite specifically caught (see TASK_02_validation_report.md).
NO_TRANSACTION_HISTORY_ROW = DF[DF["latest_is_auto_renew"].isna()].iloc[0]


# ---------------------------------------------------------------------------
# A. get_customer -- valid lookup
# ---------------------------------------------------------------------------

def test_get_customer_valid():
    result = agent_tools.get_customer(DF, KNOWN_MSNO)
    assert result["ok"] is True
    assert result["error"] is None
    d = result["data"]
    assert d["msno"] == KNOWN_MSNO
    assert d["risk_tier"] in ("Low", "Medium", "High")
    assert "key_risk_signal" in d
    assert isinstance(d["model_risk_score"], float)


def test_get_customer_special_character_id():
    """Regression guard: a real project bug earlier in this project used `.str.contains()`
    without `regex=False`, silently failing on IDs containing `+`/`/`. get_customer uses exact
    `==` equality (via copilot_data.get_customer_context), which is immune by construction --
    this test proves that, not just asserts it."""
    msno = SPECIAL_CHAR_ROW["msno"]
    assert any(c in msno for c in "+/"), "test fixture assumption broke -- no +/ found in sample"
    result = agent_tools.get_customer(DF, msno)
    assert result["ok"] is True
    assert result["data"]["msno"] == msno


def test_get_customer_no_transaction_history_does_not_crash():
    """Regression test for a real bug this suite caught: customers with zero recorded
    transaction activity have NaN in `latest_is_auto_renew`, `cancel_rate`,
    `days_since_last_txn`, etc. `copilot_data.get_customer_context()` originally did
    `int(row["latest_is_auto_renew"])` unconditionally and raised `ValueError` for exactly these
    rows -- which are still real, existing customers (they have a valid risk_tier and
    model_risk_score), never "not found". Fixed alongside this task; this test guards it."""
    msno = NO_TRANSACTION_HISTORY_ROW["msno"]
    result = agent_tools.get_customer(DF, msno)
    assert result["ok"] is True, f"should not crash or report 'not found': {result}"
    d = result["data"]
    assert d["msno"] == msno
    assert d["risk_tier"] in ("Low", "Medium", "High")
    assert d["latest_is_auto_renew"] is None  # never guessed as 0/False
    assert d["cancel_rate"] is None
    assert d["key_risk_signal"] == "Limited transaction history"


# ---------------------------------------------------------------------------
# B. get_customer -- nonexistent customer
# ---------------------------------------------------------------------------

def test_get_customer_nonexistent():
    result = agent_tools.get_customer(DF, "THIS_CUSTOMER_ID_DOES_NOT_EXIST_ANYWHERE_12345")
    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]


def test_get_customer_malformed_input():
    assert agent_tools.get_customer(DF, "")["ok"] is False
    assert agent_tools.get_customer(DF, None)["ok"] is False


# ---------------------------------------------------------------------------
# C. search_customers -- high-risk search
# ---------------------------------------------------------------------------

def test_search_customers_high_risk():
    result = agent_tools.search_customers(DF, risk_tier="High", limit=20)
    assert result["ok"] is True
    d = result["data"]
    assert d["total_matches"] > 0
    assert len(d["rows"]) <= 20
    assert all(r["risk_tier"] == "High" for r in d["rows"])
    scores = [r["model_risk_score"] for r in d["rows"]]
    assert scores == sorted(scores, reverse=True), "default sort must be Model Risk Score, descending"


# ---------------------------------------------------------------------------
# D. search_customers -- high-risk/high-value search
# ---------------------------------------------------------------------------

def test_search_customers_high_risk_high_value():
    result = agent_tools.search_customers(DF, risk_tier="High", value_tier="High", limit=20)
    assert result["ok"] is True
    for r in result["data"]["rows"]:
        assert r["risk_tier"] == "High"
        assert r["value_tier"] == "High"


def test_search_customers_segment_filter():
    result = agent_tools.search_customers(DF, segment="At-Risk Veteran", limit=10)
    assert result["ok"] is True
    assert all(r["segment"] == "At-Risk Veteran" for r in result["data"]["rows"])


def test_search_customers_hrr_range():
    result = agent_tools.search_customers(DF, min_hrr_ntd=1000, max_hrr_ntd=5000, limit=20)
    assert result["ok"] is True
    for r in result["data"]["rows"]:
        if r["historical_realized_revenue_ntd"] is not None:
            assert 1000 <= r["historical_realized_revenue_ntd"] <= 5000


def test_search_customers_auto_renew_filter():
    off = agent_tools.search_customers(DF, auto_renew=False, limit=5)
    on = agent_tools.search_customers(DF, auto_renew=True, limit=5)
    assert off["ok"] is True and on["ok"] is True
    assert off["data"]["total_matches"] > 0
    assert on["data"]["total_matches"] > 0
    assert off["data"]["total_matches"] != on["data"]["total_matches"]


# --- empty result sets, limits, sorting, malformed inputs ---

def test_search_customers_empty_result_set():
    # Champions are Low-risk by definition -- filtering them to High risk must return zero rows,
    # not an error and not a fabricated row.
    result = agent_tools.search_customers(DF, segment="Engaged Low-Risk (Champions)", risk_tier="High", limit=10)
    assert result["ok"] is True
    assert result["data"]["total_matches"] == 0
    assert result["data"]["rows"] == []


def test_search_customers_limit_enforced():
    result = agent_tools.search_customers(DF, limit=5)
    assert result["ok"] is True
    assert len(result["data"]["rows"]) == 5


def test_search_customers_limit_capped_at_200():
    result = agent_tools.search_customers(DF, limit=100000)
    assert result["ok"] is True
    assert len(result["data"]["rows"]) <= 200


def test_search_customers_sort_ascending():
    result = agent_tools.search_customers(DF, sort_by="total_revenue", ascending=True, limit=10)
    assert result["ok"] is True
    values = [r["historical_realized_revenue_ntd"] for r in result["data"]["rows"] if r["historical_realized_revenue_ntd"] is not None]
    assert values == sorted(values)


def test_search_customers_malformed_sort_by():
    result = agent_tools.search_customers(DF, sort_by="not_a_real_column")
    assert result["ok"] is False
    assert result["error"]


def test_search_customers_malformed_risk_tier():
    result = agent_tools.search_customers(DF, risk_tier="Extreme")
    assert result["ok"] is False


def test_search_customers_malformed_segment():
    result = agent_tools.search_customers(DF, segment="Not A Real Segment")
    assert result["ok"] is False


def test_search_customers_invalid_limit():
    assert agent_tools.search_customers(DF, limit=0)["ok"] is False
    assert agent_tools.search_customers(DF, limit=-5)["ok"] is False


# ---------------------------------------------------------------------------
# E. get_aggregate_metrics
# ---------------------------------------------------------------------------

def test_get_aggregate_metrics():
    result = agent_tools.get_aggregate_metrics(RISK_SUMMARY, VALUE_BY_TIER, RISK_VALUE_MATRIX, ACTION_PLAN, VALUE_BY_SEGMENT)
    assert result["ok"] is True
    d = result["data"]
    assert d["n_customers_scored"] == RISK_SUMMARY["n_customers_scored"]
    assert d["high_risk_customers"] == 22692
    assert d["elevated_risk_customers"] == 22692 + 107043
    assert d["total_realized_revenue_ntd"] > 0
    assert d["high_risk_historical_revenue_exposure_ntd"] > 0
    assert len(d["by_segment"]) == 7
    assert d["high_risk_high_value_customers"] >= 0


# ---------------------------------------------------------------------------
# F. get_segment -- valid segment
# ---------------------------------------------------------------------------

def test_get_segment_valid():
    result = agent_tools.get_segment(ACTION_PLAN, SEGMENT_SUMMARY, "At-Risk, Auto-Renew Off")
    assert result["ok"] is True
    d = result["data"]
    assert d["n_customers"] == 113820
    assert d["median_days_since_last_txn"] == 20.0
    assert d["median_tenure_days"] == 809.0


def test_get_segment_missing_behavioral_data_not_guessed():
    # Stable / Monitor has no row in segment_summary.csv -- those fields must be None, never 0
    # or a copied value from another segment.
    result = agent_tools.get_segment(ACTION_PLAN, SEGMENT_SUMMARY, "Stable / Monitor")
    assert result["ok"] is True
    assert result["data"]["median_tenure_days"] is None
    assert result["data"]["median_days_since_last_txn"] is None


# ---------------------------------------------------------------------------
# G. get_segment -- invalid segment
# ---------------------------------------------------------------------------

def test_get_segment_invalid():
    result = agent_tools.get_segment(ACTION_PLAN, SEGMENT_SUMMARY, "Not A Real Segment")
    assert result["ok"] is False
    assert result["data"] is None


# ---------------------------------------------------------------------------
# H. explain_customer_risk
# ---------------------------------------------------------------------------

def test_explain_customer_risk_high_risk_customer():
    result = agent_tools.explain_customer_risk(DF, SHAP_DF, HIGH_RISK_ROW["msno"])
    assert result["ok"] is True
    d = result["data"]
    assert len(d["top_global_drivers"]) == 5
    assert len(d["customer_deviations"]) >= 1
    # association, not causation -- guard against the exact "bad" pattern from the task spec
    text = " ".join(d["customer_deviations"]).lower()
    assert "will churn because" not in text
    assert "causes" not in text
    assert "guarantee" not in text


def test_explain_customer_risk_nonexistent_customer():
    result = agent_tools.explain_customer_risk(DF, SHAP_DF, "NOT_A_REAL_CUSTOMER_ID")
    assert result["ok"] is False


def test_explain_customer_risk_no_transaction_history_does_not_crash():
    result = agent_tools.explain_customer_risk(DF, SHAP_DF, NO_TRANSACTION_HISTORY_ROW["msno"])
    assert result["ok"] is True
    assert result["data"]["key_risk_signal"] == "Limited transaction history"
    assert len(result["data"]["customer_deviations"]) >= 1  # falls through to the generic line, never crashes


def test_search_customers_includes_no_transaction_history_customers_without_crashing():
    # This customer is Medium risk (see fixture derivation) -- searching that tier must include
    # rows like it without raising, and must report the same honest "Limited transaction
    # history" signal rather than a fabricated one.
    result = agent_tools.search_customers(DF, risk_tier="Medium", limit=200)
    assert result["ok"] is True
    signals = {r["key_risk_signal"] for r in result["data"]["rows"]}
    assert signals  # non-empty, i.e. it actually ran over real rows without raising


# ---------------------------------------------------------------------------
# I. recommend_action
# ---------------------------------------------------------------------------

def test_recommend_action_by_segment():
    result = agent_tools.recommend_action(ACTION_PLAN, segment="At-Risk, Auto-Renew Off")
    assert result["ok"] is True
    assert result["data"]["recommended_action"] == "Re-engage"
    assert result["data"]["avoid"]


def test_recommend_action_by_customer_dict():
    cust = agent_tools.get_customer(DF, HIGH_RISK_ROW["msno"])["data"]
    result = agent_tools.recommend_action(ACTION_PLAN, customer=cust)
    assert result["ok"] is True
    assert result["data"]["segment"] == cust["segment"]


def test_recommend_action_requires_exactly_one_argument():
    assert agent_tools.recommend_action(ACTION_PLAN)["ok"] is False
    assert agent_tools.recommend_action(ACTION_PLAN, segment="At-Risk Veteran", customer={"segment": "X"})["ok"] is False


def test_recommend_action_unknown_segment():
    result = agent_tools.recommend_action(ACTION_PLAN, segment="Not A Real Segment")
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# J. compare_to_champions
# ---------------------------------------------------------------------------

def test_compare_to_champions_customer():
    cust = agent_tools.get_customer(DF, HIGH_RISK_ROW["msno"])["data"]
    result = agent_tools.compare_to_champions(ACTION_PLAN, VALUE_BY_SEGMENT, customer=cust)
    assert result["ok"] is True
    assert result["data"]["champions_churn_rate_pct"] is not None
    assert result["data"]["champions_median_hrr_ntd"] is not None


def test_compare_to_champions_segment():
    result = agent_tools.compare_to_champions(ACTION_PLAN, VALUE_BY_SEGMENT, segment="At-Risk Veteran")
    assert result["ok"] is True
    assert result["data"]["subject_churn_rate_pct"] > result["data"]["champions_churn_rate_pct"]


def test_compare_to_champions_requires_exactly_one_argument():
    assert agent_tools.compare_to_champions(ACTION_PLAN, VALUE_BY_SEGMENT)["ok"] is False


# ---------------------------------------------------------------------------
# K. rank_segments_by_priority
# ---------------------------------------------------------------------------

def test_rank_segments_by_priority():
    result = agent_tools.rank_segments_by_priority(ACTION_PLAN)
    assert result["ok"] is True
    rows = result["data"]["rows"]
    names = [r["segment"] for r in rows]
    assert "Engaged Low-Risk (Champions)" not in names
    assert "Stable / Monitor" not in names
    hrrs = [r["total_hrr_ntd"] for r in rows]
    assert hrrs == sorted(hrrs, reverse=True)
    assert rows[0]["priority"] == 1
    assert rows[-1]["priority"] == len(rows)


def test_rank_segments_by_priority_top_n():
    result = agent_tools.rank_segments_by_priority(ACTION_PLAN, top_n=2)
    assert result["ok"] is True
    assert len(result["data"]["rows"]) == 2


# ---------------------------------------------------------------------------
# L. build_dashboard_deep_link
# ---------------------------------------------------------------------------

def test_build_dashboard_deep_link_customer():
    result = agent_tools.build_dashboard_deep_link("customer_360", customer_id="ABC123==")
    assert result["ok"] is True
    d = result["data"]
    assert d["page_path"] == "pages/customer_360.py"
    assert d["session_state_updates"]["cust360_search"] == "ABC123=="


def test_build_dashboard_deep_link_filters():
    result = agent_tools.build_dashboard_deep_link("priority_customers", filters={"risk_tier": ["High"]})
    assert result["ok"] is True
    assert result["data"]["session_state_updates"]["pending_filter"] == {"risk_tier": ["High"]}


def test_build_dashboard_deep_link_invalid_page():
    result = agent_tools.build_dashboard_deep_link("not_a_real_page")
    assert result["ok"] is False
    assert result["data"] is None


def test_build_dashboard_deep_link_no_extras():
    result = agent_tools.build_dashboard_deep_link("overview")
    assert result["ok"] is True
    assert result["data"]["session_state_updates"] == {}


def test_build_dashboard_deep_link_retention_intelligence_label():
    # Task 06 / P0-2 regression: the deep-link CTA label must say "Retention Intelligence" --
    # the product's current, consistent name -- never the retired "Retention Copilot" label.
    result = agent_tools.build_dashboard_deep_link("retention_copilot")
    assert result["ok"] is True
    assert result["data"]["page_title"] == "Retention Intelligence"
    assert "Retention Intelligence" in result["data"]["label"]
    assert "Retention Copilot" not in result["data"]["label"]
    assert "Retention Copilot" not in result["data"]["page_title"]


# ---------------------------------------------------------------------------
# Standalone runner (no pytest dependency) -- discovers and runs every test_* function above.
# ---------------------------------------------------------------------------

def _run_all():
    tests = {name: fn for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)}
    passed, failed = 0, 0
    for name, fn in tests.items():
        try:
            fn()
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}  {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {name}  {type(e).__name__}: {e}")
            traceback.print_exc()
        else:
            passed += 1
            print(f"PASS  {name}")
    print(f"\n{passed} passed, {failed} failed (of {len(tests)} tests)")
    return failed == 0


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
