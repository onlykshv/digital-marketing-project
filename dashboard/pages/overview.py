import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.graph_objects as go
import streamlit as st

from lib import caveats, components, data, theme

theme.apply_page_style()

risk_summary = data.safe_load(data.load_risk_summary)
action_plan = data.safe_load(data.load_action_plan)
value_by_tier = data.safe_load(data.load_value_by_tier)
risk_value_matrix = data.safe_load(data.load_risk_value_matrix)
temporal_results = data.safe_load(data.load_temporal_results)

tiers_by_name = {t["tier"]: t for t in risk_summary["risk_tiers"]}
total_hrr = data.total_realized_revenue(value_by_tier)
intervention_needed = data.customers_requiring_intervention(action_plan)
opportunities = data.priority_opportunities(action_plan, top_n=1)
top_opportunity = opportunities.iloc[0]
champions = action_plan[action_plan["priority_group"] == "Engaged Low-Risk (Champions)"].iloc[0]
stable = action_plan[action_plan["priority_group"] == "Stable / Monitor"].iloc[0]

# ---------------------------------------------------------------------------
# WHERE SHOULD KKBOX ACT? -- the one thing this page needs to say in five seconds.
# ---------------------------------------------------------------------------
theme.hero_header(
    "OVERVIEW · WHERE SHOULD KKBOX ACT?",
    f'<span class="accent-num">{theme.fmt_count(intervention_needed)}</span> customers need attention',
    f"{theme.fmt_count(tiers_by_name['High']['n_customers'])} of them are in the highest-risk tier, "
    f"out of {theme.fmt_count(risk_summary['n_customers_scored'])} customers scored.",
)

# P1-13: the AI assistant is this product's headline differentiator, but until now nothing on the
# page a manager lands on first said so -- the only route into Retention Intelligence lived below
# the priority-zone chart, requiring a scroll before a first-time visitor could discover it. This
# is the SAME "Ask Retention Intelligence about {segment}" handoff already used further down this
# page (same session-state mechanism, same real top_opportunity data, not a new claim or a new
# destination) -- only its position moved into the hero itself, so the hero workflow is reachable
# without scrolling, on the very number the hero just stated.
if st.button(
    f"Ask Retention Intelligence: why does {top_opportunity['priority_group']} need attention? →",
    key="hero_ask_ri", type="primary",
):
    st.session_state["copilot_segment_choice"] = top_opportunity["priority_group"]
    st.switch_page("pages/retention_copilot.py")

theme.insight(
    "Instead of treating the entire customer base equally, Retention Intelligence narrows the "
    "retention team's attention to customers with elevated churn risk -- and further, to the "
    "ones where that risk is worth spending on."
)

theme.stat_row([
    {"label": "Customers Scored", "value": theme.fmt_count(risk_summary["n_customers_scored"])},
    {"label": "Overall Churn Rate", "value": theme.fmt_pct(risk_summary["actual_churn_rate"] * 100)},
    {"label": "Realized Revenue (Base)", "value": theme.fmt_currency(total_hrr)},
    {"label": "Model Validated On", "value": "Future data (temporal holdout)"},
])

theme.section("Who is at risk, and what is at stake", "Every risk x value combination in the base. Size = number of customers.")
theme.field_status_badge("Priority zone identified — high risk × high value")

tiers_order = ["Low", "Medium", "High"]
points = []
for rt in tiers_order:
    row = risk_value_matrix.loc[rt]
    for vt in tiers_order:
        points.append({
            "risk_tier": rt, "value_tier": vt,
            "churn_rate": row[f"churn_rate_pct_{vt}"],
            "avg_hrr": theme.to_inr(row[f"avg_hrr_{vt}"]),
            "n": row[f"n_{vt}"],
        })

x_max = max(p["churn_rate"] for p in points)
y_max = max(p["avg_hrr"] for p in points)
priority_point = next(p for p in points if p["risk_tier"] == "High" and p["value_tier"] == "High")

fig = go.Figure()

# The "field" backdrop: heat concentrated where risk and value coincide, fading outward --
# a mood layer only. Every number the customer can read still comes from the markers/hover
# below, not from this shading.
for scale, alpha in [(0.60, 0.05), (0.42, 0.08), (0.26, 0.13)]:
    fig.add_shape(
        type="circle", xref="x", yref="y", layer="below", line_width=0,
        fillcolor=f"rgba(201,74,74,{alpha})",
        x0=priority_point["churn_rate"] - x_max * scale, x1=priority_point["churn_rate"] + x_max * 0.12,
        y0=priority_point["avg_hrr"] - y_max * scale, y1=priority_point["avg_hrr"] + y_max * 0.12,
    )
# A halo ring around the one point that is genuinely both high-risk and high-value.
fig.add_shape(
    type="circle", xref="x", yref="y", layer="below", line=dict(width=2, color="rgba(201,74,74,0.35)"),
    fillcolor="rgba(0,0,0,0)",
    x0=priority_point["churn_rate"] - x_max * 0.10, x1=priority_point["churn_rate"] + x_max * 0.10,
    y0=priority_point["avg_hrr"] - y_max * 0.10, y1=priority_point["avg_hrr"] + y_max * 0.10,
)

