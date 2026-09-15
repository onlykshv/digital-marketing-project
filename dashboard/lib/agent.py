"""The AI agent orchestration layer: turns a manager's free-text question into zero or more
deterministic tool calls (`agent_tools.py`) and a grounded answer.

This module is additive, not a replacement. `copilot_engine.py` (the existing, preset-question-
driven Retention Copilot) is untouched and still fully functional on its own -- this module adds
a second, more general capability (arbitrary free-text questions, multiple tool calls per
question) on top of the SAME deterministic tools and the SAME grounding discipline, per:

    CURRENT COPILOT
           |
    Deterministic evidence engine (agent_tools.py, copilot_data.py, data.py -- unchanged)
           |
    NEW AGENT ORCHESTRATOR (this file)
           |
    Optional LLM synthesis (llm_provider.py's complete_with_tools)

Architecture:

    question -> ask(question, ctx)
             -> if no LLM configured: deterministic fallback (routes to the same tools directly)
             -> if LLM configured: a bounded tool-call loop --
                    LLM picks a tool + arguments (from the fixed schema list only -- it can never
                    execute arbitrary code, never call a Python function that isn't one of the 9
                    tools, never invent a tenth tool)
                 -> agent.py validates + resolves arguments (e.g. customer_id -> full record)
                 -> agent_tools.py executes the ONE deterministic function that matches
                 -> the tool's exact {"ok","data","error"} result is handed back to the LLM,
                    verbatim, as a tool_result (never summarized or edited first)
                 -> repeat until the model has enough to answer, or a turn cap is hit
             -> either path returns an AgentResponse with a lightweight provenance record
                (tools_used, tool_calls, grounded, used_llm) -- never the model's internal
                reasoning, only "what tools were called".

No LLM call ever crashes the caller: `llm_provider.ProviderUnavailable` is always caught here and
turned into the deterministic fallback, with the reason attached (never a silent degradation --
same discipline as `copilot_engine.py`'s `llm_unavailable_reason`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from lib import agent_tools, copilot_data, copilot_engine, data, llm_provider, theme
from lib.agent_tool_schemas import TOOL_SCHEMAS, TOOL_NAMES

_MAX_TOOL_LOOP_ITERATIONS = 6


# ---------------------------------------------------------------------------
# Context + response types
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    """Everything the agent's tools need, already loaded by the caller (a Streamlit page, or a
    test) via the same `data.py` loaders every other page uses -- this module never loads
    anything itself. `customer_df` is the large ~971K-row table and may legitimately be `None`
    if the caller hasn't loaded it yet (the same lazy-load gate Customer 360 and Retention
    Copilot already use) -- tools that need it report a clear error rather than crashing.

    `selected_customer_id` / `selected_segment`, when set, mirror the existing Copilot's
    "currently attached context" (the customer/segment already resolved via the search box or
    segment picker before a question is asked) -- both the LLM path and the deterministic
    fallback use them to resolve an ambiguous "this customer" / "this segment" reference, and the
    deterministic fallback uses them to decide whether a customer- or segment-shaped question can
    be answered at all without an LLM.
    """
    action_plan: pd.DataFrame
    segment_summary: pd.DataFrame
    value_by_segment: pd.DataFrame
    risk_summary: dict
    value_by_tier: pd.DataFrame
    risk_value_matrix: pd.DataFrame
    shap_df: pd.DataFrame
    customer_df: pd.DataFrame | None = None
    selected_customer_id: str | None = None
    selected_segment: str | None = None


@dataclass
class ToolCallRecord:
    tool: str
    arguments: dict
    ok: bool
    result: dict = field(default_factory=dict)
    """The tool's full {"ok","data","error"} return. This is NOT shown to the manager as
    provenance text (the UI layer decides how -- or whether -- to render it, e.g. as a compact
    priority list rather than raw JSON) and is NOT re-sent to the LLM (it already received this
    exact payload as the tool_result during the loop). It exists so a page can render structured
    results (a customer profile, a list of matching customers) without re-querying the tools
    itself with guessed arguments."""


@dataclass
class AgentResponse:
    answer: str
    tools_used: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    grounded: bool = False
    used_llm: bool = False
    fallback_reason: str | None = None


# ---------------------------------------------------------------------------
# Tool dispatch -- a strict allow-list. The LLM (or the deterministic fallback) can only ever
# reach one of these 9 named functions; there is no code path from a tool name string to
# arbitrary Python execution.
# ---------------------------------------------------------------------------

def _need_customer_df(ctx: AgentContext) -> dict | None:
    """Returns an error dict if the large customer table hasn't been loaded yet, else None."""
    if ctx.customer_df is None:
        return {"ok": False, "data": None, "error": "Customer-level data has not been loaded yet for this session."}
    return None


def _resolve_customer(ctx: AgentContext, customer_id: str) -> dict:
    """Exact-ID lookup, returning agent_tools' own {"ok","data","error"} shape."""
    missing = _need_customer_df(ctx)
    if missing:
        return missing
    return agent_tools.get_customer(ctx.customer_df, customer_id)


def _exec_get_customer(args: dict, ctx: AgentContext) -> dict:
    customer_id = args.get("customer_id")
    if not customer_id:
        return {"ok": False, "data": None, "error": "customer_id is required"}
    return _resolve_customer(ctx, customer_id)


