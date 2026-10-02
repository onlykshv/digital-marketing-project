"""Tests for the Task 04 flagship Retention Intelligence page (dashboard/pages/retention_copilot.py)
and its supporting rendering components (dashboard/lib/components.py: `priority_list`,
`agent_response_block`) and the small agent.py addition this task needed (`ToolCallRecord.result`,
`agent.get_tool_result`).

Two kinds of tests, same separation of concerns as `tests/test_agent_orchestration.py`:

1. UI-level tests via `streamlit.testing.v1.AppTest`, run against the REAL, current environment
   (no ANTHROPIC_API_KEY) -- these exercise the actual page a manager would see today, including
   the deterministic fallback path, exactly as it runs live.
2. Data-layer tests of the "customer-list query" / "deep-link generation" paths via a mocked LLM
   + `agent.ask()` directly (the same mocking approach already established in
   `test_agent_orchestration.py`) -- these prove the data agent.py hands to the UI layer
   (`get_tool_result`, `ToolCallRecord.result`) is correct, without trying to simulate a full
   multi-page browser navigation inside AppTest (that mechanism -- `st.switch_page` plus the
   shared `cust360_search` session key -- is the exact same one already proven working live,
   repeatedly, for Priority Customers' and Customer 360's existing cross-page handoffs).

Runnable standalone (`python tests/test_retention_intelligence_ui.py`) or via pytest.
"""
from __future__ import annotations

import os
import sys
import traceback
from unittest import mock

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from streamlit.testing.v1 import AppTest  # noqa: E402

from lib import agent, data, llm_provider  # noqa: E402

PAGE = f"{DASHBOARD_DIR}/pages/retention_copilot.py"


def markdown_text(at) -> str:
    return " ".join(m.value for m in at.markdown)


# ---------------------------------------------------------------------------
# 1. Initial empty state
# ---------------------------------------------------------------------------

def test_initial_empty_state():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    text = markdown_text(at)
    assert "RETENTION INTELLIGENCE" in text
    assert "Ask a question about customers, risk, value, or retention actions." in text
    # centerpiece, not a dead end -- suggested prompts are already visible, no data load required
    labels = [b.label for b in at.button]
    assert "Who should we contact first?" in labels


# ---------------------------------------------------------------------------
# 2. Suggested prompt interaction
# ---------------------------------------------------------------------------

def test_suggested_prompt_interaction():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    btn = next(b for b in at.button if b.label == "How many customers are at elevated risk?")
    btn.click().run()
    assert not at.exception
    text = markdown_text(at)
    assert "You asked" in text
    assert "elevated risk" in text.lower()
    # Regression guard: a real ordering bug this task's own testing caught -- the empty-state
    # hero must never render on the SAME turn as the answer it was supposed to be replaced by
    # (has_context_or_history was originally evaluated before the button click had a chance to
    # set copilot_asked in that same script run). Fixed via a deferred st.container() slot.
    assert "Ask a question about customers, risk, value, or retention actions." not in text


# ---------------------------------------------------------------------------
# 3. Free-text question
# ---------------------------------------------------------------------------

def test_free_text_question():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    free = next(w for w in at.text_input if w.key == "copilot_freetext")
    free.set_value("Which segment should we prioritize?").run()
    assert not at.exception
    text = markdown_text(at)
    assert "You asked" in text


# ---------------------------------------------------------------------------
# 4. Customer context
# ---------------------------------------------------------------------------

def test_customer_context():
    # NOTE: this hits the same pre-existing, already-documented AppTest harness limitation as
    # Overview's CTA in every prior task's report: AppTest.from_file() runs a page in isolation,
    # outside app.py's st.navigation() page registry, so any st.page_link() call on this run
    # raises StreamlitPageNotFoundError. It is not a real bug -- the identical pattern (Priority
    # Customers -> Customer 360, Customer 360 -> Retention Intelligence) has been confirmed
    # working live in the browser repeatedly. We assert the specific expected exception rather
    # than pretending it doesn't happen.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    next(b for b in at.button if b.label == "Load customer data").click().run()
    assert not at.exception

    df = data.load_customer_lookup_data()
    known_msno = df.iloc[0]["msno"]
    search = next(w for w in at.text_input if w.key == "copilot_search_widget")
    search.set_value(known_msno).run()
    assert len(at.exception) == 1
    assert "StreamlitPageNotFoundError" in str(at.exception[0]) or "page_link" in str(at.exception[0]).lower() or "Could not find page" in str(at.exception[0])
    text = markdown_text(at)
    assert "Analysing customer" in text
    assert known_msno in text


# ---------------------------------------------------------------------------
# 5. Segment context
# ---------------------------------------------------------------------------

def test_segment_context():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    seg = next(w for w in at.selectbox if w.key == "copilot_segment_choice")
    seg.select("At-Risk Veteran").run()
    assert not at.exception
    text = markdown_text(at)
    assert "Segment in focus" in text
    assert "At-Risk Veteran" in text


# ---------------------------------------------------------------------------
# 6. Aggregate query -- numbers in the rendered answer must match the real source file
# ---------------------------------------------------------------------------

