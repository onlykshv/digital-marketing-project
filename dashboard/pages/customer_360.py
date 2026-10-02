import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from lib import caveats, data, theme

theme.apply_page_style()

theme.masthead(
    "pages/customer_360.py", "Customer 360", "What should we do for this customer?",
    "One customer at a glance -- how at-risk they are, why, and what to do. Search for a customer, "
    "or open one from Priority Customers.",
)

risk_summary = data.safe_load(data.load_risk_summary)
value_analysis = data.safe_load(data.load_value_analysis)
action_plan = data.safe_load(data.load_action_plan)

if "lookup_loaded" not in st.session_state:
    st.session_state["lookup_loaded"] = False

if not st.session_state["lookup_loaded"]:
    st.write("")
    with st.container(key="gate_c360"):
        g1, g2 = st.columns([4, 1.1], vertical_alignment="center")
        with g1:
            st.markdown(
                '<div class="ri-gate"><span class="k">Customer table</span><p>This page reads the full '
                "per-customer tables (~971K rows, ~300MB combined) -- every other page in this app runs on "
                "small, pre-aggregated summaries. Loading happens once, on demand, and is cached for the rest "
                "of this session.</p></div>",
                unsafe_allow_html=True,
            )
        with g2:
            if st.button("Load customer data", type="primary", width="stretch"):
                st.session_state["lookup_loaded"] = True
                st.rerun()
    st.stop()

df = data.safe_load(data.load_customer_lookup_data)

# Population baselines for the comparison shown in a customer's detail panel -- plain
# aggregates of columns already loaded above, computed once.
POP_AUTO_RENEW = df["latest_is_auto_renew"].mean()
POP_TENURE = df["tenure_days_at_cutoff"].median()
POP_TXN = df["total_transactions"].mean()
POP_CANCEL = df["cancel_rate"].mean()
POP_DISCOUNT = df["discount_rate"].mean()
POP_DAYS_SINCE = df["days_since_last_txn"].mean()
OBJECTIVE_BY_SEGMENT = dict(zip(action_plan["priority_group"], action_plan["marketing_objective"]))
INTENSITY_BY_SEGMENT = dict(zip(action_plan["priority_group"], action_plan["intervention_intensity"]))

# ---------------------------------------------------------------------------
# Find -- one compact control row. A customer handed over from Priority Customers or Retention
# Intelligence arrives already in the search box.
# ---------------------------------------------------------------------------
st.write("")
sc1, sc2, sc3, sc4 = st.columns([2.3, 1, 1, 1])
with sc1:
    search = st.text_input(
        "Search by Customer ID", placeholder="Search by customer ID (msno)…",
        value=st.session_state.get("cust360_search", ""),
        key="cust360_search_widget", label_visibility="collapsed",
    )
    st.session_state["cust360_search"] = search
with sc2:
    segment_choices = st.multiselect(
        "Segment", sorted(df["segment"].cat.categories.tolist()),
        placeholder="Segment", label_visibility="collapsed",
    )
with sc3:
    risk_choices = st.multiselect(
        "Risk tier", ["Low", "Medium", "High"], placeholder="Risk tier", label_visibility="collapsed",
    )
with sc4:
    value_choices = st.multiselect(
        "Value tier", sorted(df["value_tier"].cat.categories.tolist()),
        placeholder="Value tier", label_visibility="collapsed",
    )

with st.expander("More filters"):
    hrr_max = float(df["total_revenue"].max(skipna=True))
    hrr_max_inr = theme.to_inr(hrr_max)
    hrr_range_inr = st.slider("Historical Realized Revenue (₹)", 0.0, hrr_max_inr, (0.0, hrr_max_inr))
    hrr_range = (theme.from_inr(hrr_range_inr[0]), theme.from_inr(hrr_range_inr[1]))

has_query = bool(search) or bool(segment_choices) or bool(risk_choices) or bool(value_choices) or hrr_range_inr != (0.0, hrr_max_inr)

if not has_query:
    theme.empty_state(
        "SEARCH FOR A CUSTOMER",
        "Find a customer to open their profile",
        f"Enter a Customer ID above, or set a Segment, Risk tier, or Value tier filter, to bring "
        f"up a result list from {theme.fmt_count(len(df))} customers in the base. A customer "
        "selected on Priority Customers opens here automatically.",
    )
    st.stop()

