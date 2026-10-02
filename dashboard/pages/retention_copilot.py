import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from lib import agent, agent_tool_schemas, caveats, components, copilot_data, data, llm_provider, theme

theme.apply_page_style()

theme.masthead(
    "pages/retention_copilot.py", "Intelligence layer &nbsp;·&nbsp; RETENTION OPERATIONS ASSISTANT",
    "Retention Intelligence",
    "Ask who needs attention, why, and what to do next. Every answer is built from the project's own "
    "data -- it cannot invent a customer or a number.",
)

# A grounding indicator belongs directly under the header -- "what am I currently focused on"
# (the whole book of business, a segment, or one customer) is the first thing a manager should
# see. Its content depends on `cust_ctx`/`segment_choice`, which aren't resolved until the scope
# controls render further down this script -- so this reserves the position now and is filled in
# once that context is known.
context_slot = st.container()

# ---------------------------------------------------------------------------
# Small aggregate data -- always available, no gate. Large per-customer data is loaded on
# demand, same as every other page that touches it.
# ---------------------------------------------------------------------------
risk_summary = data.safe_load(data.load_risk_summary)
action_plan = data.safe_load(data.load_action_plan)
value_by_segment = data.safe_load(data.load_value_by_segment)
segment_summary = data.safe_load(data.load_segment_summary)
shap_df = data.safe_load(data.load_shap_importance)
value_by_tier = data.safe_load(data.load_value_by_tier)
risk_value_matrix = data.safe_load(data.load_risk_value_matrix)

# DATA -> TOOLS -> EVIDENCE -> DECISION: how every answer on this page is produced, stated as system
# fact (tool count from the agent's own allow-list), plus which mode is live right now.
_ai_live = llm_provider.is_configured()
_mode_html = (
    '<span class="ri-mode"><i></i>AI synthesis over tool results</span>' if _ai_live
    else '<span class="ri-mode det"><i></i>Deterministic mode</span><br/>No AI provider configured -- answers come straight from the tools'
)
with st.expander("How answers are produced"):
    theme.md(
        f"""<div class="ri-pipe">
            <div><div class="k">1 &middot; Data</div><div class="d">{theme.fmt_count(risk_summary['n_customers_scored'])} scored customers &middot; {len(copilot_data.SEGMENTS)} action groups</div></div>
            <div><div class="k">2 &middot; Tools</div><div class="d">{len(agent_tool_schemas.TOOL_NAMES)} read-only analytical tools on an explicit allow-list</div></div>
            <div><div class="k">3 &middot; Evidence</div><div class="d">Every figure in an answer comes from a tool result</div></div>
            <div><div class="k">4 &middot; Decision</div><div class="d">Finding &rarr; action &rarr; confidence &rarr; next step</div></div>
            <div class="mode"><div class="k">Answer mode</div><div class="d">{_mode_html}</div></div>
        </div>"""
    )

if "lookup_loaded" not in st.session_state:
    st.session_state["lookup_loaded"] = False

customer_df = None
if st.session_state["lookup_loaded"]:
    customer_df = data.safe_load(data.load_customer_lookup_data)
else:
    # A quiet system note, not a technical loading screen -- infrastructure the manager doesn't
    # need to think about. A plain (not primary) button, weighted like any secondary control.
    with st.container(key="gate_ri"):
        note_col, btn_col = st.columns([4, 1.1], vertical_alignment="center")
        with note_col:
            theme.recede(
                "Customer-level questions need the full customer table loaded once for this "
                "session. Segment and business-wide questions work immediately."
            )
        with btn_col:
            if st.button("Load customer data", width="stretch"):
                st.session_state["lookup_loaded"] = True
                st.rerun()

console_left, console_right = st.columns([1, 1.6], gap="large")

