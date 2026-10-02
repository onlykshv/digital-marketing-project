"""Regression tests for the final-submission fixes of task_1/FINAL_PRESENTATION_READINESS_AUDIT.md.

A1/A2 -- at-risk customers shown as "Monitor only" / "low churn risk". marketing_action_plan.csv
   defines `Stable / Monitor` as the Low-risk default bucket minus the 5,890-customer
   "Unmatched At-Risk (no segment)" residual, but outputs/customer_segments.csv labels exactly those
   5,890 Medium/High-risk customers `Stable / Monitor`. `data.load_customer_lookup_data()` now
   applies the action plan's own rule (`data.resolve_segment`) at load time; the file is untouched.
A3 -- a calibrated probability shown as exactly "100%". `theme.fmt_probability` shows anything that
   would round to 0% / 100% as "<1%" / ">99%"; the numbers themselves are unchanged.
A4 -- the segment-mode "How does this segment compare with Champions?" prompt had no segment
   comparison route and returned the generic overview. It is no longer offered.

Same conventions as every other test file here: real data, the real no-API-key environment, and
cross-page `st.page_link` asserted as the one expected AppTest harness exception.

Runnable standalone (`python tests/test_final_submission_fixes.py`) or via pytest.
"""
from __future__ import annotations

import os
import sys
import traceback

import pandas as pd

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from streamlit.testing.v1 import AppTest  # noqa: E402

from lib import agent, copilot_engine, data, theme  # noqa: E402

PAGES = f"{DASHBOARD_DIR}/pages"
DF = data.load_customer_lookup_data()
ACTION_PLAN = data.load_action_plan()

# The customer the 18 Sep audit found at the top of the default Priority Customers queue: High risk,
# file label Stable / Monitor, calibrated probability exactly 1.0.
AUDIT_TOP_MSNO = "2eO88OKrDzgAI2jGApB3ifm3yhEeCQNT2EZI2yv4ft0="


def _markdown(at) -> str:
    # injected <style> blocks are excluded: their CSS (e.g. "width: 100%") is not displayed text
    return "\n".join(
        str(m.value) for m in list(at.markdown) + list(at.caption) if not str(m.value).lstrip().startswith("<style")
    )


def _is_harness_navigation_error(at) -> bool:
    return len(at.exception) == 1 and any(
        s in str(at.exception[0]) for s in ("StreamlitPageNotFoundError", "Could not find page", "page_link")
    )


# ---------------------------------------------------------------------------
# A1 / A2 -- segment shown for at-risk customers
# ---------------------------------------------------------------------------

def test_resolve_segment_moves_only_elevated_risk_stable_monitor_customers():
    assert data.resolve_segment("High", "Stable / Monitor") == "Unmatched At-Risk (no segment)"
    assert data.resolve_segment("Medium", "Stable / Monitor") == "Unmatched At-Risk (no segment)"
    assert data.resolve_segment("Low", "Stable / Monitor") == "Stable / Monitor"
    assert data.resolve_segment("High", "At-Risk Veteran") == "At-Risk Veteran"
    assert data.resolve_segment("Low", "Engaged Low-Risk (Champions)") == "Engaged Low-Risk (Champions)"


def test_no_elevated_risk_customer_is_shown_as_stable_monitor():
    elevated = DF[DF["risk_tier"].isin(["High", "Medium"])]
    assert (elevated["segment"] == "Stable / Monitor").sum() == 0
    # ...and none of them inherits the Monitor-only playbook or its "low risk" explanation
    actions = set(elevated["segment"].astype(str).map(data.SHORT_ACTION_BY_SEGMENT))
    whys = set(elevated["segment"].astype(str).map(data.SHORT_WHY_BY_SEGMENT))
    assert "Monitor only" not in actions
    assert not any(w.startswith("Low risk") for w in whys)


def test_resolved_unmatched_group_matches_the_action_plan_definition():
    unmatched = DF[DF["segment"] == "Unmatched At-Risk (no segment)"]
    plan_n = int(ACTION_PLAN.loc[ACTION_PLAN["priority_group"] == "Unmatched At-Risk (no segment)", "n_customers"].iloc[0])
    assert len(unmatched) == plan_n == 5890
    assert set(unmatched["risk_tier"].astype(str)) == {"High", "Medium"}
    assert (unmatched["segment_file_label"] == "Stable / Monitor").all()
    # Low-risk Stable / Monitor customers are untouched
    stable = DF[DF["segment"] == "Stable / Monitor"]
    assert set(stable["risk_tier"].astype(str)) == {"Low"}
    assert len(stable) == int(ACTION_PLAN.loc[ACTION_PLAN["priority_group"] == "Stable / Monitor", "n_customers"].iloc[0])