filtered = df
if search:
    filtered = filtered[filtered["msno"].str.contains(search, case=False, na=False, regex=False)]
if segment_choices:
    filtered = filtered[filtered["segment"].isin(segment_choices)]
if risk_choices:
    filtered = filtered[filtered["risk_tier"].isin(risk_choices)]
if value_choices:
    filtered = filtered[filtered["value_tier"].isin(value_choices)]
filtered = filtered[filtered["total_revenue"].between(*hrr_range) | filtered["total_revenue"].isna()]

MAX_DISPLAY_ROWS = 500
display_cols = ["msno", "segment", "risk_tier", "risk_score_full", "value_tier", "total_revenue", "tenure_days_at_cutoff", "latest_is_auto_renew"]
display_df = filtered[display_cols].head(MAX_DISPLAY_ROWS).reset_index(drop=True)

if len(filtered) == 0:
    theme.empty_state(
        "NO MATCHES",
        "No customer matches these filters",
        "Try a shorter Customer ID, or clear a filter above -- Segment, Risk tier, Value tier, "
        "or the Historical Realized Revenue range in More filters.",
    )
    st.stop()

# Exactly one match (the normal case when a customer is handed over from Priority Customers or
# Retention Intelligence) opens the profile directly -- there is nothing to choose between, so a
# selection click would only be friction.
auto_opened = len(filtered) == 1
if auto_opened:
    row_idx = 0