def _exec_search_customers(args: dict, ctx: AgentContext) -> dict:
    missing = _need_customer_df(ctx)
    if missing:
        return missing
    limit = args.get("limit", 20)
    if not isinstance(limit, int) or limit <= 0:
        return {"ok": False, "data": None, "error": "limit must be a positive integer"}
    return agent_tools.search_customers(
        ctx.customer_df,
        risk_tier=args.get("risk_tier"),
        value_tier=args.get("value_tier"),
        segment=args.get("segment"),
        min_risk_score=args.get("min_risk_score"),
        max_risk_score=args.get("max_risk_score"),
        min_calibrated_probability=args.get("min_calibrated_probability"),
        max_calibrated_probability=args.get("max_calibrated_probability"),
        min_hrr_ntd=args.get("min_hrr_ntd"),
        max_hrr_ntd=args.get("max_hrr_ntd"),
        auto_renew=args.get("auto_renew"),
        sort_by=args.get("sort_by", "risk_score_full"),
        ascending=args.get("ascending", False),
        limit=limit,
    )


def _exec_get_aggregate_metrics(args: dict, ctx: AgentContext) -> dict:
    return agent_tools.get_aggregate_metrics(
        ctx.risk_summary, ctx.value_by_tier, ctx.risk_value_matrix, ctx.action_plan, ctx.value_by_segment
    )


def _exec_get_segment(args: dict, ctx: AgentContext) -> dict:
    segment_name = args.get("segment_name")
    if not segment_name:
        return {"ok": False, "data": None, "error": "segment_name is required"}
    return agent_tools.get_segment(ctx.action_plan, ctx.segment_summary, segment_name)


def _exec_explain_customer_risk(args: dict, ctx: AgentContext) -> dict:
    missing = _need_customer_df(ctx)
    if missing:
        return missing
    customer_id = args.get("customer_id")
    if not customer_id:
        return {"ok": False, "data": None, "error": "customer_id is required"}
    n_drivers = args.get("n_drivers", 5)
    return agent_tools.explain_customer_risk(ctx.customer_df, ctx.shap_df, customer_id, n_drivers=n_drivers)


def _exec_recommend_action(args: dict, ctx: AgentContext) -> dict:
    customer_id, segment = args.get("customer_id"), args.get("segment")
    if bool(customer_id) == bool(segment):
        return {"ok": False, "data": None, "error": "Pass exactly one of customer_id or segment"}
    if customer_id:
        resolved = _resolve_customer(ctx, customer_id)
        if not resolved["ok"]:
            return resolved
        return agent_tools.recommend_action(ctx.action_plan, customer=resolved["data"])
    return agent_tools.recommend_action(ctx.action_plan, segment=segment)


def _exec_compare_to_champions(args: dict, ctx: AgentContext) -> dict:
    customer_id, segment = args.get("customer_id"), args.get("segment")
    if bool(customer_id) == bool(segment):
        return {"ok": False, "data": None, "error": "Pass exactly one of customer_id or segment"}
    if customer_id:
        resolved = _resolve_customer(ctx, customer_id)
        if not resolved["ok"]:
            return resolved
        return agent_tools.compare_to_champions(ctx.action_plan, ctx.value_by_segment, customer=resolved["data"])
    return agent_tools.compare_to_champions(ctx.action_plan, ctx.value_by_segment, segment=segment)


def _exec_rank_segments_by_priority(args: dict, ctx: AgentContext) -> dict:
    return agent_tools.rank_segments_by_priority(ctx.action_plan, top_n=args.get("top_n"))


def _exec_build_dashboard_deep_link(args: dict, ctx: AgentContext) -> dict:
    target_page = args.get("target_page")
    if not target_page:
        return {"ok": False, "data": None, "error": "target_page is required"}
    return agent_tools.build_dashboard_deep_link(target_page, customer_id=args.get("customer_id"))


_TOOL_DISPATCH = {
    "get_customer": _exec_get_customer,
    "search_customers": _exec_search_customers,
    "get_aggregate_metrics": _exec_get_aggregate_metrics,
    "get_segment": _exec_get_segment,
    "explain_customer_risk": _exec_explain_customer_risk,
    "recommend_action": _exec_recommend_action,
    "compare_to_champions": _exec_compare_to_champions,
    "rank_segments_by_priority": _exec_rank_segments_by_priority,
    "build_dashboard_deep_link": _exec_build_dashboard_deep_link,
}
assert set(_TOOL_DISPATCH) == set(TOOL_NAMES), "agent.py's dispatch table must exactly match agent_tool_schemas.py"


def _execute_tool(name: str, arguments: dict, ctx: AgentContext) -> dict:
    """The ONLY function that turns a tool-name string into a Python call. `name` must be an
    exact match in the fixed allow-list above -- there is no getattr/eval/exec anywhere in this
    path, so the LLM (or a malformed fallback route) can never reach any function other than one
    of the 9 named tools, regardless of what string it sends.

    P1-12: this is also the single point where a tool's RETURN value is validated. Every real
    dispatch function already returns the `{"ok", "data", "error"}` shape by construction (via
    `agent_tools._ok`/`_err`, or a manually-built dict of the same shape here in agent.py) -- but
    this function does not trust that by assumption. If a dispatch function were ever changed to
    return `None` (a silent fall-through), a bare string, or a dict missing "ok", the caller
    (`_run_tool_loop`) must still never crash on `result.get("ok")` -- it gets a safe, honestly-
    labeled failure instead."""
    if name not in _TOOL_DISPATCH:
        return {"ok": False, "data": None, "error": f"Unknown tool: {name!r}"}
    if not isinstance(arguments, dict):
        return {"ok": False, "data": None, "error": "Tool arguments must be an object"}
    try:
        result = _TOOL_DISPATCH[name](arguments, ctx)
    except Exception as e:  # noqa: BLE001 -- a tool must never crash the orchestration loop
        return {"ok": False, "data": None, "error": f"Tool execution failed: {type(e).__name__}: {e}"}
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        return {"ok": False, "data": None, "error": "Tool returned a malformed result"}
    return result


