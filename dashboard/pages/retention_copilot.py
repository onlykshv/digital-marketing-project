import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from lib import agent, caveats, components, copilot_data, data, llm_provider, theme

theme.apply_page_style()

theme.page_header(
    "RETENTION OPERATIONS ASSISTANT",
    "Retention Intelligence",
    "Ask the system who needs attention, why, and what to do next. Every answer is grounded in "
    "the project's validated risk model, segmentation, and action framework.",
)

# A grounding indicator belongs directly under the header -- "what am I currently focused on"
# (the whole book of business, a segment, or one customer) is the first thing a manager should
# see, before any data-loading mechanics or suggested questions. Its actual content depends on
# `cust_ctx`/`segment_choice`, which aren't resolved until after the search/segment controls
# render further down this script -- so, exactly like the empty-state slot below, this reserves
# the visual position now and is filled in once that context is known.
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

if "lookup_loaded" not in st.session_state:
    st.session_state["lookup_loaded"] = False

customer_df = None
if st.session_state["lookup_loaded"]:
    customer_df = data.safe_load(data.load_customer_lookup_data)
else:
    # A quiet system note, not a technical loading screen -- this is infrastructure the manager
    # doesn't need to think about, not the product experience itself. A plain (not primary)
    # button, sized and weighted like any other secondary control on this page.
    note_col, btn_col = st.columns([3, 1])
    with note_col:
        theme.recede(
            "Customer-level questions need the full customer table loaded once for this "
            "session. Segment and business-wide questions work immediately."
        )
    with btn_col:
        if st.button("Load customer data"):
            st.session_state["lookup_loaded"] = True
            st.rerun()

# ---------------------------------------------------------------------------
# Context -- who/what the assistant is currently grounded to. Same underlying mechanism as
# always (the shared `cust360_search` session key Priority Customers and Customer 360 already
# use, and a segment picker), presented as a compact control row rather than a dominant search
# form. A customer selected on Priority Customers, or "Ask Retention Intelligence" clicked from
# a Customer 360 profile, arrives here automatically -- no re-searching required.
# ---------------------------------------------------------------------------
c1, c2 = st.columns([2, 1])
with c1:
    search = st.text_input(
        "Search by Customer ID", placeholder="Focus on a customer by ID (msno)…",
        value=st.session_state.get("cust360_search", ""),
        key="copilot_search_widget", label_visibility="collapsed",
    )
    st.session_state["cust360_search"] = search
with c2:
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
# new context.
_context_id = f"customer:{cust_ctx['msno']}" if cust_ctx else (f"segment:{segment_choice}" if segment_choice else "general")
if st.session_state.get("copilot_context_id") != _context_id:
    st.session_state.pop("copilot_asked", None)
    st.session_state["copilot_context_id"] = _context_id

# Fill the grounding slot reserved right under the header (see `context_slot` above) -- this is
# "WHAT IS HAPPENING / WHO IS IN FOCUS", always visible, never blank: the whole scored base, one
# segment, or one customer. Customer 360 (one customer) and Priority Customers (a segment's real
# customers) are one click away from whichever focus is currently active -- the same "take
# action" link pattern, applied consistently instead of only existing for the customer case.
with context_slot:
    if cust_ctx:
        badges = " ".join([
            theme.badge(cust_ctx["risk_tier"] + " risk", theme.RISK_COLOR_MAP.get(cust_ctx["risk_tier"], theme.COLORS["neutral"])),
            theme.badge(cust_ctx["value_tier"] + " value", theme.COLORS["navy_soft"]),
            theme.badge(cust_ctx["segment"], theme.COLORS["accent"]),
        ])
        theme.context_strip(
            f"Analysing customer <b>{cust_ctx['msno']}</b> &nbsp; {badges}",
            dot_color=theme.RISK_COLOR_MAP.get(cust_ctx["risk_tier"], theme.COLORS["neutral"]),
        )
        st.page_link("pages/customer_360.py", label="Open full profile in Customer 360 →")
    elif segment_choice:
        theme.context_strip(f"Segment in focus: <b>{segment_choice}</b>", dot_color=theme.COLORS["accent"])
        if st.button(f"View {segment_choice} customers in Priority Customers →", key="ri_segment_to_priority"):
            st.session_state["pending_filter"] = {"segment": [segment_choice]}
            st.switch_page("pages/priority_customers.py")
    else:
        _tiers_by_name = {t["tier"]: t for t in risk_summary["risk_tiers"]}
        theme.context_strip(
            f"Grounded in the full scored base &nbsp; <b>{theme.fmt_count(risk_summary['n_customers_scored'])}</b> customers "
            f"&middot; <b>{theme.fmt_count(_tiers_by_name['High']['n_customers'])}</b> High risk "
            f"&middot; <b>{theme.fmt_pct(risk_summary['actual_churn_rate'] * 100)}</b> churn",
            dot_color=theme.COLORS["neutral"],
        )

