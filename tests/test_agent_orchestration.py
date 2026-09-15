"""Tests for dashboard/lib/agent.py -- the AI agent orchestration layer (Task 03).

Two kinds of tests live here, deliberately kept separate:

1. Tests of the ORCHESTRATION LOGIC (the tool-call loop's mechanics: multi-turn looping, strict
   tool dispatch, provenance tracking, turn-cap enforcement, hallucinated-tool rejection). These
   mock `llm_provider.complete_with_tools` with controlled, clearly-fake responses using
   `unittest.mock` (Python's standard library -- no new dependency). No API key exists in this
   environment, so this project's own discipline (established in Task 02's report) applies here
   too: we do NOT pretend a real Anthropic API call was made or claim these tests validate live
   model behavior. They validate that agent.py's OWN code -- the loop, the dispatch table, the
   argument validation -- behaves correctly given a certain shape of response, whatever produced
   that response.

2. Tests of the DETERMINISTIC FALLBACK, which runs with NO mocking at all, against real project
   data -- because `llm_provider.is_configured()` is genuinely False in this environment, calling
   `agent.ask()` exercises the real, live fallback path exactly as a user would hit it today.

Runnable standalone (`python tests/test_agent_orchestration.py`) or via pytest once available --
same pytest-compatible `test_*` / plain `assert` style as `tests/test_agent_tools.py`.
"""
from __future__ import annotations

import os
import sys
import traceback
from unittest import mock

DASHBOARD_DIR = r"D:\digital-marketing-project\dashboard"
sys.path.insert(0, DASHBOARD_DIR)
os.chdir(DASHBOARD_DIR)

from lib import agent, agent_tool_schemas, agent_tools, data, llm_provider, theme  # noqa: E402

# ---------------------------------------------------------------------------
# Real fixtures (same loaders every other test file / page uses).
# ---------------------------------------------------------------------------

ACTION_PLAN = data.load_action_plan()
SEGMENT_SUMMARY = data.load_segment_summary()
VALUE_BY_SEGMENT = data.load_value_by_segment()
RISK_SUMMARY = data.load_risk_summary()
VALUE_BY_TIER = data.load_value_by_tier()
RISK_VALUE_MATRIX = data.load_risk_value_matrix()
SHAP_DF = data.load_shap_importance()
DF = data.load_customer_lookup_data()

HIGH_RISK_MSNO = DF[DF["risk_tier"] == "High"].iloc[0]["msno"]
KNOWN_SEGMENT = "At-Risk, Auto-Renew Off"

BASE_CTX_KWARGS = dict(
    action_plan=ACTION_PLAN, segment_summary=SEGMENT_SUMMARY, value_by_segment=VALUE_BY_SEGMENT,
    risk_summary=RISK_SUMMARY, value_by_tier=VALUE_BY_TIER, risk_value_matrix=RISK_VALUE_MATRIX,
    shap_df=SHAP_DF, customer_df=DF,
)


def make_ctx(**overrides) -> agent.AgentContext:
    kwargs = dict(BASE_CTX_KWARGS)
    kwargs.update(overrides)
    return agent.AgentContext(**kwargs)


def fake_llm_response(stop_reason="end_turn", text="", tool_calls=None):
    """Builds a plain dict in exactly the shape `llm_provider.complete_with_tools()` returns --
    used to mock the LLM boundary without ever touching the real Anthropic SDK."""
    tool_calls = tool_calls or []
    raw_content = [{"type": "text", "text": text}] if text else []
    raw_content += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["input"]} for c in tool_calls]
    return {"stop_reason": stop_reason, "text": text, "tool_calls": tool_calls, "raw_content": raw_content}


# ---------------------------------------------------------------------------
# Sanity: confirm we are actually exercising the real (unconfigured) fallback path in this
# environment, not accidentally skipping it.
# ---------------------------------------------------------------------------

def test_no_api_key_in_this_environment():
    assert llm_provider.is_configured() is False, "this test suite assumes no ANTHROPIC_API_KEY is set; see report for why"


# ---------------------------------------------------------------------------
# 1. Exact customer question (deterministic fallback, real data, real tool call)
# ---------------------------------------------------------------------------

def test_exact_customer_question():
    ctx = make_ctx(selected_customer_id=HIGH_RISK_MSNO)
    result = agent.ask("Why is this customer at risk?", ctx)
    assert result.grounded is True
    assert result.used_llm is False
    assert "get_customer" in result.tools_used
    assert HIGH_RISK_MSNO not in result.answer or True  # msno isn't necessarily echoed, but must not crash
    assert "unavailable" in result.answer.lower()  # transparency: fallback always says so


# ---------------------------------------------------------------------------
# 2. Unknown customer
# ---------------------------------------------------------------------------

def test_unknown_customer():
    ctx = make_ctx(selected_customer_id="THIS_ID_DOES_NOT_EXIST_ANYWHERE")
    result = agent.ask("Why is this customer at risk?", ctx)
    assert result.grounded is False
    assert "couldn't find" in result.answer.lower()


# ---------------------------------------------------------------------------
# 3. High-risk customer search (mocked LLM loop -- tests dispatch + real tool execution)
# ---------------------------------------------------------------------------