def test_aggregate_query_numbers_are_real():
    risk_summary = data.load_risk_summary()
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    btn = next(b for b in at.button if b.label == "How many customers are at elevated risk?")
    btn.click().run()
    assert not at.exception
    text = markdown_text(at)
    assert f"{risk_summary['n_customers_scored']:,}" in text


# ---------------------------------------------------------------------------
# 7. Customer-list query -- via mocked LLM tool loop + agent.ask() directly (data layer, not
#    full AppTest rendering -- see module docstring for why).
# ---------------------------------------------------------------------------

def _fake_response(stop_reason="end_turn", text="", tool_calls=None):
    tool_calls = tool_calls or []
    raw = ([{"type": "text", "text": text}] if text else []) + [
        {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["input"]} for c in tool_calls
    ]
    return {"stop_reason": stop_reason, "text": text, "tool_calls": tool_calls, "raw_content": raw}


def test_customer_list_query_populates_priority_list_data():
    action_plan = data.load_action_plan()
    segment_summary = data.load_segment_summary()
    value_by_segment = data.load_value_by_segment()
    risk_summary = data.load_risk_summary()
    value_by_tier = data.load_value_by_tier()
    risk_value_matrix = data.load_risk_value_matrix()
    shap_df = data.load_shap_importance()
    df = data.load_customer_lookup_data()

    ctx = agent.AgentContext(
        action_plan=action_plan, segment_summary=segment_summary, value_by_segment=value_by_segment,
        risk_summary=risk_summary, value_by_tier=value_by_tier, risk_value_matrix=risk_value_matrix,
        shap_df=shap_df, customer_df=df,
    )
    responses = [
        _fake_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "search_customers", "input": {"risk_tier": ["High"], "value_tier": ["High"], "limit": 5}}]),
        _fake_response(stop_reason="end_turn", text="Here are the highest-priority customers."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        response = agent.ask("Show me high-risk, high-value customers.", ctx)

    result_data = agent.get_tool_result(response, "search_customers")
    assert result_data is not None
    assert "rows" in result_data and "total_matches" in result_data
    assert all(set(r) >= {"msno", "risk_tier", "value_tier", "segment", "recommended_action"} for r in result_data["rows"])
    # this is exactly the shape components.priority_list() and agent_response_block() consume
    assert response.tool_calls[0].result["data"] is result_data


# ---------------------------------------------------------------------------
# 8. Customer selection -- the navigation mechanism itself (st.switch_page + the shared
#    cust360_search key), verified at the source level: this is the exact same mechanism
#    already proven live, repeatedly, for every other cross-page handoff in this app.
# ---------------------------------------------------------------------------

def test_priority_list_uses_the_proven_navigation_mechanism():
    src = open(f"{DASHBOARD_DIR}/lib/components.py", encoding="utf-8").read()
    assert "st.switch_page(\"pages/customer_360.py\")" in src
    assert 'st.session_state["cust360_search"] = msno' in src


# ---------------------------------------------------------------------------
# 9. Customer 360 -> Retention Intelligence handoff
# ---------------------------------------------------------------------------

def test_customer_360_handoff_link_present_and_branded():
    src = open(f"{DASHBOARD_DIR}/pages/customer_360.py", encoding="utf-8").read()
    assert 'st.page_link("pages/retention_copilot.py"' in src
    assert "Ask Retention Intelligence" in src


# ---------------------------------------------------------------------------
# 10. Deep-link generation
# ---------------------------------------------------------------------------

def test_deep_link_generation_via_mocked_tool_loop():
    action_plan = data.load_action_plan()
    ctx = agent.AgentContext(
        action_plan=action_plan, segment_summary=data.load_segment_summary(), value_by_segment=data.load_value_by_segment(),
        risk_summary=data.load_risk_summary(), value_by_tier=data.load_value_by_tier(), risk_value_matrix=data.load_risk_value_matrix(),
        shap_df=data.load_shap_importance(), customer_df=data.load_customer_lookup_data(),
    )
    known_msno = ctx.customer_df.iloc[0]["msno"]
    responses = [
        _fake_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "build_dashboard_deep_link", "input": {"target_page": "customer_360", "customer_id": known_msno}}]),
        _fake_response(stop_reason="end_turn", text="Here is the link to that customer's profile."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        response = agent.ask(f"Take me to {known_msno}", ctx)
    link_data = agent.get_tool_result(response, "build_dashboard_deep_link")
    assert link_data is not None
    assert link_data["page_path"] == "pages/customer_360.py"
    assert link_data["session_state_updates"]["cust360_search"] == known_msno


# ---------------------------------------------------------------------------
# 11. Fallback mode (real, live -- no key in this environment)
# ---------------------------------------------------------------------------

def test_fallback_mode_is_the_real_live_path():
    assert llm_provider.is_configured() is False
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    seg = next(w for w in at.selectbox if w.key == "copilot_segment_choice")
    seg.select("Engaged Low-Risk (Champions)").run()
    btn = next(b for b in at.button if "important" in b.label.lower())
    btn.click().run()
    assert not at.exception
    text = markdown_text(at)
    assert "AI synthesis" in text or "AI-assisted synthesis" in text or "not used" in text


# ---------------------------------------------------------------------------
# 12. Provenance rendering
# ---------------------------------------------------------------------------

def test_provenance_caption_present_and_honest():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    btn = next(b for b in at.button if b.label == "How many customers are at elevated risk?")
    btn.click().run()
    captions = " ".join(c.value for c in at.caption)
    assert "AI synthesis" in captions or "Grounded" in captions
    # never pretends the LLM answered when it didn't (no API key in this environment)
    assert "AI-synthesized." not in captions


# ---------------------------------------------------------------------------
# 13. Missing data (customer question asked before the large table is loaded)
# ---------------------------------------------------------------------------

def test_missing_customer_data_handled_gracefully():
    # Task 06/P1-07 regression: a customer is in focus but the large table hasn't been loaded --
    # this must say so honestly ("hasn't been loaded yet") rather than the different, misleading
    # claim "I couldn't find that customer" (which implies the ID was looked up and rejected,
    # when it was never looked up at all). Both facts are real; they must not be conflated.
    ctx = agent.AgentContext(
        action_plan=data.load_action_plan(), segment_summary=data.load_segment_summary(), value_by_segment=data.load_value_by_segment(),
        risk_summary=data.load_risk_summary(), value_by_tier=data.load_value_by_tier(), risk_value_matrix=data.load_risk_value_matrix(),
        shap_df=data.load_shap_importance(), customer_df=None, selected_customer_id="ANY_ID",
    )
    response = agent.ask("Why is this customer at risk?", ctx)
    assert response.grounded is False
    assert "hasn't been loaded yet" in response.answer.lower()
    assert "couldn't find" not in response.answer.lower()


# ---------------------------------------------------------------------------
# 14. Unknown customer
# ---------------------------------------------------------------------------

def test_unknown_customer_via_ui():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    next(b for b in at.button if b.label == "Load customer data").click().run()
    search = next(w for w in at.text_input if w.key == "copilot_search_widget")
    search.set_value("THIS_ID_DOES_NOT_EXIST_ANYWHERE_XYZ").run()
    assert not at.exception
    text = markdown_text(at)
    assert "couldn't find that customer" in text


# ---------------------------------------------------------------------------
# 15. Unsupported question
# ---------------------------------------------------------------------------

def test_unsupported_question_via_ui():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    free = next(w for w in at.text_input if w.key == "copilot_freetext")
    free.set_value("What's the weather like today?").run()
    assert not at.exception
    text = markdown_text(at)
    assert "unavailable" in text.lower()


# ---------------------------------------------------------------------------
# Task 06 / P0 regression tests -- the five audited blockers from
# test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md, exercised through the real page (AppTest) in
# the real, current no-API-key environment wherever a full page render applies.
# ---------------------------------------------------------------------------

# --- P0-1: every default general-mode suggested prompt must produce a valid response, never the
# generic "doesn't match a question this dashboard can answer" refusal. ---

_GENERIC_REFUSAL = "doesn't match a question this dashboard can answer"


def test_search_shaped_prompts_without_customer_data_loaded_guide_the_user():
    # Before "Load customer data" is clicked (the real, default first-open state), the two
    # search-shaped prompts must guide the manager to load data -- never crash, never the
    # generic refusal, never a fabricated result.
    for label in ["Who should we contact first?", "Show me high-risk, high-value customers."]:
        at = AppTest.from_file(PAGE, default_timeout=180)
        at.run()
        btn = next(b for b in at.button if b.label == label)
        btn.click().run()
        assert not at.exception, f"{label!r} raised an exception"
        text = markdown_text(at).lower()
        assert _GENERIC_REFUSAL not in text, f"{label!r} still hits the generic refusal"
        assert "load customer data" in text, f"{label!r} -> did not guide toward loading data: {text[:300]}"


def test_search_shaped_prompts_with_customer_data_loaded_produce_real_results():
    # NOTE: with real data loaded, both routes match well over 5 customers, so
    # components.agent_response_block() reaches its "View all N matching customers ->" deep-link
    # branch -- an st.page_link() call, which hits the SAME pre-existing, already-documented
    # AppTest harness limitation as every other cross-page link in this project
    # (AppTest.from_file() runs a page outside app.py's st.navigation() registry). Confirmed
    # working live in the browser for this exact link in TASK_04_validation_report.md. We assert
    # the specific expected exception, the same way test_customer_context already does, rather
    # than pretending it doesn't happen.
    for label, must_contain in [
        ("Who should we contact first?", "contact first"),
        ("Show me high-risk, high-value customers.", "priority zone"),
    ]:
        at = AppTest.from_file(PAGE, default_timeout=180)
        at.run()
        next(b for b in at.button if b.label == "Load customer data").click().run()
        btn = next(b for b in at.button if b.label == label)
        btn.click().run()
        assert len(at.exception) == 1, f"{label!r} raised an unexpected number of exceptions"
        assert "StreamlitPageNotFoundError" in str(at.exception[0]) or "Could not find page" in str(at.exception[0])
        text = markdown_text(at).lower()
        assert _GENERIC_REFUSAL not in text, f"{label!r} still hits the generic refusal"
        assert must_contain in text, f"{label!r} -> unexpected answer: {text[:300]}"
        assert "nt$" not in text  # P0-3: no raw NT$ anywhere in the rendered answer


def test_remaining_default_prompts_always_work_with_no_data_loaded():
    # P1-07: "Which segment needs attention?" / "How many customers are at elevated risk?" are
    # still default general-mode buttons and must still work with no data loaded.
    for label, must_contain in [
        # P1-10: the rank-segments answer now leads with the #1 segment as the Finding, not a
        # flat "ranked by retention priority" list header -- see test_agent_orchestration.py's
        # dedicated P1-10 tests for the full content/structure checks.
        ("Which segment needs attention?", "is the top retention priority"),
        ("How many customers are at elevated risk?", "overall churn rate"),
    ]:
        at = AppTest.from_file(PAGE, default_timeout=180)
        at.run()
        btn = next(b for b in at.button if b.label == label)
        btn.click().run()
        assert not at.exception, f"{label!r} raised an exception"
        text = markdown_text(at).lower()
        assert _GENERIC_REFUSAL not in text, f"{label!r} still hits the generic refusal"
        assert must_contain in text, f"{label!r} -> unexpected answer: {text[:300]}"


def test_customer_scoped_questions_no_longer_offered_as_general_mode_buttons():
    # P1-07: these two questions can only ever produce a "select a customer" guidance message
    # with no context, so they were deliberately removed from the general-mode suggested-question
    # buttons (see retention_copilot.py) -- offering a button that can never yield a real answer
    # is a false equivalence with the other four, working buttons. Free text can still ask them,
    # and still gets the same honest guidance as before (capability is unchanged, only what's
    # suggested as a first click).
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    labels = [b.label for b in at.button]
    assert "Why is this customer at risk?" not in labels
    assert "What should we do about this customer?" not in labels

    for question in ["Why is this customer at risk?", "What should we do about this customer?"]:
        at2 = AppTest.from_file(PAGE, default_timeout=180)
        at2.run()
        free = next(w for w in at2.text_input if w.key == "copilot_freetext")
        free.set_value(question).run()
        assert not at2.exception
        text = markdown_text(at2).lower()
        assert _GENERIC_REFUSAL not in text
        assert "search for a customer" in text


# --- P0-2: the product name is consistently "Retention Intelligence" in the nav and in every
# agent-facing/deep-link label. ---

def test_nav_page_title_is_retention_intelligence():
    src = open(f"{DASHBOARD_DIR}/app.py", encoding="utf-8").read()
    assert 'title="Retention Intelligence"' in src
    assert "Retention Copilot" not in src


# --- P0-3: currency consistency -- INR everywhere an agent answer shows money, and the display-
# only NT$ -> INR conversion is disclosed on this page (it wasn't, before this task). ---

def test_retention_intelligence_page_discloses_currency_display_conversion():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    text = markdown_text(at)
    assert "NT$" in text and "display-only" in text.lower()


# --- P0-5: Overview and Action Center each carry a restrained, context-preserving CTA into
# Retention Intelligence. Verified at the source level -- st.switch_page cross-page navigation
# is the same proven mechanism already exercised live for every other handoff in this app (not
# re-testable inside a single-page AppTest run, per this file's own module docstring). ---

def test_overview_and_action_center_still_render_without_exception():
    # P1-08 update: Overview's former static st.page_link("pages/priority_customers.py", ...) --
    # which unconditionally hit the known AppTest harness limitation (isolated single-page runs
    # can't resolve st.page_link/st.switch_page) on every plain render, per every prior task's
    # report -- was replaced by a button that carries the portfolio-signal segment as a filter
    # (see tests/test_manager_workflow.py). A button only calls st.switch_page when actually
    # clicked, so a plain render of Overview is now genuinely exception-free.
    at1 = AppTest.from_file(f"{DASHBOARD_DIR}/pages/overview.py", default_timeout=180)
    at1.run()
    assert not at1.exception

    # Action Center has no page_link at all -- it must render with zero exceptions.
    at2 = AppTest.from_file(f"{DASHBOARD_DIR}/pages/action_center.py", default_timeout=180)
    at2.run()
    assert not at2.exception


def test_overview_links_to_retention_intelligence_with_segment_context():
    # Romer-layout redesign: the Overview's one RI button reads "Ask Retention Intelligence: why
    # does <segment> need attention?" (the former "...about <segment>" duplicate was merged into it).
    src = open(f"{DASHBOARD_DIR}/pages/overview.py", encoding="utf-8").read()
    assert "Ask Retention Intelligence" in src
    assert 'st.session_state["copilot_segment_choice"]' in src
    assert 'st.switch_page("pages/retention_copilot.py")' in src


def test_action_center_links_to_retention_intelligence_with_segment_context():
    src = open(f"{DASHBOARD_DIR}/pages/action_center.py", encoding="utf-8").read()
    assert "Ask Retention Intelligence about" in src
    assert 'st.session_state["copilot_segment_choice"]' in src
    assert 'st.switch_page("pages/retention_copilot.py")' in src


def test_overview_cta_button_is_present_in_the_rendered_page():
    at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/overview.py", default_timeout=180)
    at.run()
    labels = [b.label for b in at.button]
    assert any(l.startswith("Ask Retention Intelligence") for l in labels)


def test_action_center_cta_button_is_present_in_the_rendered_page():
    at = AppTest.from_file(f"{DASHBOARD_DIR}/pages/action_center.py", default_timeout=180)
    at.run()
    labels = [b.label for b in at.button]
    assert any(l.startswith("Ask Retention Intelligence about") for l in labels)


# ---------------------------------------------------------------------------
# P1-07 regression tests -- "Retention Intelligence Hero Experience"
# (task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx)
# ---------------------------------------------------------------------------

# --- A grounding indicator ("what is happening / who is in focus") must always be visible,
# never blank, in all three states: general, segment, customer. ---

def test_general_mode_shows_a_grounding_indicator_with_real_numbers():
    from lib import theme
    risk_summary = data.load_risk_summary()
    tiers_by_name = {t["tier"]: t for t in risk_summary["risk_tiers"]}
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    text = markdown_text(at)
    assert "Grounded in the full scored base" in text
    # the same theme.fmt_count formatting Overview uses for the identical field, not the raw
    # comma-formatted number
    assert theme.fmt_count(risk_summary["n_customers_scored"]) in text
    assert theme.fmt_count(tiers_by_name["High"]["n_customers"]) in text


def test_segment_mode_grounding_indicator_has_a_take_action_link():
    # Previously segment context had no outbound link at all (asymmetric with customer context,
    # which already linked to Customer 360) -- this is the P1-07 fix for that gap.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    seg = next(w for w in at.selectbox if w.key == "copilot_segment_choice")
    seg.select("At-Risk Veteran").run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert any(l == "View At-Risk Veteran customers in Priority Customers →" for l in labels)


def test_segment_take_action_button_sets_the_real_pending_filter_mechanism():
    src = open(f"{DASHBOARD_DIR}/pages/retention_copilot.py", encoding="utf-8").read()
    assert 'st.session_state["pending_filter"] = {"segment": [segment_choice]}' in src
    assert 'st.switch_page("pages/priority_customers.py")' in src


def test_customer_mode_still_has_its_existing_customer_360_link():
    # Regression guard: restructuring the context block into a deferred slot must not have
    # dropped the customer-context link that already worked.
    src = open(f"{DASHBOARD_DIR}/pages/retention_copilot.py", encoding="utf-8").read()
    assert 'st.page_link("pages/customer_360.py", label="Open full profile in Customer 360 →")' in src


# --- General-mode suggested questions are grouped to match the WHAT-IS-HAPPENING / WHO-NEEDS-
# ATTENTION start of the manager flow, and no longer offer a customer-scoped question that can
# never be answered without a customer selected. ---

def test_general_mode_suggested_questions_are_grouped_by_flow_step():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    text = markdown_text(at)
    assert "See what's happening" in text
    assert "Find who needs attention" in text
    labels = [b.label for b in at.button]
    assert "How many customers are at elevated risk?" in labels
    assert "Which segment needs attention?" in labels
    assert "Who should we contact first?" in labels
    assert "Show me high-risk, high-value customers." in labels


# --- The "Load customer data" gate is de-emphasized (quieter copy, not a primary/blocking-
# looking alert) but must remain fully functional -- same label, same effect. ---

def test_load_customer_data_gate_still_works_and_is_de_emphasized():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    text = markdown_text(at)
    assert "~971K rows" not in text  # the old, more technical wording is gone
    assert "Customer-level questions need the full customer table" in text
    btn = next(b for b in at.button if b.label == "Load customer data")
    btn.click().run()
    assert not at.exception
    # once loaded, the loading note is gone and a customer search actually resolves --
    # proof the click had its real effect, not just that it didn't crash
    assert "Customer-level questions need the full customer table" not in markdown_text(at)
    known_msno = data.load_customer_lookup_data().iloc[0]["msno"]
    search = next(w for w in at.text_input if w.key == "copilot_search_widget")
    search.set_value(known_msno).run()
    assert "Analysing customer" in markdown_text(at)


# --- Finding vs. Evidence vs. Confidence/Caution visual hierarchy in the answer itself
# (components.agent_response_block) -- a bounded improvement; the full evidence/recommendation
# template redesign is P1-11's job, not this ticket's. ---

def _render_fake_agent_response_for_hierarchy_test():
    # AppTest.from_function runs this in an isolated context with no closure over this module's
    # globals, so DASHBOARD_DIR must be a literal here, not a reference to the module-level name.
    import sys
    sys.path.insert(0, r"D:\digital-marketing-project\dashboard")
    from lib import components

    class FakeCall:
        tool, ok, result = "get_segment", True, {}

    class FakeResponse:
        answer = (
            "Recommendation: Re-engage before the next renewal window.\n"
            "Evidence: Auto-renew is off for 88 percent of this segment.\n"
            "Caution: Based on association, not a controlled experiment."
        )
        tools_used = ["get_segment"]
        tool_calls = [FakeCall()]
        grounded = True
        used_llm = False
        fallback_reason = "no AI provider is configured for this session"

    components.agent_response_block(FakeResponse())


def test_answer_finding_line_is_rendered_with_stronger_emphasis_than_evidence():
    at = AppTest.from_function(_render_fake_agent_response_for_hierarchy_test, default_timeout=180)
    at.run()
    assert not at.exception
    md_html = " ".join(m.value for m in at.markdown)
    assert "Re-engage before the next renewal window" in md_html
    assert "font-size:1.18rem" in md_html  # the Finding tier's distinct emphasis
    captions = " ".join(c.value for c in at.caption)
    assert "Caution: Based on association" in captions  # muted tier, rendered via st.caption


# ---------------------------------------------------------------------------
# P1-09 regression tests -- "Assistant Identity & Personality"
# (task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-09)
# ---------------------------------------------------------------------------

def test_page_eyebrow_is_a_deliberate_role_title_not_the_generic_old_one():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    text = markdown_text(at)
    assert "RETENTION OPERATIONS ASSISTANT" in text
    assert "AI ASSISTANT" not in text


def test_every_answer_carries_a_consistent_name_treatment():
    # The assistant's name appears immediately before its own answer, every time, the same way
    # "You asked" always precedes the manager's question -- a restrained, always-present identity
    # cue, not a one-off label.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    btn = next(b for b in at.button if b.label == "How many customers are at elevated risk?")
    btn.click().run()
    assert not at.exception
    text = markdown_text(at)
    assert "You asked" in text
    assert "Retention Intelligence responds" in text
    # the label must appear AFTER "You asked" (question first, then the named response), not just
    # somewhere on the page
    assert text.index("You asked") < text.index("Retention Intelligence responds")


def test_name_treatment_appears_for_customer_and_segment_answers_too():
    # Regression guard across all three context modes, not just the general/aggregate one.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    seg = next(w for w in at.selectbox if w.key == "copilot_segment_choice")
    seg.select("At-Risk Veteran").run()
    btn = next(b for b in at.button if "important" in b.label.lower())
    btn.click().run()
    assert not at.exception
    assert "Retention Intelligence responds" in markdown_text(at)


def test_spinner_names_the_assistant():
    src = open(PAGE, encoding="utf-8").read()
    assert 'st.spinner("Retention Intelligence is consulting the retention model…")' in src


def test_identity_change_did_not_alter_grounded_answer_content():
    # The identity/voice additions are presentation-only -- the actual evidence-backed numbers a
    # manager sees for a real question must be exactly what they already were.
    risk_summary = data.load_risk_summary()
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    btn = next(b for b in at.button if b.label == "How many customers are at elevated risk?")
    btn.click().run()
    text = markdown_text(at)
    assert f"{risk_summary['n_customers_scored']:,}" in text
    # Scope the currency check to the answer itself, not the page's own (correct, intentional)
    # methodology disclosure at the bottom, which legitimately names "NT$" as the source currency
    # (P0-3) -- only the agent's rendered answer text must never show a raw NT$ figure.
    #
    # P1-11: "not an expected loss" moved into the answer's new "Confidence/limitations:" line,
    # which components.agent_response_block now renders via st.caption (it was added to
    # components._MUTED_LABELS, matching the existing Confidence/basis/Caution treatment) rather
    # than st.markdown -- so it no longer appears in markdown_text(at). The boundary marker moves
    # to the end of the answer's last markdown-rendered line instead (the "Recommended next
    # step:" line, still a normal, non-muted line).
    answer_start = text.index("Retention Intelligence responds")
    answer_end = text.index("highest-priority customers directly.") + len("highest-priority customers directly.")
    answer_text = text[answer_start:answer_end]
    assert "nt$" not in answer_text.lower()


def test_no_emoji_or_fabricated_activity_language_introduced():
    # Explicit tracker constraint: "No emoji, cartoon avatar, gradients or fake activity."
    src = open(PAGE, encoding="utf-8").read()
    import re
    emoji_pattern = re.compile(
        "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
    )
    assert not emoji_pattern.search(src)
    assert "is typing" not in src.lower()
    assert "is thinking" not in src.lower()


# ---------------------------------------------------------------------------
# P1-11 regression tests -- "Structured Decision Answers"
# (task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-11)
#
# The formatter-level structure (line order, exact labels, terminology/causality guardrails) is
# already covered exhaustively in tests/test_agent_orchestration.py's P1-11 section. These tests
# cover only what that file cannot: how the restructured answer actually RENDERS on the real page
# -- the Confidence/limitations muted tier, and that every context mode (general/segment) and
# every existing link/handoff still works end to end, live, with no API key.
# ---------------------------------------------------------------------------

def test_confidence_limitations_line_renders_in_the_muted_caption_tier():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    btn = next(b for b in at.button if b.label == "How many customers are at elevated risk?")
    btn.click().run()
    assert not at.exception
    captions = " ".join(c.value for c in at.caption)
    assert "Confidence/limitations:" in captions
    assert "not an expected loss" in captions
    # must NOT also appear in the normal markdown flow (it should render exactly once, as a caption)
    assert "Confidence/limitations:" not in markdown_text(at)


def test_aggregate_answer_renders_why_it_matters_and_next_step_in_order_on_the_real_page():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    btn = next(b for b in at.button if b.label == "How many customers are at elevated risk?")
    btn.click().run()
    assert not at.exception
    text = markdown_text(at)
    assert "Why it matters:" in text
    assert "Recommended next step:" in text
    assert text.index("Why it matters:") < text.index("Recommended next step:")


def test_segment_answer_renders_the_full_six_part_structure_on_the_real_page():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    seg = next(w for w in at.selectbox if w.key == "copilot_segment_choice")
    seg.select("At-Risk Veteran").run()
    btn = next(b for b in at.button if "Tell me about" in b.label)
    btn.click().run()
    assert not at.exception
    text = markdown_text(at)
    captions = " ".join(c.value for c in at.caption)
    # The Finding tier (Recommendation:) strips its own label and renders only the value, styled
    # -- the exact same established mechanism Headline: already uses (see
    # components.agent_response_block / the P1-09 hierarchy test above) -- so this checks the
    # distinct styling, not literal "Recommendation:" text. Evidence/Why it matters/Recommended
    # action fall into the generic bold-label branch, so they DO keep their literal "**Label:**"
    # markdown text.
    assert "font-size:1.18rem" in text
    assert "**Evidence:**" in text
    assert "**Why it matters:**" in text
    assert "**Recommended action:**" in text
    assert "Confidence/limitations:" in captions  # muted tier, not the main markdown flow
    assert text.index("**Evidence:**") < text.index("**Why it matters:**")
    assert text.index("**Why it matters:**") < text.index("**Recommended action:**")
    # the genuinely applicable "next step" for a segment answer is the persistent
    # "View {segment} customers in Priority Customers ->" button already rendered above the
    # answer (context_slot) -- confirmed still present and unchanged by this restructure.
    labels = [b.label for b in at.button]
    assert "View At-Risk Veteran customers in Priority Customers →" in labels


def test_search_customer_answer_renders_the_full_structure_and_keeps_priority_list_working():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    next(b for b in at.button if b.label == "Load customer data").click().run()
    btn = next(b for b in at.button if b.label == "Who should we contact first?")
    btn.click().run()
    # Same pre-existing, already-documented AppTest harness limitation as every other cross-page
    # link in this project (st.page_link raises outside app.py's st.navigation() registry, since
    # the real base has well over 5 High-risk matches here) -- confirmed working live in the
    # browser repeatedly. Assert the specific expected exception, same pattern as
    # test_search_shaped_prompts_with_customer_data_loaded_produce_real_results above.
    assert len(at.exception) == 1
    assert "StreamlitPageNotFoundError" in str(at.exception[0]) or "Could not find page" in str(at.exception[0])
    text = markdown_text(at)
    captions = " ".join(c.value for c in at.caption)
    assert "**Why it matters:**" in text
    assert "**Recommended action:**" in text
    assert "Confidence/limitations:" in captions
    # the priority list (real customer rows, each with an "Open ->" handoff to Customer 360) must
    # still render before the restructured answer text's trailing link hits the harness limit.
    assert any(b.label == "Open →" for b in at.button)


def test_customer_360_and_priority_customers_source_level_links_unaffected_by_p1_11():
    # Regression guard: P1-11 only changed answer TEXT (agent.py) and one label set
    # (components._MUTED_LABELS) -- every cross-page handoff mechanism must be byte-identical.
    src = open(PAGE, encoding="utf-8").read()
    assert 'st.page_link("pages/customer_360.py", label="Open full profile in Customer 360 →")' in src
    assert 'st.session_state["pending_filter"] = {"segment": [segment_choice]}' in src
    components_src = open(f"{DASHBOARD_DIR}/lib/components.py", encoding="utf-8").read()
    assert 'st.session_state["cust360_search"] = msno' in components_src
    assert 'st.switch_page("pages/customer_360.py")' in components_src


# ---------------------------------------------------------------------------
# Free-text / suggested-prompt state regression tests
#
# The bug these cover was real and reproducible (not hypothetical), and it made a suggested-prompt
# button look broken: `st.text_input(key="copilot_freetext")` keeps its value in session state
# across every later rerun, and the page used to READ that value each run and treat it as "the
# question being asked" (`if free_q: st.session_state["copilot_asked"] = free_q`). Because the
# suggested-prompt buttons render ABOVE that widget, clicking one set `copilot_asked` and the
# still-populated free-text box then overwrote it further down the SAME script run -- so the click
# silently did nothing. Fixed by treating a free-text submission as the event it is (an on_change
# callback, which fires only on the rerun where new text was actually submitted) instead of as
# persistent state, and by clearing the box whenever the question it holds stops being the active
# one. No routing logic was duplicated: both question sources still only record WHICH question was
# asked, and the single `agent.ask()` call at the bottom of the page still answers it.
# ---------------------------------------------------------------------------

_FREE_Q = "Which segment should we prioritize?"
_SUGGESTED_Q = "How many customers are at elevated risk?"


def _asked_block(at) -> str:
    """The rendered 'You asked' question text -- what the manager actually sees, not just state."""
    return " ".join(m.value for m in at.markdown if 'class="qa-question-text' in m.value)


def _free_text_widget(at):
    return next(w for w in at.text_input if w.key == "copilot_freetext")


def test_free_text_then_suggested_prompt_actually_executes():
    # The reported bug, exactly: type a free-text question, then click a suggested prompt.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    _free_text_widget(at).set_value(_FREE_Q).run()
    assert not at.exception
    assert _FREE_Q in _asked_block(at)  # the free-text question really was asked first

    next(b for b in at.button if b.label == _SUGGESTED_Q).click().run()
    assert not at.exception
    # The suggested prompt must win -- in session state, in the rendered question, and in the
    # actual answer content (before the fix, all three still showed the stale free-text question).
    assert at.session_state["copilot_asked"] == _SUGGESTED_Q
    asked = _asked_block(at)
    assert _SUGGESTED_Q in asked
    assert _FREE_Q not in asked
    assert "overall churn rate" in markdown_text(at).lower()


def test_selecting_a_suggested_prompt_clears_the_free_text_box():
    # A question left sitting in the box after a different question was answered reads as if it
    # were still the active one -- and is what allowed it to re-assert itself on a later rerun.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    _free_text_widget(at).set_value(_FREE_Q).run()
    assert _free_text_widget(at).value == _FREE_Q
    next(b for b in at.button if b.label == _SUGGESTED_Q).click().run()
    assert at.session_state["copilot_freetext"] == ""
    assert _free_text_widget(at).value == ""


def test_suggested_prompt_then_free_text_executes():
    # The reverse direction: a suggested prompt answered first must not block a free-text question
    # submitted after it.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    next(b for b in at.button if b.label == _SUGGESTED_Q).click().run()
    assert at.session_state["copilot_asked"] == _SUGGESTED_Q

    _free_text_widget(at).set_value(_FREE_Q).run()
    assert not at.exception
    assert at.session_state["copilot_asked"] == _FREE_Q
    asked = _asked_block(at)
    assert _FREE_Q in asked
    assert _SUGGESTED_Q not in asked


def test_free_text_is_not_resubmitted_on_an_unrelated_rerun():
    # A rerun that has nothing to do with the question box (here: the "Load customer data" gate)
    # must not re-submit the free-text value. The previous ANSWER legitimately stays on screen --
    # it comes from `copilot_asked`, which is exactly the point: the box is no longer a second,
    # competing source of truth for what was asked.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    _free_text_widget(at).set_value(_FREE_Q).run()
    next(b for b in at.button if b.label == "Load customer data").click().run()
    assert not at.exception
    assert at.session_state["copilot_asked"] == _FREE_Q
    assert _FREE_Q in _asked_block(at)


def test_context_switch_clears_both_the_answer_and_the_free_text_box():
    # Switching focus already cleared the answer (so a stale one never looks like it belongs to the
    # new context), but the free-text box used to survive that clearing and immediately re-ask its
    # question against the NEW context on the same run.
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    _free_text_widget(at).set_value(_FREE_Q).run()
    assert "You asked" in markdown_text(at)

    next(w for w in at.selectbox if w.key == "copilot_segment_choice").select("At-Risk Veteran").run()
    assert not at.exception
    assert "Segment in focus" in markdown_text(at)
    assert "You asked" not in markdown_text(at)
    assert at.session_state["copilot_freetext"] == ""
    assert _free_text_widget(at).value == ""

    # ...and the newly-offered segment prompts still work normally from that clean state.
    next(b for b in at.button if "important" in b.label.lower()).click().run()
    assert not at.exception
    assert "Retention Intelligence responds" in markdown_text(at)


def test_fresh_session_asks_nothing_and_starts_with_an_empty_question_box():
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.run()
    assert not at.exception
    assert _free_text_widget(at).value in ("", None)
    assert "You asked" not in markdown_text(at)
    # the first-open empty state is still the centerpiece
    assert "Ask a question about customers, risk, value, or retention actions." in markdown_text(at)


def test_free_text_submission_is_event_driven_not_read_from_widget_state():
    # Source-level guard on the mechanism itself: the old read-and-assign pattern is what made a
    # stale value able to override a fresh click, so its return to this page should fail a test
    # rather than require re-finding the bug by hand.
    src = open(PAGE, encoding="utf-8").read()
    assert "on_change=_submit_free_text" in src
    assert "if free_q:" not in src
    # both question sources record the question only -- routing stays in the one agent.ask() call
    assert src.count("response = agent.ask(") == 1


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
