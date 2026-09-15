import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from lib import caveats, data, theme

theme.apply_page_style()

theme.page_header(
    "CUSTOMER 360",
    "What should we do for this customer?",
    "Search for a customer to open a full intelligence profile -- their risk, their value, why "
    "they're flagged, and the recommended action.",
)

risk_summary = data.safe_load(data.load_risk_summary)
value_analysis = data.safe_load(data.load_value_analysis)
action_plan = data.safe_load(data.load_action_plan)

if "lookup_loaded" not in st.session_state:
    st.session_state["lookup_loaded"] = False

if not st.session_state["lookup_loaded"]:
    st.info(
        "This page reads the full per-customer tables (~971K rows, ~300MB combined) -- every "
        "other page in this app runs on small, pre-aggregated summaries. Loading happens once, "
        "on demand, and is cached for the rest of this session."
    )
    if st.button("Load customer data", type="primary"):
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
# Find -- a single compact control row, not a form that dominates the page. Labels are
# collapsed (placeholders carry the meaning) so this reads as one search bar, not four stacked
# form fields.
# ---------------------------------------------------------------------------
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

theme.divider()

MAX_DISPLAY_ROWS = 500
display_cols = ["msno", "segment", "risk_tier", "risk_score_full", "value_tier", "total_revenue", "tenure_days_at_cutoff", "latest_is_auto_renew"]
display_df = filtered[display_cols].head(MAX_DISPLAY_ROWS).reset_index(drop=True)

# Table view only -- total_revenue stays untouched in display_df (used below for the profile
# panel) and in the raw `filtered` frame used by the download button.
table_view = display_df.copy()
table_view["total_revenue"] = theme.to_inr(table_view["total_revenue"])

if len(filtered) == 0:
    theme.empty_state(
        "NO MATCHES",
        "No customer matches these filters",
        "Try a shorter Customer ID, or clear a filter above -- Segment, Risk tier, Value tier, "
        "or the Historical Realized Revenue range in More filters.",
    )
    st.stop()
elif len(filtered) > MAX_DISPLAY_ROWS:
    st.caption(f"{len(filtered):,} matches -- showing the first {MAX_DISPLAY_ROWS:,}. Refine the search or filters, or download all matches below. Select a row to open a profile.")
else:
    st.caption(f"{len(filtered):,} matching customer{'s' if len(filtered) != 1 else ''}. Select a row to open a profile.")