# ---------------------------------------------------------------------------
# Scope -- who/what the assistant is grounded to. The shared `cust360_search` session key (the same
# one Priority Customers and Customer 360 use) and a segment picker: a customer selected elsewhere,
# or "Ask Retention Intelligence" clicked from a profile, arrives here automatically.
# ---------------------------------------------------------------------------
with console_left:
    st.markdown('<div class="ri-eyebrow" style="margin-top:1.1rem;">Scope</div>', unsafe_allow_html=True)
    search = st.text_input(
        "Search by Customer ID", placeholder="Focus on a customer by ID (msno)…",
        value=st.session_state.get("cust360_search", ""),
        key="copilot_search_widget", label_visibility="collapsed",
    )
    st.session_state["cust360_search"] = search
    segment_choice = st.selectbox(
        "Segment", ["No segment focus"] + copilot_data.SEGMENTS, key="copilot_segment_choice", label_visibility="collapsed",
    )
    segment_choice = None if segment_choice == "No segment focus" else segment_choice

    cust_ctx = None
    if customer_df is not None and search:
        matches = customer_df[customer_df["msno"].str.contains(search, case=False, na=False, regex=False)]
        if matches.empty:
            st.markdown('<p class="recede">I couldn\'t find that customer in the scored customer base.</p>', unsafe_allow_html=True)
        else:
            if len(matches) > 1:
                picked_id = st.selectbox(f"{len(matches):,} matches -- pick one", matches["msno"].head(200).tolist())
            else:
                picked_id = matches.iloc[0]["msno"]
            cust_ctx = copilot_data.get_customer_context(customer_df, picked_id)

# A customer in focus takes precedence over a segment selection -- asking "why is this customer
# at risk" should never accidentally answer about a segment instead.
if cust_ctx:
    segment_choice = None

# Clear any answer left over from a different customer/segment/general context -- switching who
# or what is being asked about must never leave a stale answer looking like it belongs to the
# new context. The free-text box is emptied alongside the answer for the same reason: a question
# left visible in the box after its answer has been discarded reads as if it were still the
# active question. (Safe to assign here -- `copilot_freetext`'s widget is instantiated further
# down this script, and Streamlit only forbids writing a widget's state AFTER instantiation.)
_context_id = f"customer:{cust_ctx['msno']}" if cust_ctx else (f"segment:{segment_choice}" if segment_choice else "general")
if st.session_state.get("copilot_context_id") != _context_id:
    st.session_state.pop("copilot_asked", None)
    st.session_state["copilot_freetext"] = ""
    st.session_state["copilot_context_id"] = _context_id

# Fill the grounding slot reserved under the header -- always visible, never blank: the whole
# scored base, one segment, or one customer, each with its own one-click way to act on it.
with context_slot:
    if cust_ctx:
        badges = (
            theme.risk_chip(cust_ctx["risk_tier"]) + theme.value_chip(cust_ctx["value_tier"])
            + theme.badge(cust_ctx["segment"], theme.COLORS["ink_3"])
        )
        theme.context_strip(
            f'<span class="k">In focus</span> Analysing customer '
            f'<b class="ri-mono">{theme.esc(cust_ctx["msno"])}</b> &nbsp; {badges}',
            dot_color=theme.RISK_COLOR_MAP.get(cust_ctx["risk_tier"], theme.COLORS["neutral"]),
        )
        st.page_link("pages/customer_360.py", label="Open full profile in Customer 360 →")
    elif segment_choice:
        theme.context_strip(
            f'<span class="k">In focus</span> Segment in focus: <b>{segment_choice}</b>',
            dot_color=theme.COLORS["cyan"],
        )
        if st.button(f"View {segment_choice} customers in Priority Customers →", key="ri_segment_to_priority"):
            st.session_state["pending_filter"] = {"segment": [segment_choice]}
            st.switch_page("pages/priority_customers.py")
    else:
        _tiers_by_name = {t["tier"]: t for t in risk_summary["risk_tiers"]}
        theme.context_strip(
            f'<span class="k">In focus</span> Grounded in the full scored base &nbsp; <b>{theme.fmt_count(risk_summary["n_customers_scored"])}</b> customers '
            f"&middot; <b>{theme.fmt_count(_tiers_by_name['High']['n_customers'])}</b> High risk "
            f"&middot; <b>{theme.fmt_pct(risk_summary['actual_churn_rate'] * 100)}</b> churn",
            dot_color=theme.COLORS["neutral"],
        )

# ---------------------------------------------------------------------------
# Suggested questions -- operational commands that adapt to scope, always example-only (never
# hard-coded answers). General mode follows the start of the manager flow -- "see what's happening"
# then "find who needs attention" -- and deliberately does NOT offer customer-scoped questions:
# with no customer selected they could only ever produce a "please select a customer" message.
# ---------------------------------------------------------------------------
suggested = None
general_groups = None
if cust_ctx:
    suggested = [
        "Why is this customer at risk?",
        "What should we do for this customer?",
        "Should we offer a discount?",
        "Why is this customer worth retaining?",
        "How does this customer compare with Champions?",
        "What are the main reasons this customer was prioritized?",
    ]
elif segment_choice:
    suggested = [
        f"Tell me about {segment_choice} customers.",
        "Why is this segment important?",
        "What should we do with this segment?",
        "How does this segment compare with Champions?",
    ]