# ---------------------------------------------------------------------------
# System prompt -- grounding rules (task-required, verbatim in spirit) + answer structure +
# tool-selection guidance.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are Retention Intelligence, KKBOX's Retention Operations Assistant -- a \
retention operations analyst sitting on top of an existing, already-validated churn model and \
retention analytics pipeline, not a general-purpose chatbot. You help a retention/CRM manager \
answer: WHAT is happening, WHO needs attention, WHY are they at risk, WHAT should we do, and HOW \
confident is the evidence.

Voice: write like an experienced retention analyst briefing a manager. Be concise and operational \
-- lead with the point, no preamble. Be confident when the evidence genuinely supports a \
conclusion, and just as explicit and unhedged when it doesn't -- state uncertainty or missing data \
plainly, don't bury it in vague caveats. Be evidence-first (state the fact, then what it means) \
and action-oriented (close on what the retention team should do next, whenever the evidence \
supports one). Speak in business terms -- risk, value, retention effort -- not model internals.

You have access to 9 tools. Each one calls a deterministic Python function over real, already-\
computed data -- you have NO other way to access customer or business data. You must follow \
these rules with no exceptions:

RULE 1: Never invent customer information. Every fact about a customer must come from a tool result.
RULE 2: Never invent a customer ID. Only use an ID the manager gave you or that a tool returned.
RULE 3: Never invent numerical values. Every number in your answer must come from a tool result.
RULE 4: Never answer a customer-specific question without calling the appropriate tool first.
RULE 5: If a requested customer does not exist (a tool returns ok=false), say so explicitly.
RULE 6: If the available data does not contain something asked for, say exactly: "That \
information is not available in the current dataset." Do not infer or approximate it.
RULE 7: Never make a causal claim from a model association. Bad: "Auto-renew being off caused \
this customer to churn." Good: "Auto-renew is off, and this is one of the model-associated risk \
signals for this customer."
RULE 8: Never claim an intervention WILL reduce churn. Use "recommended action", "suggested \
treatment", or "priority for intervention" instead of a guarantee.
RULE 9: Never fabricate campaign performance, ROI, uplift, revenue saved, or treatment \
effectiveness -- none of that exists in this dataset.
RULE 10: If a question is outside what the tools can answer, explain the limitation plainly \
instead of guessing.
RULE 11: You are a decision-support assistant, not an autonomous system. You cannot contact a \
customer, send a message, apply a discount, change a subscription, or modify any record -- you \
can only recommend what the retention team should do. Never phrase an answer as if you are \
taking, or have already taken, an action yourself.

Terminology, never renamed or reinterpreted:
- "Model Risk Score" (model_risk_score / risk_score_full) is the RAW model output. It is NOT a \
calibrated probability -- never describe it as one, never say "X% probability" about it.
- "Estimated Churn Probability" (calibrated_probability) is the calibrated figure -- the only one \
of the two safe to call a probability.
- "Historical Realized Revenue" (HRR) is money already collected. NEVER call it CLV, lifetime \
value, or a revenue forecast.
- "High-Risk Historical Revenue Exposure" is a headcount exposure sum, NOT a probability-weighted \
expected loss.

Tool use: call the MINIMUM number of tools needed to answer -- do not call every tool "just in \
case". A question about one named customer usually needs one or two tool calls (e.g. \
get_customer, then recommend_action). A question spanning customers AND a recommendation \
(e.g. "find our most valuable at-risk customers and tell me what to do") may legitimately need \
two calls: one to find the customers, one to get the segment-level recommendation for what they \
have in common -- decide based on the actual question, never a fixed script. You may ONLY call \
the 9 provided tools. You cannot execute code, query a database directly, or access any \
information outside what a tool returns.

Answer structure -- write for a manager scanning quickly, never a raw JSON dump of a tool result. \
Follow this order whenever the evidence genuinely supports each part; skip a section rather than \
manufacture one with nothing real to say (e.g. a business-wide aggregate question usually has no \
single "recommended action" -- omit that section rather than invent one):
1. Finding -- what the data shows, stated directly. One line, the thing worth reading first.
2. Evidence -- the actual structured facts from the tool result(s) you called. Never re-query a \
tool for something already in a result you have, and never restate a raw JSON blob -- pull out \
the specific numbers/facts that support the Finding.
3. Why it matters -- your business interpretation of that evidence. State an association \
("indicates", "is associated with"), never a cause.
4. Recommended action -- pulled from the tool results' own recommendation/action fields \
(recommend_action's `objective`, rank_segments_by_priority's `recommended_action`, a segment's \
`marketing_objective`) or each customer's own `recommended_action` in a search_customers result. \
Never invent an intervention that isn't in the data.
5. Confidence/limitations -- state relevant limitations honestly. Model Risk Score is never a \
probability. This is historical association, not a causal experiment -- say so when relevant.
6. Next step (only when genuinely useful) -- point to an existing suggested question, a specific \
customer, a segment, or a dashboard page (Priority Customers, Customer 360, Action Center) that \
is already reachable. Never invent a destination or a capability that doesn't exist.