event = st.dataframe(
    table_view,
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "msno": st.column_config.TextColumn("Customer ID"),
        "segment": st.column_config.TextColumn("Segment"),
        "risk_tier": st.column_config.TextColumn("Risk"),
        "risk_score_full": st.column_config.ProgressColumn("Model Risk Score", width="medium", min_value=0.0, max_value=1.0, format="%.2f"),
        "value_tier": st.column_config.TextColumn("Value"),
        "total_revenue": st.column_config.NumberColumn("HRR (₹)", format="₹%d"),
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

# ---------------------------------------------------------------------------
# Profile -- a CRM intelligence profile, readable in about 10-15 seconds: who, how at-risk,
# what to do, why, what to avoid -- in that order, nothing to scroll past to get there.
# ---------------------------------------------------------------------------
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
cust = display_df.iloc[row_idx]
full = filtered.iloc[row_idx]  # same row, full column set (behavioral features for the profile)
segment = cust["segment"]
objective = OBJECTIVE_BY_SEGMENT.get(segment, "No specific action defined for this segment.")
intensity = INTENSITY_BY_SEGMENT.get(segment, "—")
avoid = data.AVOID_BY_SEGMENT.get(segment)

st.write("")
theme.divider()

theme.eyebrow("Customer profile")
st.markdown(
    f'<div class="profile-panel" style="font-size:2rem; font-weight:800; color:{theme.COLORS["navy"]}; '
    f'letter-spacing:-0.015em; margin-bottom:0.6rem; word-break:break-all;">{cust["msno"]}</div>',
    unsafe_allow_html=True,
)
badges = " ".join([
    theme.badge(cust["risk_tier"] + " risk", theme.RISK_COLOR_MAP.get(cust["risk_tier"], theme.COLORS["neutral"])),
    theme.badge(cust["value_tier"] + " value", theme.COLORS["navy_soft"]),
    theme.badge(segment, theme.COLORS["accent"]),
])
st.markdown(badges, unsafe_allow_html=True)
st.write("")

theme.stat_row([
    {"label": "Estimated Churn Probability", "value": f"{full['calibrated_probability'] * 100:.0f}%" if pd.notna(full["calibrated_probability"]) else "—"},
    {"label": "Model Risk Score", "value": f"{cust['risk_score_full']:.2f}"},
    {"label": "Historical Realized Revenue", "value": theme.fmt_currency(cust["total_revenue"]) if pd.notna(cust["total_revenue"]) else "—"},
    {"label": "Tenure", "value": f"{full['tenure_days_at_cutoff']:.0f} days" if pd.notna(full["tenure_days_at_cutoff"]) else "—"},
])
st.caption(
    "Model Risk Score ranks customers for prioritization -- it is not a probability. "
    "Estimated Churn Probability is a separately calibrated figure and can be read as one "
    "(see Methodology below). Historical Realized Revenue is money already collected, not a "
    "forecast of future value."
)
st.page_link("pages/retention_copilot.py", label="Ask Retention Intelligence about this customer →", icon=None)

left, right = st.columns([3, 2], gap="large")

with left:
    theme.eyebrow("Evidence")
    theme.section("Why is this customer at risk?")

    factors = []
    if full["latest_is_auto_renew"] == 0:
        factors.append(f"Auto-renew is off, while {POP_AUTO_RENEW * 100:.0f}% of the base has it on -- the model's single strongest driver (see Priority Customers).")
    if full["days_since_last_txn"] > POP_DAYS_SINCE * 1.5:
        factors.append(f"Last transaction was {full['days_since_last_txn']:.0f} days ago, well above the {POP_DAYS_SINCE:.0f}-day average.")
    if full["cancel_rate"] > POP_CANCEL * 1.5:
        factors.append(f"Cancellation rate ({full['cancel_rate'] * 100:.1f}%) is well above the {POP_CANCEL * 100:.1f}% base average.")
    if not factors:
        factors.append("No individual behavioral flag stands out sharply from the population average -- the Model Risk Score reflects a combination of smaller signals, not one dominant factor.")
    st.markdown("\n".join(f"- {f}" for f in factors))
    st.caption("Observed deviations from the population, not proven causes.")

    with st.expander("Behavior vs. the population (detail)"):
        behavior_rows = pd.DataFrame([
            {"Indicator": "Auto-renew (share of transactions)", "This customer": f"{full['auto_renew_pct'] * 100:.0f}%", "Population average": f"{POP_AUTO_RENEW * 100:.0f}%"},
            {"Indicator": "Tenure (days)", "This customer": f"{full['tenure_days_at_cutoff']:.0f}" if pd.notna(full["tenure_days_at_cutoff"]) else "not available", "Population average": f"{POP_TENURE:.0f} (median)"},
            {"Indicator": "Total transactions", "This customer": f"{full['total_transactions']:.0f}", "Population average": f"{POP_TXN:.1f}"},
            {"Indicator": "Cancellation rate", "This customer": f"{full['cancel_rate'] * 100:.1f}%", "Population average": f"{POP_CANCEL * 100:.1f}%"},
            {"Indicator": "Discount rate", "This customer": f"{full['discount_rate'] * 100:.1f}%", "Population average": f"{POP_DISCOUNT * 100:.1f}%"},
            {"Indicator": "Days since last transaction", "This customer": f"{full['days_since_last_txn']:.0f}", "Population average": f"{POP_DAYS_SINCE:.0f}"},
        ])
        st.dataframe(behavior_rows, hide_index=True, width="stretch")

with right:
    theme.eyebrow("What to do")
    theme.section("What should we do?")
    st.markdown(theme.badge(intensity, theme.intensity_color(intensity)), unsafe_allow_html=True)
    st.markdown(f"<p style='margin-top:0.6rem;'>{objective}</p>", unsafe_allow_html=True)
    st.caption(f"Segment-level treatment for {segment}, from the marketing action plan.")

    st.write("")
    st.markdown('<div class="section-title" style="font-size:0.92rem;">Why this action?</div>', unsafe_allow_html=True)
    why_action = data.SHORT_WHY_BY_SEGMENT.get(segment, "Elevated model risk for this segment, per the existing risk x value framework.")
    st.markdown(f"<p style='color:{theme.COLORS['text_muted']}; font-size:0.9rem;'>{why_action}</p>", unsafe_allow_html=True)
    st.caption("From the validated segment/action framework -- an observed association, not a causal guarantee.")

    if avoid:
        st.write("")
        st.markdown('<div class="section-title" style="font-size:0.92rem;">What should we avoid?</div>', unsafe_allow_html=True)
        st.markdown(f"<p style='color:{theme.COLORS['text_muted']}; font-size:0.9rem;'>{avoid}</p>", unsafe_allow_html=True)
        st.caption("The same framework's recommendation, stated as what not to default to -- not a new claim.")

st.write("")
caveats.render_caveats(["calibration", "hrr"], risk_summary=risk_summary, value_analysis=value_analysis)