st.write("")

# ---------------------------------------------------------------------------
# Suggested prompts -- adapt to context, but always example-only (never hard-coded answers).
#
# General mode (no customer/segment focus) is grouped into the same two steps as the start of
# the intended manager flow -- "what is happening" (business-wide questions) and "who needs
# attention" (a customer list) -- instead of one flat, unordered grid. It deliberately does NOT
# offer "Why is this customer at risk?" / "What should we do about this customer?" as buttons
# here: those questions are genuinely about one customer, and with none selected they can only
# ever produce a "please select a customer" guidance message (agent.py still answers that
# honestly if asked -- this only changes what's suggested as a first click, not what's possible).
# Customer mode and segment mode are unchanged -- both were already ordered why -> what-to-do,
# already work correctly with no context gaps, so neither needed to change.
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

# The empty-state hero must visually appear ABOVE the suggested-prompt buttons (it's the
# centerpiece), but whether to show it at all depends on whether a button click on THIS SAME
# render just set `copilot_asked` -- which only happens once the button loop below runs. A
# `st.container()` reserves this position in the layout now; its content is decided (and
# written into it) after the buttons have had a chance to act, so a click and its resulting
# answer never appear underneath a stale "nothing asked yet" hero in the same render.
empty_state_slot = st.container()

if suggested is not None:
    st.markdown('<div class="qa-question">Ask</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    for i, q in enumerate(suggested):
        if cols[i % 3].button(q, width="stretch", key=f"suggested_{i}"):
            st.session_state["copilot_asked"] = q
else:
    btn_idx = 0
    for group_label, group_qs in general_groups:
        theme.eyebrow(group_label)
        cols = st.columns(len(group_qs))
        for i, q in enumerate(group_qs):
            if cols[i].button(q, width="stretch", key=f"suggested_{btn_idx}"):
                st.session_state["copilot_asked"] = q
            btn_idx += 1
    theme.recede(
        "Search for a customer above, or pick a segment, to ask why a specific one is at risk "
        "or what to do about it."
    )

free_q = st.text_input(
    "Ask a question…", key="copilot_freetext", label_visibility="collapsed",
    placeholder="Ask about this customer, this segment, or the business as a whole, and press Enter…",
)
if free_q:
    st.session_state["copilot_asked"] = free_q

has_context_or_history = bool(cust_ctx) or bool(segment_choice) or bool(st.session_state.get("copilot_asked"))
if not has_context_or_history:
    # First-open empty state -- the visual centerpiece, not a "no data" dead end.
    with empty_state_slot:
        theme.empty_state(
            "RETENTION INTELLIGENCE",
            "Ask a question about customers, risk, value, or retention actions.",
            "Search for a customer or pick a segment above to focus the assistant, or ask a "
            "general question below. Every answer is grounded in the project's actual data -- "
            "nothing here can invent a customer, a number, or a result.",
        )

# ---------------------------------------------------------------------------
# Answer -- routed entirely through the agent orchestrator. Grounded in agent_tools.py either
# way: via LLM tool-calling when a provider is configured, or via the deterministic fallback
# (which is the existing Retention Copilot's own answer engine, called directly) when it isn't.
# ---------------------------------------------------------------------------
asked = st.session_state.get("copilot_asked")
if asked:
    ctx = agent.AgentContext(
        action_plan=action_plan, segment_summary=segment_summary, value_by_segment=value_by_segment,
        risk_summary=risk_summary, value_by_tier=value_by_tier, risk_value_matrix=risk_value_matrix,
        shap_df=shap_df, customer_df=customer_df,
        selected_customer_id=cust_ctx["msno"] if cust_ctx else None,
        selected_segment=segment_choice,
    )
    with st.spinner("Retention Intelligence is consulting the retention model…"):
        response = agent.ask(asked, ctx)

    st.markdown('<div class="qa-question">You asked</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="qa-question-text profile-panel">"{asked}"</div>', unsafe_allow_html=True)
    # A restrained, consistent name treatment for every answer -- reuses the exact "You asked"
    # label styling (no new CSS), so the identity cue costs nothing extra visually while making
    # every answer legible as coming from the same named assistant, not an anonymous response box.
    st.markdown('<div class="qa-question">Retention Intelligence responds</div>', unsafe_allow_html=True)
    components.agent_response_block(response)

st.write("")
caveats.render_caveats(["hrr"])