def test_underlying_outputs_file_and_scores_are_preserved():
    raw = pd.read_csv(data.OUTPUTS_DIR / "customer_segments.csv", usecols=["msno", "risk_tier", "segment"])
    # the file still carries its own labels -- nothing was rewritten on disk
    file_gap = raw[raw["risk_tier"].isin(["High", "Medium"]) & (raw["segment"] == "Stable / Monitor")]
    assert len(file_gap) == 5890
    # the loaded table keeps that label verbatim alongside the resolved group, and no risk tier moved
    merged = raw.merge(DF[["msno", "risk_tier", "segment_file_label"]], on="msno", suffixes=("_file", ""))
    assert len(merged) == len(raw)
    assert (merged["segment"] == merged["segment_file_label"].astype(str)).all()
    assert (merged["risk_tier_file"] == merged["risk_tier"].astype(str)).all()


def test_contact_first_answer_never_recommends_monitor_only():
    result = agent.ask("Who should we contact first?", agent.AgentContext(
        action_plan=ACTION_PLAN, segment_summary=data.load_segment_summary(),
        value_by_segment=data.load_value_by_segment(), risk_summary=data.load_risk_summary(),
        value_by_tier=data.load_value_by_tier(), risk_value_matrix=data.load_risk_value_matrix(),
        shap_df=data.load_shap_importance(), customer_df=DF,
    ))
    rows = agent.get_tool_result(result, "search_customers")["rows"]
    assert rows and all(r["risk_tier"] == "High" for r in rows)
    assert all(r["segment"] != "Stable / Monitor" for r in rows)
    assert "Monitor only" not in result.answer


def test_audit_top_customer_profile_shows_an_at_risk_playbook():
    row = DF[DF["msno"] == AUDIT_TOP_MSNO].iloc[0]
    assert str(row["risk_tier"]) == "High" and str(row["segment_file_label"]) == "Stable / Monitor"

    at = AppTest.from_file(f"{PAGES}/customer_360.py", default_timeout=300)
    at.session_state["lookup_loaded"] = True
    at.session_state["cust360_search"] = AUDIT_TOP_MSNO
    at.run()
    assert not at.exception or _is_harness_navigation_error(at)
    text = _markdown(at)
    assert AUDIT_TOP_MSNO in text
    assert "Standard outreach" in text
    assert "Monitor only" not in text
    assert "Low risk and no standout value signal" not in text
    assert "matches none of the named at-risk segment rules" in text


# ---------------------------------------------------------------------------
# A3 -- calibrated probability never displayed as a certainty
# ---------------------------------------------------------------------------

def test_fmt_probability_never_shows_zero_or_one_hundred_percent():
    assert theme.fmt_probability(1.0) == ">99%"
    assert theme.fmt_probability(0.996) == ">99%"
    assert theme.fmt_probability(0.994) == "99%"
    assert theme.fmt_probability(0.5) == "50%"
    assert theme.fmt_probability(0.006) == "1%"
    assert theme.fmt_probability(0.005) == "<1%"  # f"{0.5:.0f}" is "0" (round-half-even)
    assert theme.fmt_probability(0.004) == "<1%"
    assert theme.fmt_probability(0.0) == "<1%"
    assert theme.fmt_probability(None) == "—"
    assert theme.fmt_probability(float("nan")) == "—"
    for p in (i / 1000 for i in range(1001)):
        assert theme.fmt_probability(p) not in ("0%", "100%")


def test_retention_intelligence_probability_text_uses_the_same_bounds():
    assert copilot_engine._fmt_pct(1.0) == ">99%"
    assert copilot_engine._fmt_pct(0.0) == "<1%"
    assert copilot_engine._fmt_pct(None) == "not available"


def test_saturated_probabilities_are_preserved_in_the_data():
    # display-only: the calibrated values that motivated the fix are still exactly 1.0 / 0.0
    assert float(DF["calibrated_probability"].max()) == 1.0
    assert float(DF["calibrated_probability"].min()) == 0.0
    assert float(DF.loc[DF["msno"] == AUDIT_TOP_MSNO, "calibrated_probability"].iloc[0]) == 1.0