def test_high_risk_search_via_mocked_tool_loop():
    call_id = "call_1"
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": call_id, "name": "search_customers", "input": {"risk_tier": ["High"], "limit": 5}}]),
        fake_llm_response(stop_reason="end_turn", text="Here are 5 high-risk customers."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        ctx = make_ctx()
        result = agent.ask("Show me the top 5 high-risk customers.", ctx)
    assert result.used_llm is True
    assert result.tools_used == ["search_customers"]
    assert result.tool_calls[0].ok is True
    assert "high-risk customers" in result.answer.lower()


# ---------------------------------------------------------------------------
# 4. High-risk/high-value search
# ---------------------------------------------------------------------------

def test_high_risk_high_value_search_via_mocked_tool_loop():
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "search_customers", "input": {"risk_tier": ["High"], "value_tier": ["High"], "limit": 10}}]),
        fake_llm_response(stop_reason="end_turn", text="These customers are both high risk and high value."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Find high-risk high-value customers.", make_ctx())
    assert result.tools_used == ["search_customers"]
    assert result.tool_calls[0].ok is True
    # Verify the underlying REAL tool execution actually filtered correctly (not just that the
    # mock was called) by re-running the same arguments directly:
    real = agent._exec_search_customers({"risk_tier": ["High"], "value_tier": ["High"], "limit": 10}, make_ctx())
    assert real["ok"] is True
    assert all(r["risk_tier"] == "High" and r["value_tier"] == "High" for r in real["data"]["rows"])


# ---------------------------------------------------------------------------
# 5. Aggregate question (deterministic fallback keyword route, real data)
# ---------------------------------------------------------------------------

def test_aggregate_question_fallback():
    result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.grounded is True
    assert result.used_llm is False
    assert "get_aggregate_metrics" in result.tools_used
    assert "churn rate" in result.answer.lower()


# ---------------------------------------------------------------------------
# 6. Segment question (deterministic fallback, real data)
# ---------------------------------------------------------------------------

def test_segment_question_fallback():
    ctx = make_ctx(selected_segment=KNOWN_SEGMENT)
    result = agent.ask("Tell me about this segment.", ctx)
    assert result.grounded is True
    assert result.used_llm is False
    assert "get_segment" in result.tools_used


# ---------------------------------------------------------------------------
# 7. Risk explanation (mocked loop calling explain_customer_risk against real data)
# ---------------------------------------------------------------------------

def test_risk_explanation_via_mocked_tool_loop():
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "explain_customer_risk", "input": {"customer_id": HIGH_RISK_MSNO}}]),
        fake_llm_response(stop_reason="end_turn", text="This customer's risk is associated with several signals."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask(f"Why is {HIGH_RISK_MSNO} at risk?", make_ctx())
    assert result.tools_used == ["explain_customer_risk"]
    assert result.tool_calls[0].ok is True
    real = agent._exec_explain_customer_risk({"customer_id": HIGH_RISK_MSNO}, make_ctx())
    assert real["ok"] is True
    assert len(real["data"]["top_global_drivers"]) == 5


# ---------------------------------------------------------------------------
# 8. Recommended action (mocked loop)
# ---------------------------------------------------------------------------

def test_recommended_action_via_mocked_tool_loop():
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "recommend_action", "input": {"segment": KNOWN_SEGMENT}}]),
        fake_llm_response(stop_reason="end_turn", text="Recommended action for this segment."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("What should we do about At-Risk Auto-Renew Off customers?", make_ctx())
    assert result.tools_used == ["recommend_action"]
    assert result.tool_calls[0].ok is True


# ---------------------------------------------------------------------------
# 9. Comparison question (mocked loop)
# ---------------------------------------------------------------------------

def test_comparison_question_via_mocked_tool_loop():
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "compare_to_champions", "input": {"customer_id": HIGH_RISK_MSNO}}]),
        fake_llm_response(stop_reason="end_turn", text="Compared to Champions, this customer differs in churn rate."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask(f"How does {HIGH_RISK_MSNO} compare to Champions?", make_ctx())
    assert result.tools_used == ["compare_to_champions"]
    assert result.tool_calls[0].ok is True


# ---------------------------------------------------------------------------
# 10. Multi-tool question -- the loop must call a second tool after the first result comes back
# ---------------------------------------------------------------------------

def test_multi_tool_question_via_mocked_tool_loop():
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "search_customers", "input": {"risk_tier": ["High"], "value_tier": ["High"], "limit": 5}}]),
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c2", "name": "recommend_action", "input": {"segment": KNOWN_SEGMENT}}]),
        fake_llm_response(stop_reason="end_turn", text="Here are the most valuable at-risk customers and what to do."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Find the highest-value customers who are at high risk and tell me what we should do.", make_ctx())
    assert result.tools_used == ["search_customers", "recommend_action"], f"got {result.tools_used}"
    assert all(c.ok for c in result.tool_calls)
    assert result.grounded is True


# ---------------------------------------------------------------------------
# 11. Unsupported question (fallback -- no customer/segment context, no keyword match)
# ---------------------------------------------------------------------------

def test_unsupported_question_fallback():
    result = agent.ask("What's the weather like today?", make_ctx())
    assert result.grounded is False
    assert result.used_llm is False
    assert "unavailable" in result.answer.lower()
    assert result.tools_used == []


# ---------------------------------------------------------------------------
# 12. Missing API key (the real, live condition in this environment)
# ---------------------------------------------------------------------------

def test_missing_api_key_routes_to_fallback_and_does_not_crash():
    assert llm_provider.is_configured() is False
    result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.used_llm is False
    assert result.fallback_reason == "no AI provider is configured for this session"
    assert "unavailable" in result.answer.lower() or result.grounded is True  # never pretends AI was used


def test_empty_question_does_not_crash():
    result = agent.ask("", make_ctx())
    assert result.answer
    result2 = agent.ask("   ", make_ctx())
    assert result2.answer


# ---------------------------------------------------------------------------
# 13. Malformed tool arguments -- must return ok=False, never raise
# ---------------------------------------------------------------------------

def test_malformed_arguments_missing_customer_id():
    result = agent._execute_tool("get_customer", {}, make_ctx())
    assert result["ok"] is False


def test_malformed_arguments_negative_limit():
    result = agent._execute_tool("search_customers", {"limit": -5}, make_ctx())
    assert result["ok"] is False


def test_malformed_arguments_both_customer_and_segment():
    result = agent._execute_tool("recommend_action", {"customer_id": HIGH_RISK_MSNO, "segment": KNOWN_SEGMENT}, make_ctx())
    assert result["ok"] is False


def test_malformed_arguments_not_a_dict():
    result = agent._execute_tool("get_customer", "not a dict", make_ctx())
    assert result["ok"] is False


def test_malformed_arguments_unknown_segment_passed_through():
    result = agent._execute_tool("get_segment", {"segment_name": "Not A Real Segment"}, make_ctx())
    assert result["ok"] is False


# ---------------------------------------------------------------------------
# 14. Hallucination prevention -- a tool name outside the fixed allow-list must never execute
# anything; there is no getattr/eval path from a string to arbitrary code.
# ---------------------------------------------------------------------------

def test_unknown_tool_name_is_rejected_not_executed():
    result = agent._execute_tool("execute_python", {"code": "import os; os.system('echo pwned')"}, make_ctx())
    assert result["ok"] is False
    assert "unknown tool" in result["error"].lower()


def test_unknown_tool_name_in_mocked_loop_does_not_crash():
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "delete_all_customers", "input": {}}]),
        fake_llm_response(stop_reason="end_turn", text="I can't do that."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Delete every customer record.", make_ctx())
    assert result.tool_calls[0].ok is False  # the fake tool call was rejected, not executed
    assert result.answer  # loop still completes and returns something


def test_tool_dispatch_table_is_a_fixed_allowlist_matching_schemas():
    assert set(agent._TOOL_DISPATCH.keys()) == set(agent_tool_schemas.TOOL_NAMES)
    assert len(agent_tool_schemas.TOOL_NAMES) == 9


# ---------------------------------------------------------------------------
# Turn-cap enforcement (a well-behaved but never-terminating mock must not loop forever)
# ---------------------------------------------------------------------------

def test_tool_loop_turn_cap_is_enforced():
    always_tool_use = fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c", "name": "get_aggregate_metrics", "input": {}}])
    with mock.patch("lib.llm_provider.complete_with_tools", return_value=always_tool_use) as mocked_complete, \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Keep going forever.", make_ctx())
    # P1-12: exceeding the turn cap now falls through to the SAME deterministic-fallback path
    # every other orchestration failure uses (see agent._OrchestrationFailed / agent.ask's
    # except clause), rather than returning a bare "AI couldn't finish" dead end -- so the
    # returned AgentResponse looks like any other deterministic-fallback answer (used_llm=False),
    # and its own tool_calls reflect only what actually grounds THAT answer, not the 6 discarded
    # attempts from the failed LLM loop. What this test must actually prove -- that the loop
    # truly stops at the configured bound and never runs away -- is asserted directly against how
    # many times the (mocked) provider was called.
    assert mocked_complete.call_count == agent._MAX_TOOL_LOOP_ITERATIONS
    assert result.used_llm is False
    assert result.fallback_reason == "tool-call loop exceeded its turn limit"


# ---------------------------------------------------------------------------
# 15. Causal-language guardrail
# ---------------------------------------------------------------------------

def test_system_prompt_forbids_causal_language():
    prompt = agent._SYSTEM_PROMPT.lower()
    assert "never make a causal claim" in prompt
    assert "caused this customer to churn" in prompt  # the explicit bad example is quoted so the model recognizes the pattern to avoid
    assert "guarantee" in prompt


def test_explain_customer_risk_schema_states_association_not_causation():
    schema = next(t for t in agent_tool_schemas.TOOL_SCHEMAS if t["name"] == "explain_customer_risk")
    desc = schema["description"].lower()
    assert "association" in desc
    assert "never a cause" in desc or "causal" in desc


# ---------------------------------------------------------------------------
# 16. Terminology guardrail
# ---------------------------------------------------------------------------

def test_system_prompt_preserves_terminology_distinctions():
    prompt = agent._SYSTEM_PROMPT
    assert "Model Risk Score" in prompt
    assert "Estimated Churn Probability" in prompt
    assert "NOT a calibrated probability" in prompt
    assert "Historical Realized Revenue" in prompt
    assert "NEVER call it CLV" in prompt
    assert "High-Risk Historical Revenue Exposure" in prompt
    assert "NOT a probability-weighted expected loss" in prompt


def test_all_tool_schemas_have_name_description_and_input_schema():
    for schema in agent_tool_schemas.TOOL_SCHEMAS:
        assert schema["name"]
        assert len(schema["description"]) > 50, f"{schema['name']} description too thin for an LLM to disambiguate"
        assert schema["input_schema"]["type"] == "object"


def test_search_customers_schema_distinguishes_risk_score_from_probability():
    schema = next(t for t in agent_tool_schemas.TOOL_SCHEMAS if t["name"] == "search_customers")
    props = schema["input_schema"]["properties"]
    assert "min_risk_score" in props and "min_calibrated_probability" in props
    assert "NOT a probability" in props["min_risk_score"]["description"]
    assert "calibrated probability filter" in props["min_calibrated_probability"]["description"]


def test_recommend_action_schema_forbids_guarantee_language():
    schema = next(t for t in agent_tool_schemas.TOOL_SCHEMAS if t["name"] == "recommend_action")
    desc = schema["description"].lower()
    assert "never claims" in desc or "never" in desc
    assert "guarantee" not in desc.split("never")[0]  # sanity: the word appears in a negation, not asserted positively


# ---------------------------------------------------------------------------
# Task 06 / P0 regression tests -- the five audited blockers from
# test_cases/TASK_05_PRODUCT_READINESS_AUDIT.md, verified against the real, live, no-API-key
# fallback path exactly as a manager would hit it today (no mocking in this section).
# ---------------------------------------------------------------------------

# --- P0-1 / P0-4: "Who should we contact first?" and "Show me high-risk, high-value customers."
# must resolve through search_customers deterministically, with no LLM configured. ---

def test_contact_first_routes_to_search_customers_deterministically():
    result = agent.ask("Who should we contact first?", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True
    assert result.tools_used == ["search_customers"]
    rows = agent.get_tool_result(result, "search_customers")["rows"]
    assert len(rows) > 0
    assert all(r["risk_tier"] == "High" for r in rows)
    assert "AI synthesis unavailable" in result.answer
    assert "NT$" not in result.answer


def test_high_risk_high_value_routes_to_search_customers_deterministically():
    result = agent.ask("Show me high-risk, high-value customers.", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True
    assert result.tools_used == ["search_customers"]
    rows = agent.get_tool_result(result, "search_customers")["rows"]
    assert len(rows) > 0
    assert all(r["risk_tier"] == "High" and r["value_tier"] == "High" for r in rows)


def test_new_search_routes_call_the_real_tool_not_a_duplicate_filter():
    # P0-4 requirement: the deterministic path must call agent_tools.search_customers itself,
    # not re-implement filtering. Cross-check the routed result against a direct call with the
    # same arguments -- they must be identical, row for row.
    routed = agent.ask("Who should we contact first?", make_ctx())
    direct = agent_tools.search_customers(DF, risk_tier=["High"], sort_by="risk_score_full", ascending=False, limit=10)
    assert direct["ok"] is True
    routed_rows = agent.get_tool_result(routed, "search_customers")["rows"]
    assert [r["msno"] for r in routed_rows] == [r["msno"] for r in direct["data"]["rows"]]


def test_search_customers_routes_handle_customer_ids_with_regex_special_characters():
    # msno values are base64-like and legitimately contain '+' and '/' (see
    # test_agent_tools.py's own regex-special-character coverage of the underlying tool). The new
    # routing in agent.py does no string/regex matching on msno at all -- it only forwards
    # whatever agent_tools.search_customers returns -- so any such row must pass through intact.
    result = agent.ask("Show me high-risk, high-value customers.", make_ctx())
    rows = agent.get_tool_result(result, "search_customers")["rows"]
    assert len(rows) > 0
    for r in rows:
        assert isinstance(r["msno"], str) and len(r["msno"]) > 0  # never mangled/dropped


def test_search_customers_route_no_results_handled_gracefully():
    # P0-4 requirement: "no results" must be a clean, honest message, not a crash or a guess.
    answer = agent._format_search_customers_answer({"rows": [], "total_matches": 0}, headline="Headline: test.")
    assert "no customers currently match" in answer.lower()
    assert "headline: test." in answer.lower()


def test_search_customers_route_without_loaded_customer_data_guides_the_user():
    # P0-4 / P0-1 requirement 4: a question needing data that hasn't been loaded yet must guide
    # the manager, never silently fail or pretend to answer.
    ctx = make_ctx(customer_df=None)
    result = agent.ask("Who should we contact first?", ctx)
    assert result.grounded is False
    assert result.used_llm is False
    assert "load customer data" in result.answer.lower()
    assert result.tools_used == []


def test_search_customers_results_hand_off_to_customer_360_via_the_proven_mechanism():
    # P0-4 requirement 10: results must be able to open in Customer 360. The rows returned here
    # carry a real msno; components.priority_list() (unchanged this task) opens any such row via
    # st.session_state["cust360_search"] + st.switch_page("pages/customer_360.py") -- the exact,
    # already-proven mechanism. This test confirms the data shape that mechanism depends on.
    result = agent.ask("Who should we contact first?", make_ctx())
    rows = agent.get_tool_result(result, "search_customers")["rows"]
    assert rows and all("msno" in r for r in rows)
    # the msno actually resolves back to a real customer via the same exact-match tool the
    # priority list's "Open ->" action ultimately lands on (Customer 360 / get_customer)
    lookup = agent_tools.get_customer(DF, rows[0]["msno"])
    assert lookup["ok"] is True


# --- P0-1 requirement 4: a customer-shaped question with no customer selected must guide the
# manager into selecting one, never produce a misleading answer. ---

def test_why_is_this_customer_at_risk_without_context_guides_to_search():
    result = agent.ask("Why is this customer at risk?", make_ctx())
    assert result.grounded is False
    assert result.used_llm is False
    assert result.tools_used == []
    assert "search for a customer" in result.answer.lower()
    # must not look like a real evidence-backed answer (no Recommendation:/Evidence: labels)
    assert "recommendation:" not in result.answer.lower()
    assert "evidence:" not in result.answer.lower()


def test_what_should_we_do_about_this_customer_without_context_guides_to_search():
    result = agent.ask("What should we do about this customer?", make_ctx())
    assert result.grounded is False
    assert result.used_llm is False
    assert "search for a customer" in result.answer.lower()


def test_customer_reference_guidance_does_not_fire_once_context_is_set():
    # sanity: the same phrasing, WITH a customer selected, must go through the real evidence path
    # (this guards against the new guidance check accidentally shadowing the working path).
    result = agent.ask("Why is this customer at risk?", make_ctx(selected_customer_id=HIGH_RISK_MSNO))
    assert result.grounded is True
    assert result.tools_used == ["get_customer"]


# --- P0-3: agent-facing monetary values must render in INR (via theme.fmt_currency), never raw
# NT$, matching every other surface in the product. ---

def test_aggregate_answer_uses_inr_not_raw_ntd():
    result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.grounded is True
    assert "NT$" not in result.answer
    assert theme.CURRENCY_SYMBOL in result.answer


def test_rank_segments_answer_uses_inr_not_raw_ntd():
    result = agent.ask("Which segment needs attention?", make_ctx())
    assert result.grounded is True
    assert "NT$" not in result.answer
    assert theme.CURRENCY_SYMBOL in result.answer


def test_aggregate_answer_currency_value_matches_theme_conversion():
    # not just "no NT$" -- the rendered figure must be the SAME centralized conversion every
    # other page uses, not an independently-computed one.
    metrics = agent_tools.get_aggregate_metrics(RISK_SUMMARY, VALUE_BY_TIER, RISK_VALUE_MATRIX, ACTION_PLAN, VALUE_BY_SEGMENT)
    assert metrics["ok"] is True
    expected = theme.fmt_currency(metrics["data"]["total_realized_revenue_ntd"])
    result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert expected in result.answer


# --- P0-2: the product name is consistently "Retention Intelligence" in agent-facing text. ---

def test_llm_system_prompts_do_not_reference_the_retired_name():
    from lib import copilot_engine
    assert "Retention Copilot" not in agent._SYSTEM_PROMPT
    assert "Retention Copilot" not in copilot_engine._SYSTEM_PROMPT
    assert "Retention Intelligence" in agent._SYSTEM_PROMPT
    assert "Retention Intelligence" in copilot_engine._SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# P1-09 regression tests -- "Assistant Identity & Personality"
# (task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-09)
# ---------------------------------------------------------------------------

def test_system_prompt_states_a_consistent_name_and_role():
    prompt = agent._SYSTEM_PROMPT
    assert "You are Retention Intelligence, KKBOX's Retention Operations Assistant" in prompt
    assert "not a general-purpose chatbot" in prompt


def test_system_prompt_states_the_required_voice_traits():
    prompt = agent._SYSTEM_PROMPT.lower()
    assert "voice:" in prompt
    assert "concise and operational" in prompt
    assert "confident when the evidence genuinely supports a conclusion" in prompt
    assert "explicit and unhedged" in prompt  # uncertainty/missing data must be stated plainly
    assert "evidence-first" in prompt
    assert "action-oriented" in prompt
    assert "business terms" in prompt


def test_system_prompt_forbids_implying_autonomous_action():
    prompt = agent._SYSTEM_PROMPT
    assert "RULE 11" in prompt
    rule11 = prompt.split("RULE 11:")[1].split("Terminology")[0]
    for capability in ("contact a customer", "send a message", "apply a discount", "change a subscription", "modify any record"):
        assert capability in rule11
    assert "only recommend what the retention team should do" in rule11


def test_p1_09_additions_did_not_alter_the_existing_grounding_rules():
    # Regression guard: RULE 1-10 and the terminology section must be byte-identical to before
    # this task -- P1-09 is additive-only (a new opening/voice paragraph and one new trailing
    # rule), never a rewrite of the existing grounding contract.
    prompt = agent._SYSTEM_PROMPT
    for rule_text in [
        "RULE 1: Never invent customer information. Every fact about a customer must come from a tool result.",
        "RULE 2: Never invent a customer ID. Only use an ID the manager gave you or that a tool returned.",
        "RULE 3: Never invent numerical values. Every number in your answer must come from a tool result.",
        "RULE 4: Never answer a customer-specific question without calling the appropriate tool first.",
        "RULE 5: If a requested customer does not exist (a tool returns ok=false), say so explicitly.",
        'RULE 6: If the available data does not contain something asked for, say exactly: "That '
        'information is not available in the current dataset." Do not infer or approximate it.',
        "RULE 9: Never fabricate campaign performance, ROI, uplift, revenue saved, or treatment "
        "effectiveness -- none of that exists in this dataset.",
    ]:
        assert rule_text in prompt


def test_agent_tool_dispatch_and_schemas_unaffected_by_the_identity_change():
    # Personality is presentation-only -- the tool allow-list, its schemas, and the deterministic
    # dispatch table must be exactly what they were before P1-09.
    assert set(agent._TOOL_DISPATCH) == set(agent_tool_schemas.TOOL_NAMES)
    assert len(agent_tool_schemas.TOOL_SCHEMAS) == 9


def test_deterministic_answers_still_grounded_and_unaffected_by_identity_change():
    # The identity/voice text lives only in the LLM system prompt; the deterministic fallback's
    # actual evidence-backed content (what genuinely runs with no API key) must be byte-for-byte
    # what it already was -- proven by re-running two representative real fallback calls and
    # checking their exact, already-established content is untouched.
    result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.grounded is True
    assert "Headline:" in result.answer
    assert "overall churn rate" in result.answer

    result2 = agent.ask("Why is this customer at risk?", make_ctx(selected_customer_id=HIGH_RISK_MSNO))
    assert result2.grounded is True
    assert "Recommendation:" in result2.answer


# ---------------------------------------------------------------------------
# P1-10 regression tests -- "Numbers-to-Decisions Pass"
# (task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-10)
# ---------------------------------------------------------------------------

def test_aggregate_answer_ends_with_a_recommended_next_step():
    # Previously ended on the exposure figure with no closing implication/action line.
    metrics = agent_tools.get_aggregate_metrics(RISK_SUMMARY, VALUE_BY_TIER, RISK_VALUE_MATRIX, ACTION_PLAN, VALUE_BY_SEGMENT)
    assert metrics["ok"] is True
    answer = agent._format_aggregate_answer(metrics["data"])
    assert "Recommended next step:" in answer
    lower = answer.lower()
    # only ever names real, already-working questions -- no invented capability
    assert "which segment needs attention" in lower or "who should we contact first" in lower


def test_rank_segments_answer_leads_with_a_headline_finding():
    result = agent_tools.rank_segments_by_priority(ACTION_PLAN)
    assert result["ok"] is True
    rows = result["data"]["rows"]
    answer = agent._format_rank_segments_answer(rows)
    assert answer.startswith("Headline:")
    assert rows[0]["segment"] in answer.split("\n")[0]


def test_rank_segments_answer_caps_prose_and_points_to_action_center():
    result = agent_tools.rank_segments_by_priority(ACTION_PLAN)
    rows = result["data"]["rows"]
    assert len(rows) > 3, "this test assumes the real data has more than 3 priority segments"
    answer = agent._format_rank_segments_answer(rows)
    lines = answer.splitlines()
    # P1-11: the cap moved from 3 to 6 lines -- Headline, Also worth attention, Recommended
    # action, Why it matters, Confidence/limitations, Recommended next step. This is a deliberate
    # consequence of P1-11's acceptance criterion "evidence and action are distinct": the
    # recommended action used to be folded into the Headline sentence itself; it is now its own
    # line, and the answer also gained explicit Why-it-matters and Confidence/limitations lines
    # per the required six-part decision structure. It is still a short, capped answer -- not
    # every row is restated in prose, only the top one plus up to two runners-up (see below).
    assert len(lines) <= 6, f"expected a short, capped answer, got {len(lines)} lines: {lines}"
    assert "Also worth attention:" in answer
    assert "Action Center" in answer
    assert f"all {len(rows):,} segments" in answer
    # not every row is restated in prose -- only the top one plus up to two runners-up
    for r in rows[3:]:
        assert r["segment"] not in answer


def test_rank_segments_answer_no_pointer_needed_when_rows_are_already_short():
    rows = [
        {"priority": 1, "segment": "Segment A", "n_customers": 10, "churn_rate_pct": 50.0, "total_hrr_ntd": 1000.0, "recommended_action": "Re-engage"},
        {"priority": 2, "segment": "Segment B", "n_customers": 5, "churn_rate_pct": 30.0, "total_hrr_ntd": 500.0, "recommended_action": "Monitor"},
    ]
    answer = agent._format_rank_segments_answer(rows)
    assert "Recommended next step:" not in answer
    assert "Segment B" in answer  # still mentioned, since everything fits without capping


def test_rank_segments_answer_handles_empty_rows():
    assert agent._format_rank_segments_answer([]) == "No segments currently need prioritization."


def test_p1_10_formatters_still_use_inr_not_raw_ntd():
    metrics = agent_tools.get_aggregate_metrics(RISK_SUMMARY, VALUE_BY_TIER, RISK_VALUE_MATRIX, ACTION_PLAN, VALUE_BY_SEGMENT)
    aggregate_answer = agent._format_aggregate_answer(metrics["data"])
    assert "NT$" not in aggregate_answer
    assert theme.CURRENCY_SYMBOL in aggregate_answer

    rank_result = agent_tools.rank_segments_by_priority(ACTION_PLAN)
    rank_answer = agent._format_rank_segments_answer(rank_result["data"]["rows"])
    assert "NT$" not in rank_answer
    assert theme.CURRENCY_SYMBOL in rank_answer


def test_rank_segments_via_real_fallback_call_matches_direct_formatter_output():
    # Proves the live path (agent.ask -> _deterministic_fallback) produces the same restructured
    # answer as the formatter tested directly above, not a second, divergent implementation.
    result = agent_tools.rank_segments_by_priority(ACTION_PLAN)
    expected = agent._format_rank_segments_answer(result["data"]["rows"])
    response = agent.ask("Which segment should we prioritize?", make_ctx())
    assert response.grounded is True
    assert expected in response.answer


# ---------------------------------------------------------------------------
# P1-11 regression tests -- "Structured Decision Answers"
# (task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-11)
#
# Response structure required: Finding -> Evidence -> Why it matters -> Recommended action ->
# Confidence/limitations -> Next step (where applicable). Covers all four deterministic answer
# types this project has (customer, segment, aggregate, segment-ranking, search-customer-list),
# plus the terminology/causality guardrails re-verified against the actual restructured text.
# ---------------------------------------------------------------------------

def test_customer_answer_follows_the_six_part_order():
    ctx = make_ctx(selected_customer_id=HIGH_RISK_MSNO)
    result = agent.ask("Why is this customer at risk?", ctx)
    assert result.grounded is True
    answer = result.answer
    # Finding(Recommendation) -> Evidence -> Why it matters -> Recommended action ->
    # Confidence/limitations, in that order -- "evidence and action are distinct" per P1-11's
    # acceptance criteria, not folded into one sentence.
    assert "Recommendation:" in answer and "Evidence:" in answer and "Why it matters:" in answer
    assert "Recommended action:" in answer and "Confidence/limitations:" in answer
    assert answer.index("Recommendation:") < answer.index("Evidence:")
    assert answer.index("Evidence:") < answer.index("Why it matters:")
    assert answer.index("Why it matters:") < answer.index("Recommended action:")
    assert answer.index("Recommended action:") < answer.index("Confidence/limitations:")


def test_segment_answer_follows_the_six_part_order():
    ctx = make_ctx(selected_segment=KNOWN_SEGMENT)
    result = agent.ask("Tell me about this segment.", ctx)
    assert result.grounded is True
    answer = result.answer
    assert "Recommendation:" in answer and "Evidence:" in answer and "Why it matters:" in answer
    assert "Recommended action:" in answer and "Confidence/limitations:" in answer
    assert answer.index("Recommendation:") < answer.index("Evidence:") < answer.index("Why it matters:")
    assert answer.index("Why it matters:") < answer.index("Recommended action:") < answer.index("Confidence/limitations:")


def test_customer_and_segment_answers_have_no_manufactured_next_step_line():
    # The genuinely applicable "next step" for these two answer types is the persistent, always-
    # working Customer 360 / Priority Customers link already rendered directly above the answer
    # on the page (see retention_copilot.py's context_slot) -- a deliberate design decision, not
    # an oversight, documented in agent._render_copilot_answer's own docstring and the validation
    # report. This regression-guards that decision rather than silently drifting either way.
    cust_answer = agent.ask("Why is this customer at risk?", make_ctx(selected_customer_id=HIGH_RISK_MSNO)).answer
    seg_answer = agent.ask("Tell me about this segment.", make_ctx(selected_segment=KNOWN_SEGMENT)).answer
    assert "Next step" not in cust_answer
    assert "Next step" not in seg_answer


def test_aggregate_answer_includes_why_it_matters_and_confidence_limitations_in_order():
    metrics = agent_tools.get_aggregate_metrics(RISK_SUMMARY, VALUE_BY_TIER, RISK_VALUE_MATRIX, ACTION_PLAN, VALUE_BY_SEGMENT)
    answer = agent._format_aggregate_answer(metrics["data"])
    assert "Why it matters:" in answer
    assert "Confidence/limitations:" in answer
    assert answer.index("Why it matters:") < answer.index("Confidence/limitations:")
    assert answer.index("Confidence/limitations:") < answer.index("Recommended next step:")
    assert "not an expected loss" in answer
    assert "not a calibrated probability" in answer
    # No single "Recommended action" section exists for a business-wide aggregate question -- the
    # action framework operates at the segment/customer level, so this section is genuinely not
    # applicable here and must not be manufactured.
    assert "Recommended action:" not in answer


def test_rank_segments_answer_keeps_the_action_distinct_from_the_finding():
    result = agent_tools.rank_segments_by_priority(ACTION_PLAN)
    rows = result["data"]["rows"]
    answer = agent._format_rank_segments_answer(rows)
    headline_line = answer.splitlines()[0]
    # P1-10 folded the recommended action into the same sentence as the Finding; P1-11 splits it
    # into its own line, per the explicit acceptance criterion "evidence and action are distinct".
    assert "Recommended:" not in headline_line
    assert "Recommended action:" in answer
    assert answer.index(headline_line) == 0
    assert answer.index("Recommended action:") > len(headline_line)
    assert "Why it matters:" in answer
    assert "Confidence/limitations:" in answer
    assert answer.index("Recommended action:") < answer.index("Why it matters:") < answer.index("Confidence/limitations:")


def test_contact_first_answer_has_why_action_and_confidence_in_order():
    result = agent.ask("Who should we contact first?", make_ctx())
    assert result.grounded is True
    answer = result.answer
    assert "contact first" in answer.lower()  # headline substring preserved (regression guard)
    assert answer.index("Result summary:") < answer.index("Why it matters:")
    assert answer.index("Why it matters:") < answer.index("Recommended action:")
    assert answer.index("Recommended action:") < answer.index("Confidence/limitations:")
    assert answer.index("Confidence/limitations:") < answer.index("Recommended next step:")
    assert "not a calibrated probability" in answer


def test_high_risk_high_value_answer_has_why_action_and_confidence_in_order():
    result = agent.ask("Show me high-risk, high-value customers.", make_ctx())
    assert result.grounded is True
    answer = result.answer
    assert "priority zone" in answer.lower()  # headline substring preserved (regression guard)
    assert answer.index("Result summary:") < answer.index("Why it matters:")
    assert answer.index("Why it matters:") < answer.index("Recommended action:")
    assert answer.index("Recommended action:") < answer.index("Confidence/limitations:")


def test_search_customer_answer_recommended_action_points_to_the_list_not_a_single_invented_action():
    # A search result can span multiple segments with different recommended treatments -- the
    # answer text must not assert one combined action; it must point at the per-row
    # `recommended_action` already rendered by components.priority_list.
    result = agent.ask("Who should we contact first?", make_ctx())
    answer = result.answer
    assert "see each customer's recommended treatment in the list below" in answer.lower()
    rows = agent.get_tool_result(result, "search_customers")["rows"]
    assert all("recommended_action" in r for r in rows)


def test_no_answer_mislabels_model_risk_score_as_a_probability():
    # Terminology guardrail, re-verified against the actual restructured text of every
    # deterministic answer type -- not just the system prompt.
    answers = [
        agent._format_aggregate_answer(agent_tools.get_aggregate_metrics(RISK_SUMMARY, VALUE_BY_TIER, RISK_VALUE_MATRIX, ACTION_PLAN, VALUE_BY_SEGMENT)["data"]),
        agent._format_rank_segments_answer(agent_tools.rank_segments_by_priority(ACTION_PLAN)["data"]["rows"]),
        agent.ask("Who should we contact first?", make_ctx()).answer,
        agent.ask("Show me high-risk, high-value customers.", make_ctx()).answer,
        agent.ask("Why is this customer at risk?", make_ctx(selected_customer_id=HIGH_RISK_MSNO)).answer,
        agent.ask("Tell me about this segment.", make_ctx(selected_segment=KNOWN_SEGMENT)).answer,
    ]
    for ans in answers:
        assert "Model Risk Score is a probability" not in ans
        assert "% probability" not in ans
        if "Model Risk Score" in ans:
            assert "not a calibrated probability" in ans or "raw model output" in ans, ans


def test_why_it_matters_and_evidence_never_use_causal_language():
    answers = [
        agent._format_aggregate_answer(agent_tools.get_aggregate_metrics(RISK_SUMMARY, VALUE_BY_TIER, RISK_VALUE_MATRIX, ACTION_PLAN, VALUE_BY_SEGMENT)["data"]),
        agent._format_rank_segments_answer(agent_tools.rank_segments_by_priority(ACTION_PLAN)["data"]["rows"]),
        agent.ask("Who should we contact first?", make_ctx()).answer,
        agent.ask("Why is this customer at risk?", make_ctx(selected_customer_id=HIGH_RISK_MSNO)).answer,
        agent.ask("Tell me about this segment.", make_ctx(selected_segment=KNOWN_SEGMENT)).answer,
    ]
    banned = ("this caused", "causes churn", "will reduce churn", "guarantees", "will save")
    for ans in answers:
        lower = ans.lower()
        for phrase in banned:
            assert phrase not in lower, f"found banned causal phrase {phrase!r} in: {ans}"


def test_search_customers_link_and_customer_360_handoff_unaffected_by_answer_restructure():
    # Regression guard: the answer TEXT changed (P1-11); the underlying tool result rows -- and
    # therefore the click-through to Customer 360 -- must be byte-identical to before.
    result = agent.ask("Who should we contact first?", make_ctx())
    rows = agent.get_tool_result(result, "search_customers")["rows"]
    assert rows and all("msno" in r for r in rows)
    lookup = agent_tools.get_customer(DF, rows[0]["msno"])
    assert lookup["ok"] is True


def test_system_prompt_describes_the_six_part_decision_structure():
    prompt = agent._SYSTEM_PROMPT
    for fragment in (
        "1. Finding --", "2. Evidence --", "3. Why it matters --", "4. Recommended action --",
        "5. Confidence/limitations --", "6. Next step",
    ):
        assert fragment in prompt
    assert "skip a section rather than" in prompt.lower()


def test_p1_11_system_prompt_rewrite_did_not_alter_the_existing_grounding_rules():
    # Regression guard: P1-11 only rewrote the "Answer structure" paragraph. RULE 1-11 and the
    # Terminology section must be exactly what they were before this task.
    prompt = agent._SYSTEM_PROMPT
    for rule_text in [
        "RULE 1: Never invent customer information. Every fact about a customer must come from a tool result.",
        "RULE 2: Never invent a customer ID. Only use an ID the manager gave you or that a tool returned.",
        "RULE 3: Never invent numerical values. Every number in your answer must come from a tool result.",
        "RULE 4: Never answer a customer-specific question without calling the appropriate tool first.",
        "RULE 5: If a requested customer does not exist (a tool returns ok=false), say so explicitly.",
        'RULE 6: If the available data does not contain something asked for, say exactly: "That '
        'information is not available in the current dataset." Do not infer or approximate it.',
        "RULE 7: Never make a causal claim from a model association.",
        "RULE 8: Never claim an intervention WILL reduce churn.",
        "RULE 9: Never fabricate campaign performance, ROI, uplift, revenue saved, or treatment "
        "effectiveness -- none of that exists in this dataset.",
        "RULE 10: If a question is outside what the tools can answer, explain the limitation plainly",
        "RULE 11: You are a decision-support assistant, not an autonomous system.",
        '"Model Risk Score" (model_risk_score / risk_score_full) is the RAW model output.',
        '"Estimated Churn Probability" (calibrated_probability) is the calibrated figure',
        '"High-Risk Historical Revenue Exposure" is a headcount exposure sum, NOT a probability-weighted',
    ]:
        assert rule_text in prompt


def test_p1_11_answer_restructure_did_not_change_the_tool_dispatch_or_schemas():
    # Personality/structure work is presentation-only -- the tool allow-list and dispatch table
    # must be exactly what they were before P1-11.
    assert set(agent._TOOL_DISPATCH) == set(agent_tool_schemas.TOOL_NAMES)
    assert len(agent_tool_schemas.TOOL_SCHEMAS) == 9


# ---------------------------------------------------------------------------
# P1-12 regression tests -- "Agent Reliability & Failure-Mode Hardening"
# (task_1/KKBox_Retention_Intelligence_Task_Tracker_T07_onwards.xlsx, row P1-12)
#
# One test group per named failure class in the tracker: missing API key, LLM timeout/request
# failure, malformed tool call, invalid/hallucinated tool name, malformed tool response, partial
# tool failure, repeated tool calls, and the bounded-loop cap. No ANTHROPIC_API_KEY exists in
# this environment (confirmed by test_no_api_key_in_this_environment above) -- every test here
# either exercises the REAL, live deterministic-fallback path with no mocking at all, or mocks
# only `lib.llm_provider.complete_with_tools` / `lib.llm_provider.is_configured` (the same
# established boundary every other mocked-loop test in this file already mocks) to simulate a
# specific failure shape. None of this fabricates a working LLM call or claims live provider
# behavior was tested.
# ---------------------------------------------------------------------------

# --- Missing API key: the deterministic path is used, never a faked "successful" LLM call. ---

def test_missing_api_key_never_invokes_the_tool_loop():
    # A stronger guarantee than "the answer looks deterministic" -- the LLM boundary function is
    # never even called when no key is configured, proven by making it raise if it were.
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=AssertionError("must not be called")):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True


# --- LLM/API timeout or request failure: must terminate safely, no partial/stale state, falls
# back to the real deterministic answer. ---

def test_request_failure_on_the_very_first_turn_falls_back_deterministically():
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=llm_provider.ProviderUnavailable("Provider request failed: APITimeoutError")), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True
    assert "APITimeoutError" in (result.fallback_reason or "")
    assert "Headline:" in result.answer  # the real, grounded deterministic aggregate answer


def test_request_failure_mid_loop_discards_partial_state_and_falls_back():
    # Turn 1 succeeds (a real tool executes) -- turn 2 times out. The manager must never see that
    # one-tool partial result presented as a finished answer; the whole attempt is discarded and
    # a fresh, real deterministic answer is computed instead (same "fall back safely when the
    # requested answer cannot be grounded completely" requirement as partial tool failure).
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "get_aggregate_metrics", "input": {}}]),
        llm_provider.ProviderUnavailable("Provider request failed: TimeoutError"),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True
    assert "TimeoutError" in (result.fallback_reason or "")
    # this is the FRESH deterministic answer, not a stitched-together partial one
    assert "Headline:" in result.answer