Keep answers concise. Do not narrate which tools you called or your reasoning process -- just \
answer, grounded in what the tools returned."""


def _build_tool_context_prefix(ctx: AgentContext) -> str:
    parts = []
    if ctx.selected_customer_id:
        parts.append(f"Currently selected customer: {ctx.selected_customer_id}")
    if ctx.selected_segment:
        parts.append(f"Currently selected segment: {ctx.selected_segment}")
    return ("\n".join(parts) + "\n\n") if parts else ""


# ---------------------------------------------------------------------------
# LLM tool-call loop
# ---------------------------------------------------------------------------

def _tool_call_signature(name: str, arguments: dict) -> str:
    """A stable, hashable key for 'the same tool called with the same arguments' -- used only to
    avoid re-executing a deterministic tool twice for an identical request within one loop, never
    to change what gets sent back to the model (every tool_use still gets its own tool_result;
    see the P1-12 comment in the loop below)."""
    import json
    try:
        return name + "::" + json.dumps(arguments, sort_keys=True, default=str)
    except TypeError:
        # Arguments that somehow aren't JSON-serializable (should not happen -- the LLM's tool
        # input is always JSON-decoded already) -- fall back to never matching a cache entry
        # rather than raising, so a truly odd payload just always re-executes.
        return name + "::" + repr(arguments)


class _OrchestrationFailed(Exception):
    """P1-12: raised internally when the tool-call loop reaches a genuine dead end -- the turn
    cap was exhausted, or the provider returned something too malformed to safely continue with
    -- and cannot produce a real final answer. Always caught by `ask()`, which treats it exactly
    like `llm_provider.ProviderUnavailable`: discard whatever partial state this attempt
    gathered and fall through to `_deterministic_fallback`, the SAME guaranteed-working path used
    when no AI provider is configured at all, rather than showing the manager a bare "the AI
    couldn't finish" dead end. Never propagates past `ask()`."""


def _run_tool_loop(question: str, ctx: AgentContext) -> AgentResponse:
    prefix = _build_tool_context_prefix(ctx)
    messages: list[dict] = [{"role": "user", "content": f"{prefix}Manager's question: {question}"}]
    tools_used: list[str] = []
    tool_calls: list[ToolCallRecord] = []
    # P1-12: results already computed once in this loop, keyed by (tool, arguments) signature --
    # a deterministic tool called twice with identical arguments always returns the same result,
    # so a repeated identical request is answered from this cache instead of re-executed. This
    # does not shorten the loop (the model still gets a real tool_result for every tool_use it
    # issues, exactly as the API requires) -- it only removes redundant computation, and is a
    # second line of defense alongside the hard `_MAX_TOOL_LOOP_ITERATIONS` turn cap below, which
    # remains the actual bound on how many rounds a pathologically repetitive model can consume.
    seen_results: dict[str, dict] = {}

    for _ in range(_MAX_TOOL_LOOP_ITERATIONS):
        response = llm_provider.complete_with_tools(_SYSTEM_PROMPT, messages, TOOL_SCHEMAS)

        # P1-12: defensive access only -- `llm_provider.complete_with_tools` always returns this
        # exact shape today (see its own docstring/contract), but agent.py does not assume that
        # forever holds for every possible provider implementation. `.get(...)` with a safe
        # default means a missing key here degrades to a clean failure, never a KeyError escaping
        # into the page.
        if not isinstance(response, dict):
            raise _OrchestrationFailed("the AI provider returned an unusable response")
        stop_reason = response.get("stop_reason")
        raw_tool_calls = response.get("tool_calls") or []

        if stop_reason == "tool_use" and not raw_tool_calls:
            # Claims tool use but names none -- malformed/anomalous, not a real final answer and
            # not a real tool request either. Never loop on nothing.
            raise _OrchestrationFailed("the AI provider requested tool use but specified no tool")

        if stop_reason != "tool_use":
            # A genuine final turn -- return it as-is, even if grounded is False (e.g. every tool
            # call this turn failed); this is the LLM's own real answer, not a failure to paper
            # over with the deterministic path.
            return AgentResponse(
                answer=response.get("text") or "The AI provider returned an empty answer.",
                tools_used=tools_used, tool_calls=tool_calls,
                grounded=any(c.ok for c in tool_calls), used_llm=True,
            )

        messages.append({"role": "assistant", "content": response.get("raw_content") or []})
        tool_result_blocks = []
        for call in raw_tool_calls:
            if not isinstance(call, dict):
                call = {}
            # P1-12: a missing/malformed "name" safely falls through _execute_tool's own
            # allow-list check below (an empty/None name is simply not in _TOOL_DISPATCH); a
            # missing "input" defaults to {} (rejected by _execute_tool's dict-type check only if
            # it truly isn't a dict); a missing "id" gets a locally-generated placeholder so the
            # API-required tool_result can still be built rather than skipped or crashing.
            name = call.get("name")
            call_args = call.get("input")
            call_id = call.get("id") or f"missing_id_{len(tool_calls)}"
            if call_args is None:
                call_args = {}

            signature = _tool_call_signature(name, call_args) if isinstance(call_args, dict) else None
            if signature is not None and signature in seen_results:
                result = seen_results[signature]
            else:
                result = _execute_tool(name, call_args, ctx)
                if signature is not None:
                    seen_results[signature] = result

            tools_used.append(name)
            tool_calls.append(ToolCallRecord(tool=name, arguments=call_args, ok=bool(result.get("ok")), result=result))
            tool_result_blocks.append(llm_provider.format_tool_result(call_id, result))
        messages.append({"role": "user", "content": tool_result_blocks})

    # Exceeded the turn cap without a final answer -- fail safe rather than loop forever.
    raise _OrchestrationFailed("tool-call loop exceeded its turn limit")


