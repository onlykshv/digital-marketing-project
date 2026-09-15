import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.graph_objects as go
import streamlit as st

from lib import caveats, data, theme

theme.apply_page_style()

theme.page_header(
    "CUSTOMER VALUE",
    "Who is worth saving?",
    "Historical Realized Revenue (HRR) across the base -- money already collected, not a "
    "lifetime-value forecast. See the note at the bottom of this page for what that means.",
)

value_analysis = data.safe_load(data.load_value_analysis)
value_by_tier = data.safe_load(data.load_value_by_tier)
value_by_segment = data.safe_load(data.load_value_by_segment)
risk_value_matrix = data.safe_load(data.load_risk_value_matrix)
action_plan = data.safe_load(data.load_action_plan)
risk_summary = data.safe_load(data.load_risk_summary)

total_hrr = data.total_realized_revenue(value_by_tier)
highest = data.highest_value_segment(value_by_segment)
high_risk_exposure = data.high_risk_historical_revenue_exposure(risk_value_matrix)
high_value_n = data.high_value_customer_count(risk_value_matrix)

theme.stat_row([
    {"label": "Total Realized Revenue", "value": theme.fmt_currency(total_hrr)},
    {"label": "Highest-Value Segment", "value": highest["segment"]},
    {"label": "High-Risk Historical Revenue Exposure", "value": theme.fmt_currency(high_risk_exposure)},
    {"label": "High-Value Customers", "value": theme.fmt_count(high_value_n)},
])
st.caption(
    "\"High-Risk Historical Revenue Exposure\" = actual historical revenue already held by "
    "customers in the model's High-risk tier -- not a probability-weighted expected loss. It is "
    "based on Model Risk Score, which is not a calibrated probability (see Methodology below)."
)

theme.section("Where revenue concentrates", "Total realized revenue held by each behavioral segment.")

vbs = value_by_segment.sort_values("total_HRR", ascending=True)
# P1-10: previously every non-Champions segment shared one color, so Stable/Monitor (explicitly
# "no action recommended" everywhere else in this product) read as visually equal to the actual
# at-risk segments retention effort should target. Reusing the theme's own existing color
# semantics (accent = actions/priority, per theme.py's own palette comment) rather than inventing
# a new one: Champions keep their existing green, Stable/Monitor is muted to neutral grey, and
# every genuinely actionable at-risk segment gets the accent color. No data or ordering changed.
def _segment_bar_color(segment_name: str) -> str:
    if segment_name == "Engaged Low-Risk (Champions)":
        return theme.COLORS["low"]
    if segment_name == "Stable / Monitor":
        return theme.COLORS["neutral"]
    return theme.COLORS["accent"]


bar_colors = [_segment_bar_color(s) for s in vbs["segment"]]
fig = go.Figure(go.Bar(
    x=theme.to_inr(vbs["total_HRR"]), y=vbs["segment"], orientation="h", marker_color=bar_colors,
    text=[f"{theme.fmt_currency(v)} · {p:.0f}%" for v, p in zip(vbs["total_HRR"], vbs["pct_of_total_HRR"])],
    textposition="outside", cliponaxis=False,
    hovertemplate="%{y}<br>Revenue: ₹%{x:,.0f}<extra></extra>",
))
theme.chart_layout(fig, height=theme.CHART_HEIGHT_LARGE, xaxis_title="Total realized revenue (₹)",
                    xaxis=dict(range=[0, float(theme.to_inr(vbs["total_HRR"]).max()) * 1.18]))
st.plotly_chart(fig, width="stretch", config=theme.PLOTLY_CONFIG)

champions_row = action_plan[action_plan["priority_group"] == "Engaged Low-Risk (Champions)"].iloc[0]
champions_pct_of_hrr = float(
    value_by_segment.set_index("segment").loc["Engaged Low-Risk (Champions)", "pct_of_total_HRR"]
)
theme.insight(
    f"<b>Champions</b> hold the largest share of realized revenue ({champions_pct_of_hrr:.1f}% of the "
    f"total) and the lowest churn rate in the base ({champions_row['churn_rate_pct']:.1f}%). Value and risk "
    f"move in opposite directions here -- exactly the segment retention spend should never target."
)

st.write("")
theme.eyebrow("Value and risk move in opposite directions")
theme.section(
    "Where should retention spend go?",
    "Every risk x value cell in the base. Size = avg. realized revenue per customer. Color = churn rate. "
    "Percent labels = share of the base.",
)

tiers_order = ["Low", "Medium", "High"]
cells = []
for rt in tiers_order:
    for vt in tiers_order:
        cells.append({
            "risk": rt, "value": vt,
            "n": int(risk_value_matrix.loc[rt, f"n_{vt}"]),
            "pct": float(risk_value_matrix.loc[rt, f"pct_{vt}"]),
            "churn": float(risk_value_matrix.loc[rt, f"churn_rate_pct_{vt}"]),
            "avg_hrr": float(theme.to_inr(risk_value_matrix.loc[rt, f"avg_hrr_{vt}"])),
        })
hh = next(c for c in cells if c["risk"] == "High" and c["value"] == "High")

fig2 = go.Figure(go.Scatter(
    x=[c["risk"] for c in cells], y=[c["value"] for c in cells],
    mode="markers+text",
    marker=dict(
        size=[max(34, min(120, (c["avg_hrr"] ** 0.5) / 2.6)) for c in cells],
        color=[c["churn"] for c in cells],
        colorscale=[[0, theme.COLORS["low"]], [0.5, theme.COLORS["medium"]], [1, theme.COLORS["high"]]],
        cmin=0, cmax=100,
        line=dict(width=1, color="white"),
        opacity=0.88,
    ),
    text=[(f"{c['pct']:.0f}%" if c["pct"] >= 1 else "<1%") for c in cells], textposition="middle center",
    textfont=dict(color="white", size=12, family="Inter"),
    customdata=[[c["n"], c["churn"], c["avg_hrr"]] for c in cells],
    hovertemplate="<b>%{x} risk, %{y} value</b><br>%{customdata[0]:,} customers<br>Churn: %{customdata[1]:.1f}%<br>Avg. HRR: ₹%{customdata[2]:,.0f}<extra></extra>",
))
# High-risk/high-value gets the same halo language as Command Center's field -- one visual
# identity for "where risk and value coincide" across the product.
fig2.add_shape(
    type="circle", xref="x", yref="y", layer="below", line=dict(width=2, color="rgba(201,74,74,0.4)"),
    fillcolor="rgba(201,74,74,0.08)", x0=1.65, x1=2.35, y0=1.65, y1=2.35,
)
fig2.update_xaxes(categoryorder="array", categoryarray=tiers_order, title="Risk tier")
fig2.update_yaxes(categoryorder="array", categoryarray=tiers_order, title="Value tier")
theme.chart_layout(fig2, height=440)
st.plotly_chart(fig2, width="stretch", config=theme.PLOTLY_CONFIG)

theme.insight(
    f"<b>High risk + high value</b> ({theme.fmt_count(hh['n'])} customers, {hh['churn']:.1f}% observed churn): "
    f"these customers combine elevated churn risk with meaningful historical realized revenue, making them "
    f"the strongest candidates for high-touch retention. Everywhere else on this field, at least one of "
    f"those two conditions is missing."
)

st.write("")
caveats.render_caveats(
    ["hrr", "revenue_exposure", "causal"], value_analysis=value_analysis, risk_summary=risk_summary,
)