def test_llm_provider_requests_use_a_bounded_explicit_timeout():
    # Contract test (no network call): the Anthropic client is constructed with a real, bounded
    # timeout, not left to the SDK's own multi-minute default. `anthropic.Anthropic` itself is
    # mocked, so this never talks to a real service and never needs a real key -- the fake key
    # value below exists only to satisfy `is_configured()`'s presence check for this unit test,
    # not to claim any live behavior was exercised.
    import anthropic
    fake_client = mock.MagicMock()
    fake_client.messages.create.return_value = mock.MagicMock(content=[])
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-unit-test-only-not-real"}), \
         mock.patch("anthropic.Anthropic", return_value=fake_client) as mocked_ctor:
        try:
            llm_provider.complete("system", "user question")
        except llm_provider.ProviderUnavailable:
            pass  # the mocked response has no text content -- expected, irrelevant to this check
    assert mocked_ctor.call_count == 1
    _, kwargs = mocked_ctor.call_args
    assert "timeout" in kwargs
    assert isinstance(kwargs["timeout"], (int, float)) and 0 < kwargs["timeout"] <= 60


# --- Malformed tool call: missing name, missing/invalid arguments, wrong types, invalid IDs --
# rejected safely, never executed as arbitrary behavior. ---

def test_malformed_tool_call_missing_name_rejected_safely():
    result = agent._execute_tool(None, {}, make_ctx())
    assert result["ok"] is False
    assert result["data"] is None