for rt in tiers_order:
    pts = [p for p in points if p["risk_tier"] == rt]
    fig.add_trace(go.Scatter(
        x=[p["churn_rate"] for p in pts],
        y=[p["avg_hrr"] for p in pts],
        mode="markers",
        name=f"{rt} risk",
        marker=dict(
            size=[max(20, min(80, (p["n"] ** 0.5) / 6)) for p in pts],
            color=theme.RISK_COLOR_MAP[rt],
            opacity=0.82,
            line=dict(width=1, color="white"),
        ),
        customdata=[[p["value_tier"], p["n"]] for p in pts],
        hovertemplate=(
            f"<b>{rt} risk, %{{customdata[0]}} value</b><br>"
            "Churn rate: %{x:.1f}%<br>Avg. HRR: ₹%{y:,.0f}<br>Customers: %{customdata[1]:,}<extra></extra>"
        ),
    ))
fig.add_annotation(
    x=priority_point["churn_rate"], y=priority_point["avg_hrr"] + y_max * 0.14,
    text="<b>PRIORITY ZONE</b>", showarrow=False,
    font=dict(size=12, color=theme.COLORS["high"]), xanchor="center", yanchor="bottom",
)
theme.chart_layout(
    fig, height=560, xaxis_title="Churn rate (%)", yaxis_title="Avg. realized revenue per customer (₹)",
    xaxis=dict(range=[-x_max * 0.06, x_max * 1.25]), yaxis=dict(range=[-y_max * 0.06, y_max * 1.22]),
)
st.plotly_chart(fig, width="stretch", config=theme.PLOTLY_CONFIG)

theme.insight(
    "High risk and high value rarely coincide at scale -- most realized revenue sits with "
    "<b>Low-risk</b> customers. The small High-risk/High-value pocket in the top-right is worth "
    "individual attention; everything else is handled at the segment level below."
)

st.write("")
left, right = st.columns([3, 2], gap="large")
with left:
    components.recommendation_block(
        eyebrow="THE BIGGEST ACTIONABLE OPPORTUNITY",
        title=top_opportunity["priority_group"],
        stat_html=(
            f"<b>{theme.fmt_count(top_opportunity['n_customers'])}</b> customers &middot; "
            f"<b style='color:{theme.COLORS['high']};'>{top_opportunity['churn_rate_pct']:.1f}%</b> churn &middot; "
            f"<b>{theme.fmt_currency(top_opportunity['total_HRR'])}</b> realized revenue"
        ),
        objective=top_opportunity["marketing_objective"],
        intensity=top_opportunity["intervention_intensity"],
        why=data.SHORT_WHY_BY_SEGMENT.get(top_opportunity["priority_group"], "Elevated model risk for this segment."),
        rationale=top_opportunity["rationale"],
        size="large",
    )
    if st.button(f"Ask Retention Intelligence about {top_opportunity['priority_group']} →", key="ask_ri_overview"):
        st.session_state["copilot_segment_choice"] = top_opportunity["priority_group"]
        st.switch_page("pages/retention_copilot.py")
    # P1-08: this is the page's one "portfolio signal" -- the biggest actionable opportunity --
    # so the link into the work queue must actually carry that segment as a starting filter,
    # not drop the manager into the generic default view. Same `pending_filter` mechanism
    # priority_customers.py already consumes (from the Retention Intelligence search-results and
    # segment deep links) -- no new session-state convention, no new filtering logic.
    if st.button(f"View {top_opportunity['priority_group']} customers in Priority Customers →", key="view_priority_customers_overview"):
        st.session_state["pending_filter"] = {"segment": [top_opportunity["priority_group"]]}
        st.switch_page("pages/priority_customers.py")

with right:
    components.secondary_story(
        eyebrow="PROTECT THE WINNERS -- GROWTH, NOT RISK",
        title=champions["priority_group"],
        stat_html=(
            f"<b>{theme.fmt_count(champions['n_customers'])}</b> customers &middot; "
            f"<b style='color:{theme.COLORS['low']};'>{champions['churn_rate_pct']:.1f}%</b> churn &middot; "
            f"<b>{theme.fmt_currency(champions['total_HRR'])}</b> realized revenue"
        ),
        objective=champions["marketing_objective"],
        color=theme.COLORS["low"],
    )
    theme.recede(
        f"Separately, {theme.fmt_count(stable['n_customers'])} customers ({stable['pct_of_base']:.0f}% of the "
        f"base) are Stable / Monitor -- {stable['churn_rate_pct']:.1f}% churn, no action recommended."
    )

st.write("")
caveats.render_caveats(
    ["temporal", "calibration", "reusability"], risk_summary=risk_summary, temporal_results=temporal_results,
)