def test_audit_top_customer_probability_is_shown_as_above_99_not_100():
    at = AppTest.from_file(f"{PAGES}/customer_360.py", default_timeout=300)
    at.session_state["lookup_loaded"] = True
    at.session_state["cust360_search"] = AUDIT_TOP_MSNO
    at.run()
    text = _markdown(at)
    assert "&gt;99%" in text or ">99%" in text
    assert "100%" not in text


def test_no_page_formats_the_calibrated_probability_by_hand():
    for page in ("customer_360.py", "priority_customers.py"):
        src = open(f"{PAGES}/{page}", encoding="utf-8").read()
        assert "calibrated_probability'] * 100" not in src, page
        assert "theme.fmt_probability(" in src, page


# ---------------------------------------------------------------------------
# A4 -- no segment-mode Champions comparison prompt
# ---------------------------------------------------------------------------

def test_segment_mode_does_not_offer_a_champions_comparison():
    at = AppTest.from_file(f"{PAGES}/retention_copilot.py", default_timeout=300)
    at.session_state["lookup_loaded"] = True
    at.session_state["cust360_search"] = ""
    at.session_state["copilot_segment_choice"] = "At-Risk, Auto-Renew Off"
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert not any("compare with Champions" in l for l in labels)
    for q in ("Tell me about At-Risk, Auto-Renew Off customers.", "Why is this segment important?",
              "What should we do with this segment?"):
        assert q in labels


def test_customer_mode_champions_comparison_is_still_offered():
    # The customer-mode prompt has a real route (classify_customer_intent -> compare_champions)
    # and must survive the segment-mode removal.
    assert copilot_engine.classify_customer_intent("How does this customer compare with Champions?") == "compare_champions"
    src = open(f"{PAGES}/retention_copilot.py", encoding="utf-8").read()
    assert '"How does this customer compare with Champions?"' in src
    assert '"How does this segment compare with Champions?"' not in src


# ---------------------------------------------------------------------------
# Claim-safety wording
# ---------------------------------------------------------------------------

def _dashboard_sources() -> dict[str, str]:
    import glob
    return {f: open(f, encoding="utf-8").read() for f in glob.glob("lib/*.py") + glob.glob("pages/*.py")}


def test_historical_revenue_is_never_described_as_at_stake_or_at_risk():
    # HRR is money already collected; "at stake" / "revenue at risk" read as a forecast of loss.
    for f, src in _dashboard_sources().items():
        low = src.lower()
        assert "at stake" not in low, f
        assert "revenue at risk" not in low, f


def test_no_page_promises_an_outcome_from_outreach():
    # There is no campaign-response data, so no surface may claim outreach "pays off".
    for f, src in _dashboard_sources().items():
        assert "pays off" not in src.lower(), f


def test_newcomer_wording_states_the_rule_not_a_cause():
    for text in (data.SHORT_WHY_BY_SEGMENT["At-Risk Newcomer"], data.AVOID_BY_SEGMENT["At-Risk Newcomer"]):
        assert "onboarding gap" not in text and "points to" not in text
    assert "short tenure" in data.AVOID_BY_SEGMENT["At-Risk Newcomer"]


def test_unitless_revenue_per_transaction_gets_its_currency():
    out = theme.convert_ntd_mentions_in_text("avg revenue/txn 305 vs 150 overall (higher-value transactions)")
    assert out == f"avg revenue/txn {theme.fmt_currency(305)} vs {theme.fmt_currency(150)} overall (higher-value transactions)"
    assert "305" not in out and "₹" in out


def test_segment_answer_shows_revenue_per_transaction_with_a_currency():
    from lib import copilot_data
    action_plan, summary = data.load_action_plan(), data.load_segment_summary()
    raw_hits = action_plan[action_plan["defining_characteristics"].str.contains("avg revenue/txn", na=False)]
    assert len(raw_hits), "fixture: at least one segment states a revenue-per-transaction comparison"
    seg_name = raw_hits.iloc[0]["priority_group"]
    seg = copilot_data.get_segment_context(action_plan, summary, seg_name)
    answer = copilot_engine.deterministic_segment_answer("segment_overview", seg)
    rendered = " ".join([answer.why] + list(answer.evidence))
    assert "avg revenue/txn ₹" in rendered
    assert "avg revenue/txn 305" not in rendered and "avg revenue/txn 73" not in rendered


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