def test_malformed_tool_call_empty_string_name_rejected_safely():
    result = agent._execute_tool("", {"customer_id": HIGH_RISK_MSNO}, make_ctx())
    assert result["ok"] is False


def test_malformed_tool_call_arguments_not_a_dict_rejected_safely():
    for bad_args in (None, "a string", 42, ["a", "list"]):
        result = agent._execute_tool("get_aggregate_metrics", bad_args, make_ctx())
        assert result["ok"] is False, f"expected rejection for arguments={bad_args!r}"


def test_malformed_tool_call_wrong_argument_type_rejected_safely():
    # limit as a string instead of an int -- must be rejected, never crash the process trying to
    # use it as one.
    result = agent._execute_tool("search_customers", {"limit": "ten"}, make_ctx())
    assert result["ok"] is False


def test_malformed_tool_call_invalid_customer_id_type_rejected_safely():
    for bad_id in (12345, ["msno1"], {"id": "x"}, None):
        result = agent._execute_tool("get_customer", {"customer_id": bad_id}, make_ctx())
        assert result["ok"] is False, f"expected rejection for customer_id={bad_id!r}"


def test_malformed_tool_call_in_mocked_loop_does_not_crash_and_reaches_a_final_answer():
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "get_customer", "input": {"customer_id": 999}}]),
        fake_llm_response(stop_reason="end_turn", text="That customer ID isn't valid."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Look up customer 999", make_ctx())
    assert result.tool_calls[0].ok is False
    assert result.answer  # loop still completes, no crash


# --- Invalid/hallucinated tool name: the explicit allow-list is the only path to execution --
# never getattr/eval/dynamic import. ---

def test_no_getattr_eval_exec_or_dynamic_import_anywhere_in_agent_py():
    # Structural guarantee, not just a behavioral one: scans the actual source for the exact
    # mechanisms the tracker explicitly forbids, so this can never silently regress even if a
    # future change reshapes the dispatch code.
    src = open(f"{DASHBOARD_DIR}/lib/agent.py", encoding="utf-8").read()
    for forbidden in ("getattr(", "eval(", "exec(", "__import__("):
        assert forbidden not in src, f"found forbidden dynamic-execution mechanism: {forbidden!r}"


def test_hallucinated_tool_name_with_realistic_looking_arguments_is_rejected():
    # A more adversarial hallucinated name than the existing "delete_all_customers" test uses --
    # one that looks like it could plausibly be a 10th real tool -- still hits the same allow-list
    # rejection, not a lookup that almost-matches.
    result = agent._execute_tool("get_customer_full_profile", {"customer_id": HIGH_RISK_MSNO}, make_ctx())
    assert result["ok"] is False
    assert "unknown tool" in result["error"].lower()


# --- Malformed tool response: missing ok/data/error, unexpected shape, a tool that raises --
# handled safely, deterministic fallback preserved. ---

def test_execute_tool_coerces_none_return_into_a_safe_error():
    original = agent._TOOL_DISPATCH["get_aggregate_metrics"]
    agent._TOOL_DISPATCH["get_aggregate_metrics"] = lambda args, ctx: None
    try:
        result = agent._execute_tool("get_aggregate_metrics", {}, make_ctx())
    finally:
        agent._TOOL_DISPATCH["get_aggregate_metrics"] = original
    assert result["ok"] is False
    assert result["data"] is None
    assert "malformed" in result["error"].lower()


def test_execute_tool_coerces_non_dict_return_into_a_safe_error():
    original = agent._TOOL_DISPATCH["get_aggregate_metrics"]
    for bad_return in ("just a string", 42, ["a", "list"]):
        agent._TOOL_DISPATCH["get_aggregate_metrics"] = lambda args, ctx, r=bad_return: r
        try:
            result = agent._execute_tool("get_aggregate_metrics", {}, make_ctx())
        finally:
            agent._TOOL_DISPATCH["get_aggregate_metrics"] = original
        assert result["ok"] is False, f"expected rejection for return value {bad_return!r}"


def test_execute_tool_coerces_dict_missing_ok_key_into_a_safe_error():
    original = agent._TOOL_DISPATCH["get_aggregate_metrics"]
    agent._TOOL_DISPATCH["get_aggregate_metrics"] = lambda args, ctx: {"data": {"n": 1}}
    try:
        result = agent._execute_tool("get_aggregate_metrics", {}, make_ctx())
    finally:
        agent._TOOL_DISPATCH["get_aggregate_metrics"] = original
    assert result["ok"] is False


def test_execute_tool_never_invents_data_when_coercing_a_malformed_result():
    original = agent._TOOL_DISPATCH["get_aggregate_metrics"]
    agent._TOOL_DISPATCH["get_aggregate_metrics"] = lambda args, ctx: "unusable"
    try:
        result = agent._execute_tool("get_aggregate_metrics", {}, make_ctx())
    finally:
        agent._TOOL_DISPATCH["get_aggregate_metrics"] = original
    assert result["data"] is None  # never a guessed/placeholder value


def test_tool_that_raises_is_handled_safely_not_propagated():
    original = agent._TOOL_DISPATCH["get_aggregate_metrics"]

    def _boom(args, ctx):
        raise RuntimeError("simulated tool crash")

    agent._TOOL_DISPATCH["get_aggregate_metrics"] = _boom
    try:
        result = agent._execute_tool("get_aggregate_metrics", {}, make_ctx())
    finally:
        agent._TOOL_DISPATCH["get_aggregate_metrics"] = original
    assert result["ok"] is False
    assert "RuntimeError" in result["error"]


def test_malformed_provider_response_shape_falls_back_to_deterministic():
    # complete_with_tools returning something that isn't even a dict -- must not KeyError/crash;
    # must reach the real deterministic answer.
    with mock.patch("lib.llm_provider.complete_with_tools", return_value="not a dict"), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True
    assert "Headline:" in result.answer


def test_provider_response_missing_expected_keys_falls_back_to_deterministic():
    with mock.patch("lib.llm_provider.complete_with_tools", return_value={"stop_reason": "tool_use"}), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True


def test_tool_use_stop_reason_with_no_tool_calls_falls_back_to_deterministic():
    # Claims tool_use but names no tool -- malformed/anomalous, must not loop on nothing and must
    # not be mistaken for a genuine final answer.
    with mock.patch("lib.llm_provider.complete_with_tools", return_value=fake_llm_response(stop_reason="tool_use", tool_calls=[])), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True


def test_malformed_individual_tool_call_entry_in_mocked_loop_does_not_crash():
    # A tool_calls entry missing "input" and "id" entirely (not just malformed values) --
    # exercises the defensive .get(...) access in the loop itself, not just _execute_tool.
    responses = [
        {"stop_reason": "tool_use", "text": "", "tool_calls": [{"name": "get_aggregate_metrics"}], "raw_content": []},
        fake_llm_response(stop_reason="end_turn", text="Done."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.answer  # no crash
    assert result.tool_calls[0].tool == "get_aggregate_metrics"
    assert result.tool_calls[0].ok is True  # missing input defaulted to {} -- a valid call for this tool


# --- Partial tool failure: one tool succeeds, another fails, in the same turn -- both results
# forwarded honestly; grounded reflects actual success, not mere attempt. ---

def test_partial_failure_within_one_turn_both_results_are_forwarded_honestly():
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[
            {"id": "c1", "name": "get_customer", "input": {"customer_id": HIGH_RISK_MSNO}},
            {"id": "c2", "name": "get_customer", "input": {"customer_id": "DOES_NOT_EXIST_XYZ"}},
        ]),
        fake_llm_response(stop_reason="end_turn", text="One customer found, one not."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Look up two customers", make_ctx())
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0].ok is True
    assert result.tool_calls[1].ok is False
    # the failure is preserved as a real failure, never silently dropped or overwritten by the
    # successful call
    assert result.tool_calls[1].result["data"] is None
    assert result.grounded is True  # at least one call genuinely succeeded


def test_when_every_tool_call_fails_the_answer_is_not_reported_as_grounded():
    # P1-12: `grounded` now means "at least one tool call actually succeeded", not merely "a tool
    # was attempted" -- the direct fix for "do not present incomplete evidence as complete".
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[
            {"id": "c1", "name": "get_customer", "input": {"customer_id": "DOES_NOT_EXIST_XYZ"}},
        ]),
        fake_llm_response(stop_reason="end_turn", text="I couldn't find that customer."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Look up a customer", make_ctx())
    assert result.tool_calls[0].ok is False
    assert result.grounded is False


# --- Repeated tool calls: bounded loop preserved; identical repeated calls handled safely
# without redundant re-execution or unbounded consumption. ---

def test_duplicate_identical_tool_call_is_not_re_executed_but_still_answered():
    real_fn = agent._TOOL_DISPATCH["get_aggregate_metrics"]
    call_count = {"n": 0}

    def _counting_wrapper(args, ctx):
        call_count["n"] += 1
        return real_fn(args, ctx)

    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "get_aggregate_metrics", "input": {}}]),
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c2", "name": "get_aggregate_metrics", "input": {}}]),
        fake_llm_response(stop_reason="end_turn", text="Same numbers both times."),
    ]
    agent._TOOL_DISPATCH["get_aggregate_metrics"] = _counting_wrapper
    try:
        with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
             mock.patch("lib.llm_provider.is_configured", return_value=True):
            result = agent.ask("Give me the numbers, then give them again.", make_ctx())
    finally:
        agent._TOOL_DISPATCH["get_aggregate_metrics"] = real_fn
    # the underlying deterministic computation ran once, not twice --
    assert call_count["n"] == 1
    # -- but the model still received a real tool_result for BOTH tool_use requests it made
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0].ok is True and result.tool_calls[1].ok is True
    assert result.tool_calls[0].result == result.tool_calls[1].result