# ---------------------------------------------------------------------------
# Deterministic fallback -- used when no LLM is configured, or a configured call fails. Routes
# the SAME well-defined question shapes the existing Copilot already supports (via
# copilot_engine.py, unchanged) plus a small set of new tool-shaped questions (aggregate metrics,
# segment ranking) directly to one tool call each. Anything else gets an honest "unavailable"
# answer rather than a guess -- this is intentionally narrower than the LLM path, per the task's
# explicit instruction not to fake AI-quality routing without an AI.
# ---------------------------------------------------------------------------

_AGGREGATE_KEYWORDS = ("how many", "total customers", "churn rate", "aggregate", "overall", "elevated risk", "at risk are there")
_RANK_SEGMENT_KEYWORDS = ("which segment", "prioritize", "rank segment")
# "Who should we contact first" -> the actual priority/customer ranking capability (search_customers,
# sorted by Model Risk Score, no value filter -- this is the same "priority queue" definition
# Priority Customers itself uses, just narrowed to the highest-urgency tier for a "first" answer).
_CONTACT_FIRST_KEYWORDS = ("contact first", "who should we contact", "who should we save", "who to contact", "who do we contact")
# "Show me high-risk, high-value customers" -> the same search_customers tool, filtered on BOTH
# tiers this phrasing names explicitly -- matches Overview's own "Priority Zone" (High risk x
# High value) framing, not a new definition invented for this route.
_HIGH_RISK_HIGH_VALUE_KEYWORDS = (
    "high-risk, high-value", "high risk, high value", "high-risk high-value", "high risk high value",
    "high risk and high value", "high-risk and high-value", "high risk, high-value",
)
# A question phrased about "this/that customer" with no customer actually selected. This is a
# routing/context problem, not a missing capability -- the honest answer is to say so and point
# the manager at the search box, never a guess and never the generic "unsupported question" text.
_CUSTOMER_REFERENCE_PHRASES = ("this customer", "that customer")

# Shared guidance text for "this needs the large customer table, which isn't loaded yet" -- used
# everywhere that condition can arise, so the message is worded identically no matter which
# question path hit it.
_LOAD_DATA_GUIDANCE = (
    "This question needs the full customer table, which hasn't been loaded yet for "
    "this session. Click \"Load customer data\" above, then ask again."
)


def _render_copilot_answer(a: copilot_engine.CopilotAnswer) -> str:
    """Plain-text rendering of a `CopilotAnswer` for the customer- and segment-scoped deterministic
    fallback path. Every field here already exists on `CopilotAnswer` (built in
    `copilot_engine.deterministic_customer_answer` / `deterministic_segment_answer` from the same
    evidence the LLM path would also use) -- this function only orders and labels them.

    P1-11: reordered into Finding(Recommendation) -> Evidence -> Why it matters -> Recommended
    action(+Avoid) -> Confidence/limitations, matching the same six-part structure used by the
    aggregate/rank-segments/search-customer formatters below. No "Next step" line is added here:
    the genuinely applicable next step for a customer or segment answer -- "Open full profile in
    Customer 360" / "View {segment} customers in Priority Customers" -- is already a persistent,
    working link rendered directly above every answer on this page (see retention_copilot.py's
    `context_slot`), not something this function has a second, different destination to offer;
    repeating it as a text line here would be a manufactured section, not new information.
    """
    lines = [f"Recommendation: {a.recommendation}"]
    if a.evidence:
        lines.append("Evidence: " + "; ".join(a.evidence))
    if a.why:
        lines.append(f"Why it matters: {a.why}")
    if a.what_to_do:
        lines.append(f"Recommended action: {a.what_to_do}")
    if a.what_to_avoid:
        lines.append(f"Avoid: {a.what_to_avoid}")
    confidence_parts = [p for p in (a.confidence_basis, a.caution) if p]
    if confidence_parts:
        lines.append("Confidence/limitations: " + " ".join(confidence_parts))
    return "\n".join(lines)


