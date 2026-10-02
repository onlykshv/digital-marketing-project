import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.graph_objects as go
import streamlit as st

from lib import caveats, data, theme

theme.apply_page_style()

theme.masthead(
    "pages/customer_value.py", "Customer value", "Who is worth saving?",
    "Where the risk of leaving meets revenue already earned. Value here is Historical Realized "
    "Revenue -- money already collected, not a forecast.",
)

value_analysis = data.safe_load(data.load_value_analysis)
value_by_tier = data.safe_load(data.load_value_by_tier)
value_by_segment = data.safe_load(data.load_value_by_segment)
risk_value_matrix = data.safe_load(data.load_risk_value_matrix)
action_plan = data.safe_load(data.load_action_plan)
risk_summary = data.safe_load(data.load_risk_summary)

total_hrr = data.total_realized_revenue(value_by_tier)
high_risk_exposure = data.high_risk_historical_revenue_exposure(risk_value_matrix)
high_value_n = data.high_value_customer_count(risk_value_matrix)

theme.kpi_strip([
    {"label": "Revenue to date", "value": theme.fmt_currency(total_hrr), "dot": theme.COLORS["neutral"],
     "note": "Every scored customer, all time."},
    {"label": "Revenue from high-risk customers", "value": theme.fmt_currency(high_risk_exposure), "dot": theme.COLORS["high"],
     "note": "Already earned from High-risk customers -- not a forecast of loss (High-Risk Historical Revenue Exposure)."},
    {"label": "High-value customers", "value": theme.fmt_count(high_value_n), "dot": theme.COLORS["low"],
     "note": "Top value tier, across every risk tier."},
])
st.write("")

# ---------------------------------------------------------------------------
# The risk x value grid: where attention and historical value intersect. Each cell holds just two
# numbers -- customers and observed churn -- tinted by churn; the inspector beside it turns any
# cell into a drill-down into exactly those customers.
# ---------------------------------------------------------------------------
tiers_order = ["Low", "Medium", "High"]
cells = {}
for rt in tiers_order:
    for vt in tiers_order:
        cells[(rt, vt)] = {
            "risk": rt, "value": vt,
            "n": int(risk_value_matrix.loc[rt, f"n_{vt}"]),
            "pct": float(risk_value_matrix.loc[rt, f"pct_{vt}"]),
            "churn": float(risk_value_matrix.loc[rt, f"churn_rate_pct_{vt}"]),
            "avg_hrr_ntd": float(risk_value_matrix.loc[rt, f"avg_hrr_{vt}"]),
        }
hh = cells[("High", "High")]

matrix_col, inspect_col = st.columns([1.6, 1], gap="medium")

with inspect_col:
    with st.container(key="rp_inspect"):
        theme.panel_head("Inspect a group", right="pick risk &amp; value")
        sel_risk = st.segmented_control("Risk tier", tiers_order, default="High", key="cv_risk") or "High"
        sel_value = st.segmented_control("Value tier", tiers_order, default="High", key="cv_value") or "High"
        c = cells[(sel_risk, sel_value)]
        is_zone = (sel_risk, sel_value) == ("High", "High")
        theme.md(
            f"""<div class="ri-inspect">
                <div class="t">{sel_risk} risk &times; {sel_value} value{" &middot; save first" if is_zone else ""}</div>
                <div class="ri-facts">
                    <div><div class="l">Customers</div><div class="v">{c['n']:,}</div></div>
                    <div><div class="l">Churn rate</div><div class="v" style="color:{theme.RISK_TEXT_COLOR_MAP[sel_risk]};">{c['churn']:.1f}%</div></div>
                    <div><div class="l">Share of base</div><div class="v">{c['pct']:.2f}%</div></div>
                    <div><div class="l">Avg. revenue to date</div><div class="v">{theme.fmt_currency(c['avg_hrr_ntd'])}</div></div>
                </div>
            </div>"""
        )
        if st.button(f"Review these {c['n']:,} customers in Priority Customers →", key="cv_drill", type="primary", width="stretch"):
            st.session_state["pending_filter"] = {"risk_tier": [sel_risk], "value_tier": [sel_value]}
            st.switch_page("pages/priority_customers.py")