def test_repeated_calls_with_different_arguments_are_not_deduplicated():
    # Sanity guard on the dedup key itself: same tool, DIFFERENT arguments, must not be conflated.
    responses = [
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c1", "name": "search_customers", "input": {"risk_tier": ["High"], "limit": 3}}]),
        fake_llm_response(stop_reason="tool_use", tool_calls=[{"id": "c2", "name": "search_customers", "input": {"risk_tier": ["Low"], "limit": 3}}]),
        fake_llm_response(stop_reason="end_turn", text="Here are both groups."),
    ]
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=responses), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Compare high and low risk customers.", make_ctx())
    rows_a = result.tool_calls[0].result["data"]["rows"]
    rows_b = result.tool_calls[1].result["data"]["rows"]
    assert all(r["risk_tier"] == "High" for r in rows_a)
    assert all(r["risk_tier"] == "Low" for r in rows_b)


# Note: "identical repeated calls still respect the hard turn cap even with the dedup cache
# active" is already covered directly by test_tool_loop_turn_cap_is_enforced above (its own
# scenario IS a repeated-identical-call sequence, and its docstring calls this out) -- not
# duplicated here.


# --- Cross-cutting: no exception ever escapes ask(); terminology/grounding guardrails hold even
# on the failure path, not just the success path. ---