def _format_aggregate_answer(m: dict) -> str:
    # Monetary figures route through theme.fmt_currency -- the SAME centralized NT$->INR
    # display conversion every other page uses (theme.NTD_TO_INR is the one fixed rate in the
    # whole project; nothing here re-implements or re-derives it). The source values
    # (*_ntd fields) remain in NT$ exactly as agent_tools.get_aggregate_metrics returned them --
    # only the rendered string changes.
    #
    # P1-11: Finding (Headline) -> Evidence (the stat lines, unchanged from P1-10) -> Why it
    # matters -> Confidence/limitations -> Next step. There is no single "Recommended action" for
    # a business-wide aggregate question -- the action framework operates at the segment/customer
    # level (see _format_rank_segments_answer / _render_copilot_answer) -- so that section is
    # genuinely not applicable here and is omitted rather than manufactured.
    #
    # "Why it matters" is a plain ratio of two numbers already in this same answer (high-risk
    # revenue exposure as a share of total realized revenue) -- not a new query, not an invented
    # fact -- worded as a neutral comparison, not a claim about direction, since which way that
    # ratio falls is a real fact this function must not assume.
    high_risk_revenue_pct = (
        m["high_risk_historical_revenue_exposure_ntd"] / m["total_realized_revenue_ntd"] * 100
        if m["total_realized_revenue_ntd"] else 0.0
    )
    high_risk_base_pct = (
        m["high_risk_customers"] / m["n_customers_scored"] * 100 if m["n_customers_scored"] else 0.0
    )
    lines = [
        f"Headline: {m['n_customers_scored']:,} customers scored, {m['overall_churn_rate_pct']:.1f}% overall churn rate.",
        f"High risk: {m['high_risk_customers']:,} customers. Elevated risk (Medium+High): {m['elevated_risk_customers']:,} customers.",
        f"High-risk x High-value population: {m['high_risk_high_value_customers']:,} customers.",
        f"Total Historical Realized Revenue: {theme.fmt_currency(m['total_realized_revenue_ntd'])}.",
        f"High-Risk Historical Revenue Exposure: {theme.fmt_currency(m['high_risk_historical_revenue_exposure_ntd'])}.",
        f"Why it matters: High-risk customers are {high_risk_base_pct:.1f}% of the scored base by count and "
        f"hold {high_risk_revenue_pct:.1f}% of total realized revenue -- the "
        f"{m['high_risk_high_value_customers']:,} customers who are both High risk and High value (above) "
        "are where risk and revenue genuinely overlap, and where retention effort has the most at stake per customer.",
        "Confidence/limitations: High-Risk Historical Revenue Exposure is a headcount exposure sum, not an "
        "expected loss, and Model Risk Score (used to define the High-risk tier) is not a calibrated probability.",
        "Recommended next step: ask \"Which segment needs attention?\" to find where to focus, or "
        "\"Who should we contact first?\" to see the highest-priority customers directly.",
    ]
    return "\n".join(lines)


def _format_rank_segments_answer(rows: list[dict]) -> str:
    # P1-10: previously a flat numbered list restating every returned segment with equal visual
    # weight and no Finding-tier line at all. P1-11: the top segment is still the Finding (a
    # "Headline:" line, picked up by the existing, unchanged tiering logic in
    # components.agent_response_block -- no new UI code), but the recommended action -- previously
    # folded into the same sentence as the Finding -- is now its own "Recommended action:" line,
    # per the acceptance criterion that evidence/finding and action must be visually and textually
    # distinct. "Why it matters" reuses the exact justification copilot_engine.py's own
    # which_segment_priority branch already gives for this same ranking (not a new interpretation
    # invented for this formatter). No row is ever dropped from the underlying data; this only
    # changes how many are restated in prose, and only when more exist beyond what's shown does a
    # closing line point at Action Center, which already has the complete ranked portfolio.
    if not rows:
        return "No segments currently need prioritization."
    top = rows[0]
    lines = [
        f"Headline: {top['segment']} is the top retention priority -- {top['n_customers']:,} customers, "
        f"{top['churn_rate_pct']:.1f}% churn, {theme.fmt_currency(top['total_hrr_ntd'])} at stake.",
    ]
    runners_up = rows[1:3]
    if runners_up:
        lines.append("Also worth attention: " + "; ".join(
            f"{r['priority']}. {r['segment']} ({theme.fmt_currency(r['total_hrr_ntd'])} at stake, "
            f"recommended: {r['recommended_action']})"
            for r in runners_up
        ) + ".")
    lines.append(f"Recommended action: {top['recommended_action']}.")
    lines.append(
        "Why it matters: ranked by Historical Realized Revenue at stake among the at-risk segments the "
        "action framework recommends intervening on -- the same ranking used on Overview and Action Center."
    )
    lines.append(
        "Confidence/limitations: this ranking is based on realized revenue already collected, not a "
        "probability-weighted forecast of prevented churn."
    )
    if len(rows) > 3:
        lines.append(f"Recommended next step: see the complete ranked list of all {len(rows):,} segments, with revenue at stake and the recommended action for each, in Action Center.")
    return "\n".join(lines)


def _format_search_customers_answer(d: dict, *, headline: str, why: str = "") -> str:
    """Renders a `search_customers` tool result as plain answer text. The actual customer rows
    are NOT restated here as a numeric wall -- `components.agent_response_block` already renders
    them as a compact, click-through priority list from the same tool result (via
    `ToolCallRecord.result`), exactly as it does for an LLM-driven search_customers call.

    P1-11: Finding (headline) -> Evidence (result summary) -> Why it matters (optional, only when
    the caller has a real, grounded reason this specific filter combination was chosen) ->
    Recommended action -> Confidence/limitations -> Next step. "Recommended action" points at the
    per-customer `recommended_action` already present in each row below (rendered by
    `components.priority_list`) rather than inventing one combined action for a list that can
    span multiple segments with different recommended treatments -- restating it here as a single
    line would either be wrong for some rows or would re-derive something already shown."""
    rows = d.get("rows") or []
    total = d.get("total_matches", len(rows))
    if not rows:
        return f"{headline}\n\nNo customers currently match this in the scored customer base."
    shown = min(len(rows), 5)
    lines = [
        headline,
        f"Result summary: {total:,} customer{'s' if total != 1 else ''} match -- the top {shown} by Model Risk Score are below.",
    ]
    if why:
        lines.append(f"Why it matters: {why}")
    lines.append(
        "Recommended action: see each customer's recommended treatment in the list below, from the "
        "validated action framework -- it varies by the customer's segment."
    )
    lines.append(
        "Confidence/limitations: this list is ranked by Model Risk Score, the model's raw output -- not a "
        "calibrated probability. Estimated Churn Probability is the calibrated figure, shown per customer."
    )
    lines.append("Recommended next step: open a customer below for the full profile, or view the complete list in Priority Customers.")
    return "\n".join(lines)