else:
    general_groups = [
        ("See what's happening", ["How many customers are at elevated risk?", "Which segment needs attention?"]),
        ("Find who needs attention", ["Who should we contact first?", "Show me high-risk, high-value customers."]),
    ]


# Both question sources -- a suggested-question button and the free-text box -- do exactly one
# thing: record WHICH question was asked. Routing stays in the single `agent.ask()` call below.
def _select_suggested(question: str) -> None:
    # Picking a suggestion also empties the free-text box, so the box can never keep displaying a
    # question that is no longer the one being answered.
    st.session_state["copilot_asked"] = question
    st.session_state["copilot_freetext"] = ""


def _submit_free_text() -> None:
    text = (st.session_state.get("copilot_freetext") or "").strip()
    if text:
        st.session_state["copilot_asked"] = text


with console_left:
    if suggested is not None:
        st.markdown('<div class="qa-question">Ask</div>', unsafe_allow_html=True)
        for i, q in enumerate(suggested):
            if st.button(q, width="stretch", key=f"suggested_{i}"):
                _select_suggested(q)
    else:
        btn_idx = 0
        for group_label, group_qs in general_groups:
            theme.eyebrow(group_label)
            for q in group_qs:
                if st.button(q, width="stretch", key=f"suggested_{btn_idx}"):
                    _select_suggested(q)
                btn_idx += 1
        theme.recede(
            "Search for a customer above, or pick a segment, to ask why a specific one is at risk "
            "or what to do about it."
        )

    st.markdown('<div class="ri-eyebrow">Or ask in your own words</div>', unsafe_allow_html=True)
    # Submitting free text is an EVENT, so it is handled by an on_change callback rather than by
    # reading the widget's return value. A keyed text_input keeps its value across every later
    # rerun; reading that value each run made a stale entry overwrite a suggested-question click
    # made on the same run (the buttons render before this widget), so the button looked dead.
    # on_change fires only on the rerun where the manager actually submitted new text.
    _scope_word = "this customer" if cust_ctx else ("this segment" if segment_choice else "the business")
    st.text_input(
        "Ask a question…", key="copilot_freetext", label_visibility="collapsed",
        placeholder=f"Ask anything about {_scope_word}, then press Enter…",
        on_change=_submit_free_text,
    )

# ---------------------------------------------------------------------------
# Answer -- routed entirely through the agent orchestrator. Grounded in agent_tools.py either way:
# via LLM tool-calling when a provider is configured, or via the deterministic fallback (the
# existing answer engine, called directly) when it isn't.
# ---------------------------------------------------------------------------
asked = st.session_state.get("copilot_asked")
has_context_or_history = bool(cust_ctx) or bool(segment_choice) or bool(asked)

with console_right:
    if not has_context_or_history:
        # First-open state -- the console at rest, telling the manager what it can do.
        theme.empty_state(
            "RETENTION INTELLIGENCE",
            "Ask a question about customers, risk, value, or retention actions.",
            "Search for a customer or pick a segment to focus the assistant, or ask a "
            "general question. Every answer is grounded in the project's actual data -- "
            "nothing here can invent a customer, a number, or a result.",
        )
    elif not asked:
        theme.empty_state(
            "READY",
            "Pick a question on the left.",
            "The answer will be grounded in the scope shown above -- change the customer or segment "
            "at any time and the assistant re-grounds itself.",
        )
    else:
        ctx = agent.AgentContext(
            action_plan=action_plan, segment_summary=segment_summary, value_by_segment=value_by_segment,
            risk_summary=risk_summary, value_by_tier=value_by_tier, risk_value_matrix=risk_value_matrix,
            shap_df=shap_df, customer_df=customer_df,
            selected_customer_id=cust_ctx["msno"] if cust_ctx else None,
            selected_segment=segment_choice,
        )
        with st.spinner("Retention Intelligence is consulting the retention model…"):
            response = agent.ask(asked, ctx)

        with st.container(key="ri_answer"):
            st.markdown('<div class="qa-question">You asked</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="qa-question-text profile-panel">"{asked}"</div>', unsafe_allow_html=True)
            # A restrained, consistent name treatment for every answer -- the same label styling as
            # "You asked", so every answer reads as coming from the same named assistant.
            st.markdown('<div class="qa-question">Retention Intelligence responds</div>', unsafe_allow_html=True)
            components.agent_response_block(response)

st.write("")
caveats.render_caveats(["hrr"])