with matrix_col:
    with st.container(key="rp_matrix"):
        theme.panel_head("Risk &times; value", right="customers &middot; churn rate")
        head = '<div></div>' + "".join(f'<div class="ri-mx-h">{vt} value</div>' for vt in tiers_order)
        body = []
        for rt in ["High", "Medium", "Low"]:
            body.append(f'<div class="ri-mx-r"><div>Risk<b style="color:{theme.RISK_TEXT_COLOR_MAP[rt]};">{rt}</b></div></div>')
            for vt in tiers_order:
                cc = cells[(rt, vt)]
                rgb = theme.RISK_COLOR_MAP[rt].lstrip("#")
                r, g, b = int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16)
                tint = f"rgba({r},{g},{b},{0.02 + 0.16 * cc['churn'] / 100:.3f})"
                zone = (rt, vt) == ("High", "High")
                sel = (rt, vt) == (sel_risk, sel_value)
                classes = "ri-cell" + (" zone" if zone else "") + (" sel" if sel else "")
                tag_html = '<span class="tag"><span class="ri-badge High">Priority zone</span></span>' if zone else ""
                body.append(
                    f'<div class="{classes}" style="background:{tint};" title="{rt} risk · {vt} value: {cc["n"]:,} customers">'
                    f'{tag_html}'
                    f'<div class="n">{theme.fmt_count(cc["n"])}</div>'
                    f'<div class="churn" style="color:{theme.RISK_TEXT_COLOR_MAP[rt]};">{cc["churn"]:.1f}% churn</div></div>'
                )
        st.markdown(
            f'<div class="ri-matrix">{head}{"".join(body)}</div>'
            '<div class="ri-mx-axis">Revenue to date &rarr;</div>',
            unsafe_allow_html=True,
        )
        theme.insight(
            f"<b>High risk + high value</b> ({theme.fmt_count(hh['n'])} customers, {hh['churn']:.1f}% churn) is the "
            f"one group where both conditions hold -- the strongest case for personal retention outreach."
        )

# ---------------------------------------------------------------------------
# Where revenue concentrates, by behavioural segment
# ---------------------------------------------------------------------------
vbs = value_by_segment.sort_values("total_HRR", ascending=True)
# P1-10: colour carries the segment's role -- Champions keep the growth colour, Stable/Monitor is
# muted to neutral grey ("no action recommended" everywhere else in this product), and every
# genuinely actionable at-risk segment gets the action colour. No data or ordering changed.
def _segment_bar_color(segment_name: str) -> str:
    if segment_name == "Engaged Low-Risk (Champions)":
        return theme.COLORS["low"]
    if segment_name == "Stable / Monitor":
        return theme.COLORS["neutral"]
    return theme.COLORS["accent"]


bar_colors = [_segment_bar_color(s) for s in vbs["segment"]]
fig = go.Figure(go.Bar(
    x=theme.to_inr(vbs["total_HRR"]), y=vbs["segment"], orientation="h", marker_color=bar_colors,
    marker_line_width=0, width=0.55, marker_cornerradius=3,
    text=[f"{theme.fmt_currency(v)} · {p:.0f}%" for v, p in zip(vbs["total_HRR"], vbs["pct_of_total_HRR"])],
    textposition="outside", cliponaxis=False,
    textfont=dict(size=11, color=theme.COLORS["text_muted"], family="Inter, sans-serif"),
    customdata=vbs[["n_customers", "pct_of_total_HRR"]].values,
    hovertemplate="<b>%{y}</b><br>Revenue to date ₹%{x:,.0f}<br>%{customdata[1]:.1f}% of all revenue<br>%{customdata[0]:,} customers<extra></extra>",
))
theme.chart_layout(
    fig, height=330,
    xaxis=dict(visible=False, range=[0, float(theme.to_inr(vbs["total_HRR"]).max()) * 1.2]),
    yaxis=dict(title=None, tickfont=dict(size=12, color=theme.COLORS["text"], family="Inter, sans-serif")),
    margin=dict(l=8, r=24, t=8, b=8),
)

st.write("")
with st.container(key="rp_revenue"):
    theme.panel_head("Where revenue concentrates", right="revenue to date, by customer group")
    theme.plot(fig)
    theme.md(
        f"""<div class="ri-legend">
            <div><i style="background:{theme.COLORS['accent']};"></i>At-risk groups &mdash; where retention effort goes</div>
            <div><i style="background:{theme.COLORS['low']};"></i>Champions &mdash; grow, don't retain</div>
            <div><i style="background:{theme.COLORS['neutral']};"></i>Stable / Monitor &mdash; no action</div>
        </div>"""
    )

theme.journey_next("pages/customer_value.py", key="next_customer_value")

st.write("")
caveats.render_caveats(
    ["hrr", "revenue_exposure", "causal"], value_analysis=value_analysis, risk_summary=risk_summary,
)