else:
    # Table view only -- total_revenue stays untouched in display_df (used below for the profile
    # panel) and in the raw `filtered` frame used by the download button.
    table_view = display_df.copy()
    table_view["total_revenue"] = theme.to_inr(table_view["total_revenue"])
    if len(filtered) > MAX_DISPLAY_ROWS:
        st.caption(f"{len(filtered):,} matches -- showing the first {MAX_DISPLAY_ROWS:,}. Refine the search or filters, or download all matches below. Select a row to open a profile.")
    else:
        st.caption(f"{len(filtered):,} matching customers. Select a row to open a profile.")

    event = st.dataframe(
        table_view,
        hide_index=True,
        width="stretch",
        height=min(38 + 35 * len(table_view), 360),
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "msno": st.column_config.TextColumn("Customer ID", width=260),
            "segment": st.column_config.TextColumn("Segment"),
            "risk_tier": st.column_config.TextColumn("Risk", width=80),
            "risk_score_full": st.column_config.ProgressColumn("Model Risk Score", width="medium", min_value=0.0, max_value=1.0, format="%.2f"),
            "value_tier": st.column_config.TextColumn("Value", width=80),
            "total_revenue": st.column_config.NumberColumn("HRR (₹)", format="₹%d", help="Historical Realized Revenue -- money already collected, not a forecast."),
            "tenure_days_at_cutoff": st.column_config.NumberColumn("Tenure (days)", format="%d"),
            "latest_is_auto_renew": st.column_config.CheckboxColumn("Auto-renew"),
        },
    )

    st.download_button(
        "Download filtered results (CSV)",
        data=filtered[display_cols].to_csv(index=False).encode("utf-8"),
        file_name="customer_lookup_filtered.csv",
        mime="text/csv",
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if not selected_rows:
        theme.empty_state(
            "SELECT A CUSTOMER",
            "Choose a row above to open a profile",
            "The profile -- risk, value, why they're flagged, and the recommended action -- opens "
            "here once a row is selected.",
        )
        st.stop()
    row_idx = selected_rows[0]

# ---------------------------------------------------------------------------
# Profile -- a customer brief, laid out like a report: the main panel says who this customer is,
# why they are at risk and what to do; the side panel holds the signals behind that, and the model
# figures behind a toggle. Every number is this customer's own row or a plain population aggregate.
# ---------------------------------------------------------------------------
cust = display_df.iloc[row_idx]
full = filtered.iloc[row_idx]  # same row, full column set (behavioral features for the profile)
segment = cust["segment"]
objective = OBJECTIVE_BY_SEGMENT.get(segment, "No specific action defined for this segment.")
intensity = INTENSITY_BY_SEGMENT.get(segment, "—")
avoid = data.AVOID_BY_SEGMENT.get(segment)
risk_tier = str(cust["risk_tier"])

evidence_stats = [
    {"label": "Estimated Churn Probability", "value": f"{full['calibrated_probability'] * 100:.0f}%" if pd.notna(full["calibrated_probability"]) else "—"},
    {"label": "Model Risk Score", "value": f"{cust['risk_score_full']:.2f}"},
    {"label": "Historical Realized Revenue", "value": theme.fmt_currency(cust["total_revenue"]) if pd.notna(cust["total_revenue"]) else "—"},
    {"label": "Tenure", "value": f"{full['tenure_days_at_cutoff']:.0f} days" if pd.notna(full["tenure_days_at_cutoff"]) else "—"},
]
hrr_value = evidence_stats[2]["value"]


def _num(v, fmt: str, suffix: str = "") -> str:
    return f"{v:{fmt}}{suffix}" if pd.notna(v) else "—"


# The flag rules below are exactly the ones this page's evidence list has always used -- no new
# thresholds: auto-renew off; recency or cancellation rate more than 1.5x the base average.
auto_renew = full["latest_is_auto_renew"]
signals = [
    {"label": "Auto-renew (latest)", "value": "—" if pd.isna(auto_renew) else ("On" if auto_renew == 1 else "Off"),
     "base": f"{POP_AUTO_RENEW * 100:.0f}% of the base on", "flag": auto_renew == 0},
    {"label": "Days since last transaction", "value": _num(full["days_since_last_txn"], ".0f"),
     "base": f"base average {POP_DAYS_SINCE:.0f}", "flag": bool(full["days_since_last_txn"] > POP_DAYS_SINCE * 1.5)},
    {"label": "Cancellation rate", "value": _num(full["cancel_rate"] * 100, ".1f", "%"),
     "base": f"base average {POP_CANCEL * 100:.1f}%", "flag": bool(full["cancel_rate"] > POP_CANCEL * 1.5)},
    {"label": "Total transactions", "value": _num(full["total_transactions"], ".0f"),
     "base": f"base average {POP_TXN:.1f}", "flag": False},
]
signal_html = "".join(
    f'<div class="{"flag" if s["flag"] else ""}"><span class="l">{theme.dot(theme.COLORS["high"] if s["flag"] else theme.COLORS["ink_3"])}{s["label"]}</span>'
    f'<span class="v">{s["value"]}<span class="b">{s["base"]}</span></span></div>'
    for s in signals
)

factors = []
if full["latest_is_auto_renew"] == 0:
    factors.append(f"Auto-renew is off, while {POP_AUTO_RENEW * 100:.0f}% of the base has it on -- the model's single strongest driver (see Priority Customers).")
if full["days_since_last_txn"] > POP_DAYS_SINCE * 1.5:
    factors.append(f"Last transaction was {full['days_since_last_txn']:.0f} days ago, well above the {POP_DAYS_SINCE:.0f}-day average.")
if full["cancel_rate"] > POP_CANCEL * 1.5:
    factors.append(f"Cancellation rate ({full['cancel_rate'] * 100:.1f}%) is well above the {POP_CANCEL * 100:.1f}% base average.")
if not factors:
    factors.append("No individual behavioral flag stands out sharply from the population average -- the Model Risk Score reflects a combination of smaller signals, not one dominant factor.")

brief_col, side_col = st.columns([1.6, 1], gap="medium")

# The side panel is filled first: the brief's last element is the Customer 360 -> Retention
# Intelligence page link, so everything else on the profile must already be on the page by then.
with side_col:
    with st.container(key="rp_signals"):
        theme.panel_head("Signals", right="this customer vs. the base")
        st.markdown(f'<div class="ri-sig">{signal_html}</div>', unsafe_allow_html=True)
    with st.expander("Model details"):
        theme.stat_row(evidence_stats)
        st.caption(
            "Model Risk Score ranks customers for prioritization -- it is not a probability. "
            "Estimated Churn Probability is a separately calibrated figure and can be read as one "
            "(see Methodology below). Historical Realized Revenue is money already collected, not a "
            "forecast of future value."
        )
    with st.expander("Behavior vs. the population (detail)"):
        behavior_rows = pd.DataFrame([
            {"Indicator": "Auto-renew (share of transactions)", "This customer": _num(full["auto_renew_pct"] * 100, ".0f", "%"), "Population average": f"{POP_AUTO_RENEW * 100:.0f}%"},
            {"Indicator": "Tenure (days)", "This customer": f"{full['tenure_days_at_cutoff']:.0f}" if pd.notna(full["tenure_days_at_cutoff"]) else "not available", "Population average": f"{POP_TENURE:.0f} (median)"},
            {"Indicator": "Total transactions", "This customer": _num(full["total_transactions"], ".0f"), "Population average": f"{POP_TXN:.1f}"},
            {"Indicator": "Cancellation rate", "This customer": _num(full["cancel_rate"] * 100, ".1f", "%"), "Population average": f"{POP_CANCEL * 100:.1f}%"},
            {"Indicator": "Discount rate", "This customer": _num(full["discount_rate"] * 100, ".1f", "%"), "Population average": f"{POP_DISCOUNT * 100:.1f}%"},
            {"Indicator": "Days since last transaction", "This customer": _num(full["days_since_last_txn"], ".0f"), "Population average": f"{POP_DAYS_SINCE:.0f}"},
        ])
        st.dataframe(behavior_rows, hide_index=True, width="stretch")

with brief_col:
    with st.container(key="rp_brief"):
        origin = "Opened automatically &mdash; the only customer matching this search" if auto_opened else "Customer profile"
        theme.panel_head("Customer brief", dot=theme.RISK_COLOR_MAP.get(risk_tier), right=origin)
        why_action = data.SHORT_WHY_BY_SEGMENT.get(segment, "Elevated model risk for this segment, per the existing risk x value framework.")
        # The recommendation is inherited from the customer's segment in the action framework --
        # labelled as such, so it is never read as a bespoke judgement about this one customer.
        gap_html = (
            '<div class="ri-gap-note"><span class="k">Label gap</span><span>This customer is in the '
            f"{risk_tier} risk tier but carries the Stable / Monitor label: at-risk customers who match none of "
            "the named segment rules fall into that label in the per-customer segment file, so this is that "
            "label's playbook, not a risk-based one.</span></div>"
        ) if data.segment_label_gap(risk_tier, segment) else ""
        theme.md(
            f"""<div class="ri-profile ri-id">
                <div class="who">{theme.esc(cust['msno'])}</div>
                <div>{theme.risk_badge(risk_tier)} &nbsp;{theme.value_chip(cust['value_tier'])}{theme.badge(segment, theme.COLORS['ink_3'])}</div>
            </div>
            <div class="ri-kv" style="margin-top:0.5rem;"><div><span class="k">Revenue to date</span><span class="v">{hrr_value}</span></div></div>"""
        )
        theme.section("Why is this customer at risk?")
        st.markdown('<ul class="ri-why">' + "".join(f"<li>{f}</li>" for f in factors) + "</ul>", unsafe_allow_html=True)
        st.caption("Observed deviations from the population, not proven causes.")
        avoid_html = f'<div class="ri-act-avoid"><b>Avoid:</b> {avoid}</div>' if avoid else ""
        theme.md(
            f"""<div class="rp-h" style="margin-top:0.4rem;"><span class="t">Action</span><span class="r">{intensity}</span></div>
            <div class="ri-inherit"><div class="k">Segment playbook &middot; {segment}</div></div>
            <div class="ri-act-verb">{data.SHORT_ACTION_BY_SEGMENT.get(segment, "Standard outreach")}</div>
            <div class="ri-act-obj">{objective}</div>
            <div class="ri-act-avoid"><b>Why this action:</b> {why_action}</div>
            {avoid_html}
            {gap_html}"""
        )
        st.page_link("pages/retention_copilot.py", label="Ask Retention Intelligence about this customer →", icon=None)

st.write("")
caveats.render_caveats(["calibration", "hrr"], risk_summary=risk_summary, value_analysis=value_analysis)