def _deterministic_fallback(question: str, ctx: AgentContext, reason: str) -> AgentResponse:
    """Reuses `copilot_engine.py`'s existing, already-tested deterministic answer templates
    directly (the exact same code path the current preset-question Copilot uses) for a customer-
    or segment-shaped question, rather than a second, weaker parallel formatter. This is the
    concrete form of "preserve the deterministic answer path, add orchestration above it": when
    there is no AI to orchestrate with, this function IS the existing Copilot."""
    q = question.lower()

    if ctx.selected_customer_id:
        # Distinguish "the table isn't loaded yet" from "this ID genuinely isn't in the scored
        # base" -- these are different facts and conflating them into one message would be a
        # small but real honesty violation (previously this branch said "couldn't find that
        # customer" even when the true reason was that customer-level data hadn't been loaded).
        if ctx.customer_df is None:
            return AgentResponse(
                answer=_LOAD_DATA_GUIDANCE,
                grounded=False, used_llm=False, fallback_reason=reason,
            )
        cust_result = _resolve_customer(ctx, ctx.selected_customer_id)
        if not cust_result["ok"]:
            return AgentResponse(
                answer="I couldn't find that customer in the scored customer base.",
                grounded=False, used_llm=False, fallback_reason=reason,
            )
        cust = cust_result["data"]
        pop = copilot_data.get_population_baselines(ctx.customer_df)
        champions = copilot_data.get_champions_context(ctx.action_plan, ctx.value_by_segment)
        top_drivers = copilot_data.get_top_drivers(ctx.shap_df, data.feature_display_name, n=5)
        copilot_answer = copilot_engine.deterministic_customer_answer(
            copilot_engine.classify_customer_intent(question), cust, pop, champions, top_drivers
        )
        return AgentResponse(
            answer=f"[AI synthesis unavailable: {reason} -- showing the grounded deterministic answer]\n\n{_render_copilot_answer(copilot_answer)}",
            tools_used=["get_customer"],
            tool_calls=[ToolCallRecord("get_customer", {"customer_id": ctx.selected_customer_id}, True, result=cust_result)],
            grounded=True, used_llm=False, fallback_reason=reason,
        )

    if ctx.selected_segment:
        seg_result = agent_tools.get_segment(ctx.action_plan, ctx.segment_summary, ctx.selected_segment)
        if not seg_result["ok"]:
            return AgentResponse(answer=seg_result["error"], grounded=False, used_llm=False, fallback_reason=reason)
        all_segments = {
            s: c for s in copilot_data.SEGMENTS
            if (c := copilot_data.get_segment_context(ctx.action_plan, ctx.segment_summary, s)) is not None
        }
        copilot_answer = copilot_engine.deterministic_segment_answer(
            copilot_engine.classify_segment_intent(question), seg_result["data"], all_segments
        )
        return AgentResponse(
            answer=f"[AI synthesis unavailable: {reason} -- showing the grounded deterministic answer]\n\n{_render_copilot_answer(copilot_answer)}",
            tools_used=["get_segment"],
            tool_calls=[ToolCallRecord("get_segment", {"segment_name": ctx.selected_segment}, True, result=seg_result)],
            grounded=True, used_llm=False, fallback_reason=reason,
        )

    if any(k in q for k in _CONTACT_FIRST_KEYWORDS):
        missing = _need_customer_df(ctx)
        if missing:
            return AgentResponse(
                answer=_LOAD_DATA_GUIDANCE,
                grounded=False, used_llm=False, fallback_reason=reason,
            )
        args = {"risk_tier": ["High"], "sort_by": "risk_score_full", "ascending": False, "limit": 10}
        result = agent_tools.search_customers(ctx.customer_df, **args)
        if result["ok"]:
            answer = _format_search_customers_answer(
                result["data"],
                headline="Headline: These are the highest-priority customers to contact first, ranked by Model Risk Score.",
                why="These are the customers with the model's highest risk signal in the base -- "
                    "addressing them first concentrates retention effort where the model indicates "
                    "the most urgent risk.",
            )
            return AgentResponse(
                answer=f"[AI synthesis unavailable: {reason} -- showing the grounded deterministic answer]\n\n{answer}",
                tools_used=["search_customers"],
                tool_calls=[ToolCallRecord("search_customers", args, True, result=result)],
                grounded=True, used_llm=False, fallback_reason=reason,
            )

    if any(k in q for k in _HIGH_RISK_HIGH_VALUE_KEYWORDS):
        missing = _need_customer_df(ctx)
        if missing:
            return AgentResponse(
                answer=_LOAD_DATA_GUIDANCE,
                grounded=False, used_llm=False, fallback_reason=reason,
            )
        args = {"risk_tier": ["High"], "value_tier": ["High"], "sort_by": "risk_score_full", "ascending": False, "limit": 10}
        result = agent_tools.search_customers(ctx.customer_df, **args)
        if result["ok"]:
            answer = _format_search_customers_answer(
                result["data"],
                headline="Headline: These customers are both High risk and High value -- the Priority Zone.",
                why="These customers combine elevated model risk with High historical revenue -- the "
                    "combination the action framework prioritizes highest for retention effort.",
            )
            return AgentResponse(
                answer=f"[AI synthesis unavailable: {reason} -- showing the grounded deterministic answer]\n\n{answer}",
                tools_used=["search_customers"],
                tool_calls=[ToolCallRecord("search_customers", args, True, result=result)],
                grounded=True, used_llm=False, fallback_reason=reason,
            )

    if any(k in q for k in _AGGREGATE_KEYWORDS):
        result = _exec_get_aggregate_metrics({}, ctx)
        if result["ok"]:
            answer = _format_aggregate_answer(result["data"])
            return AgentResponse(
                answer=f"[AI synthesis unavailable: {reason} -- showing the grounded deterministic answer]\n\n{answer}",
                tools_used=["get_aggregate_metrics"],
                tool_calls=[ToolCallRecord("get_aggregate_metrics", {}, True, result=result)],
                grounded=True, used_llm=False, fallback_reason=reason,
            )

    if any(k in q for k in _RANK_SEGMENT_KEYWORDS):
        result = _exec_rank_segments_by_priority({}, ctx)
        if result["ok"]:
            answer = _format_rank_segments_answer(result["data"]["rows"])
            return AgentResponse(
                answer=f"[AI synthesis unavailable: {reason} -- showing the grounded deterministic answer]\n\n{answer}",
                tools_used=["rank_segments_by_priority"],
                tool_calls=[ToolCallRecord("rank_segments_by_priority", {}, True, result=result)],
                grounded=True, used_llm=False, fallback_reason=reason,
            )

    # A customer-shaped question ("why is THIS customer at risk", "what should we do for THAT
    # customer") with no customer actually selected -- this is a routing/context problem, not an
    # unsupported question, so it gets its own honest, specific guidance rather than the generic
    # "doesn't match a question this dashboard can answer" message below. This is guidance, not an
    # answer: grounded stays False and no tool is called, so it can never be mistaken for a real,
    # evidence-backed response about an unspecified customer.
    if any(p in q for p in _CUSTOMER_REFERENCE_PHRASES):
        return AgentResponse(
            answer=(
                "This question is about a specific customer, but none is currently selected. "
                "Search for a customer by ID above, or open one from Priority Customers or "
                "Customer 360, then ask this again."
            ),
            grounded=False, used_llm=False, fallback_reason=reason,
        )

    return AgentResponse(
        answer=(
            "AI synthesis is unavailable for this question "
            f"({reason}), and it doesn't match a question this dashboard can answer "
            "deterministically without one. Try selecting a specific customer or segment first, "
            "or ask a simpler question such as \"how many customers are at elevated risk\" or "
            "\"which segment should we prioritize\"."
        ),
        grounded=False, used_llm=False, fallback_reason=reason,
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def ask(question: str, ctx: AgentContext) -> AgentResponse:
    """Answer one manager question, grounded entirely in `agent_tools.py`. Always returns a
    usable AgentResponse -- never raises, never returns a blank/broken answer.

    P1-12 -- reliability hardening: every way the LLM tool-call loop can fail (no API key,
    request/timeout failure, a turn-cap-exhausting or otherwise unusable provider response --
    `_run_tool_loop` raises `_OrchestrationFailed` for the latter two) reaches this SAME
    `_deterministic_fallback` call. This is the one, single recovery path this function has, and
    it is exercised identically regardless of *why* the LLM path didn't work -- there is no
    second, parallel "partial LLM answer" path that could show incomplete evidence as complete.
    The final `except Exception` is a deliberate, broad last resort (same discipline already used
    at this project's other module boundaries -- see `llm_provider.py`, `_execute_tool` above):
    any truly unforeseen bug in the orchestration loop must degrade to the deterministic path,
    never crash the page.
    """
    if not question or not question.strip():
        return AgentResponse(answer="Ask a question about a customer, a segment, or the overall customer base.", grounded=False, used_llm=False)

    if not llm_provider.is_configured():
        return _deterministic_fallback(question, ctx, reason="no AI provider is configured for this session")

    try:
        return _run_tool_loop(question, ctx)
    except (llm_provider.ProviderUnavailable, _OrchestrationFailed) as e:
        return _deterministic_fallback(question, ctx, reason=str(e))
    except Exception as e:  # noqa: BLE001 -- last-resort safety net; see docstring above
        return _deterministic_fallback(question, ctx, reason=f"unexpected orchestration error: {type(e).__name__}")


def get_tool_result(response: AgentResponse, tool_name: str) -> dict | None:
    """Convenience for the UI layer: the successful `data` payload of the most recent call to
    `tool_name` in this response, or None if that tool wasn't called (or failed). Used to decide
    whether to render a structured extra -- a priority list for `search_customers`, a profile
    header for `get_customer` -- alongside the answer text, without the page re-guessing
    arguments or re-querying tools itself."""
    for call in reversed(response.tool_calls):
        if call.tool == tool_name and call.ok:
            return call.result.get("data")
    return None