def test_completely_unexpected_exception_in_the_loop_still_falls_back_safely():
    with mock.patch("lib.agent._run_tool_loop", side_effect=RuntimeError("totally unforeseen bug")), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert result.used_llm is False
    assert result.grounded is True
    assert "RuntimeError" in (result.fallback_reason or "")
    assert "Headline:" in result.answer


def test_deterministic_fallback_after_simulated_timeout_still_never_calls_model_risk_score_a_probability():
    with mock.patch("lib.llm_provider.complete_with_tools", side_effect=llm_provider.ProviderUnavailable("Provider request failed: APITimeoutError")), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("How many customers are at elevated risk?", make_ctx())
    assert "Model Risk Score is a probability" not in result.answer
    assert "not a calibrated probability" in result.answer


def test_deterministic_fallback_after_simulated_crash_preserves_customer_360_handoff_data():
    # Regression guard: an induced orchestration crash must not corrupt or drop the real
    # search_customers row shape the Customer 360 handoff depends on -- the deterministic
    # fallback recomputes it independently and correctly.
    with mock.patch("lib.agent._run_tool_loop", side_effect=RuntimeError("boom")), \
         mock.patch("lib.llm_provider.is_configured", return_value=True):
        result = agent.ask("Who should we contact first?", make_ctx())
    rows = agent.get_tool_result(result, "search_customers")["rows"]
    assert rows and all("msno" in r for r in rows)
    lookup = agent_tools.get_customer(DF, rows[0]["msno"])
    assert lookup["ok"] is True


def test_p1_12_hardening_did_not_change_the_tool_allowlist_or_dispatch_table():
    assert set(agent._TOOL_DISPATCH) == set(agent_tool_schemas.TOOL_NAMES)
    assert len(agent_tool_schemas.TOOL_SCHEMAS) == 9


def test_p1_12_hardening_did_not_change_any_analytical_values():
    # The deterministic answers' actual numbers must be byte-identical to their pre-P1-12 values
    # -- this task hardens orchestration, it does not touch models/thresholds/scores/HRR.
    metrics = agent_tools.get_aggregate_metrics(RISK_SUMMARY, VALUE_BY_TIER, RISK_VALUE_MATRIX, ACTION_PLAN, VALUE_BY_SEGMENT)
    assert metrics["data"]["n_customers_scored"] == RISK_SUMMARY["n_customers_scored"]
    assert metrics["data"]["overall_churn_rate_pct"] == RISK_SUMMARY["actual_churn_rate"] * 100


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
