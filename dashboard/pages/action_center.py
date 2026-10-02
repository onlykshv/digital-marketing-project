import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.graph_objects as go
import streamlit as st

from lib import caveats, components, data, theme

theme.apply_page_style()

action_plan = data.safe_load(data.load_action_plan)
risk_summary = data.safe_load(data.load_risk_summary)
value_analysis = data.safe_load(data.load_value_analysis)

all_opportunities = data.priority_opportunities(action_plan)
top_two = all_opportunities.head(2)
secondary = all_opportunities.iloc[2:]
champions = action_plan[action_plan["priority_group"] == "Engaged Low-Risk (Champions)"].iloc[0]
stable = action_plan[action_plan["priority_group"] == "Stable / Monitor"].iloc[0]
base_churn_pct = risk_summary["actual_churn_rate"] * 100

theme.masthead(
    "pages/action_center.py", "Action center", "What should we do?",
    "Your retention playbook: one campaign per customer group, starting where the most revenue is at stake.",
    stats=[
        {"label": "Customers in retention plays", "value": theme.fmt_count(data.customers_requiring_intervention(action_plan)), "dot": theme.COLORS["high"]},
        {"label": "Retention plays", "value": f"{len(all_opportunities)}"},
    ],
)

# ---------------------------------------------------------------------------
# Start with these two -- the plays with the most realized revenue at stake, each with its own way
# into the customers and the assistant.
# ---------------------------------------------------------------------------
p1, p2 = top_two.iloc[0], top_two.iloc[1]
col1, col2 = st.columns(2, gap="medium")
with col1:
    with st.container(key="rp_play1"):
        theme.panel_head("Start here", dot=theme.COLORS["cyan"], right="most revenue at stake")
        components.play_card(
            eyebrow="PRIORITY 01", row=p1,
            why=data.SHORT_WHY_BY_SEGMENT.get(p1["priority_group"], "Elevated model risk for this segment."),
            avoid=data.AVOID_BY_SEGMENT.get(p1["priority_group"]), base_churn_pct=base_churn_pct,
        )
        if st.button("View these customers →", key="view_pc_action_center_p1", type="primary", width="stretch"):
            st.session_state["pending_filter"] = {"segment": [p1["priority_group"]]}
            st.switch_page("pages/priority_customers.py")
        if st.button("Ask Retention Intelligence about this group →", key="ask_ri_action_center", width="stretch"):
            st.session_state["copilot_segment_choice"] = p1["priority_group"]
            st.session_state["cust360_search"] = ""  # a segment question must not land on an earlier customer
            st.switch_page("pages/retention_copilot.py")
with col2:
    with st.container(key="rp_play2"):
        theme.panel_head("Next", dot=theme.COLORS["neutral"], right="second-largest")
        components.play_card(
            eyebrow="PRIORITY 02", row=p2,
            why=data.SHORT_WHY_BY_SEGMENT.get(p2["priority_group"], "Elevated model risk for this segment."),
            avoid=data.AVOID_BY_SEGMENT.get(p2["priority_group"]), base_churn_pct=base_churn_pct,
        )
        if st.button("View these customers →", key="view_pc_action_center_p2", type="primary", width="stretch"):
            st.session_state["pending_filter"] = {"segment": [p2["priority_group"]]}
            st.switch_page("pages/priority_customers.py")
        if st.button("Ask Retention Intelligence about this group →", key="ask_ri_action_center_p2", width="stretch"):
            st.session_state["copilot_segment_choice"] = p2["priority_group"]
            st.session_state["cust360_search"] = ""
            st.switch_page("pages/retention_copilot.py")

# ---------------------------------------------------------------------------
# The whole playbook: all seven groups, banded by what kind of play they are (retain / grow /
# monitor), so the manager sees where effort goes AND where it deliberately does not. Each row
# opens in place to its detail -- every field read from the action-plan row itself or the existing
# plain-English segment mappings.
# ---------------------------------------------------------------------------
theme.section_header("The full playbook", note="Open any row for who it covers, why, the value involved and how confident the framework is.")


def _index_row(r, rank_label: str, dot_color: str) -> str:
    group = r["priority_group"]
    intensity = r["intervention_intensity"]
    avoid = data.AVOID_BY_SEGMENT.get(group)
    detail = (
        f'<div class="ri-pb-detail">'
        f'<div class="action"><span class="l">What to do</span>{r["marketing_objective"]}</div>'
        f'<div><span class="l">Who</span>{data.SHORT_WHY_BY_SEGMENT.get(group, "")}</div>'
        f'<div><span class="l">Revenue to date</span><b>{theme.fmt_currency(r["total_HRR"])}</b> &middot; median {theme.fmt_currency(r["median_HRR"])} per customer</div>'
        f'<div><span class="l">Avoid</span>{avoid or "&mdash;"}</div>'
        f'<div><span class="l">Confidence</span>{r["pct_matching_dominant_recommendation"]:.0f}% of this group sits in the risk &times; value '
        f'cell that sets this intensity &mdash; an observed association, not a causal guarantee.</div>'
        f'</div>'
    )
    return (
        f'<details class="ri-pb-item"><summary class="ri-pb-row">'
        f'<div class="rk">{rank_label}</div>'
        f'<div class="nm">{theme.dot(dot_color)}{group}</div>'
        f'<div class="fig">{theme.fmt_count(r["n_customers"])}</div>'
        f'<div class="fig" style="color:{dot_color};">{r["churn_rate_pct"]:.1f}%</div>'
        f'<div class="act">{data.SHORT_ACTION_BY_SEGMENT.get(group, "")} <span class="ri-chip" style="margin-left:0.3rem;">{intensity}</span></div>'
        f'<div class="chev">&rsaquo;</div>'
        f"</summary>{detail}</details>"
    )


index_html = [
    '<div class="ri-pb"><div class="ri-pb-row head"><div>#</div><div>Customer group</div><div>Customers</div>'
    '<div>Churn rate</div><div>Campaign</div><div></div></div>',
    f'<div class="ri-pb-band" style="color:var(--high-text);">Retain <span>{len(all_opportunities)} at-risk groups &middot; '
    f'{theme.fmt_count(all_opportunities["n_customers"].sum())} customers</span></div>',
]
for i, (_, r) in enumerate(all_opportunities.iterrows()):
    index_html.append(_index_row(r, f"{i + 1:02d}", theme.COLORS["high_text"] if r["churn_rate_pct"] >= 50 else theme.COLORS["medium_text"]))
index_html.append('<div class="ri-pb-band" style="color:var(--low-text);">Grow <span>not a retention play</span></div>')
index_html.append(_index_row(champions, "&mdash;", theme.COLORS["low_text"]))
index_html.append('<div class="ri-pb-band" style="color:var(--muted);">Monitor <span>no action recommended</span></div>')
index_html.append(_index_row(stable, "&mdash;", theme.COLORS["text_faint"]))
index_html.append("</div>")
st.markdown("".join(index_html), unsafe_allow_html=True)

st.write("")
st.download_button(
    "Download full action plan (CSV)",
    data=action_plan.to_csv(index=False).encode("utf-8"),
    file_name="marketing_action_plan.csv",
    mime="text/csv",
)

# ---------------------------------------------------------------------------
# Not a retention play: the two groups the framework deliberately does not spend retention budget
# on. Shown so "what not to do" is as explicit as "what to do".
# ---------------------------------------------------------------------------
theme.divider()
theme.section_header("Not a retention play", note="Where the framework deliberately spends no retention budget.")
g_col, m_col = st.columns(2, gap="medium")
with g_col:
    # P2-16: secondary_story's own eyebrow carries the signpost -- no second, stacked label above it.
    components.secondary_story(
        eyebrow="GROWTH OPPORTUNITY",
        title=champions["priority_group"],
        stat_html=(
            f"<b>{theme.fmt_count(champions['n_customers'])}</b> customers &middot; "
            f"<b style='color:{theme.COLORS['low_text']};'>{champions['churn_rate_pct']:.1f}%</b> churn &middot; "
            f"<b>{theme.fmt_currency(champions['total_HRR'])}</b> revenue to date"
        ),
        objective=champions["marketing_objective"],
        color=theme.COLORS["low_text"],
    )
with m_col:
    components.secondary_story(
        eyebrow="MONITOR",
        title="Stable / Monitor",
        stat_html=(
            f"<b>{theme.fmt_count(stable['n_customers'])}</b> customers "
            f"({stable['pct_of_base']:.0f}% of the base) &middot; <b>{stable['churn_rate_pct']:.1f}%</b> churn"
        ),
        objective=stable["marketing_objective"],
        color=theme.COLORS["text_muted"],
    )

st.write("")
# P1-10: the smaller groups' detail stays behind progressive disclosure -- the playbook above
# already shows all three at a glance; this is the campaign table for anyone who wants it.
with st.expander(f"Other customers needing attention -- {len(secondary)} smaller at-risk groups"):
    st.caption("Same framework, lower revenue at stake.")
    sec_display = secondary[["priority_group", "n_customers", "churn_rate_pct", "total_HRR", "intervention_intensity"]].copy()
    sec_display["total_HRR"] = sec_display["total_HRR"].apply(theme.fmt_currency)
    sec_display = sec_display.rename(columns={
        "priority_group": "Segment", "n_customers": "Customers", "churn_rate_pct": "Churn Rate (%)",
        "total_HRR": "Revenue", "intervention_intensity": "Recommended Treatment",
    })
    st.dataframe(
        sec_display, hide_index=True, width="stretch",
        column_config={
            "Customers": st.column_config.NumberColumn(format="%d"),
            "Churn Rate (%)": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )
    st.caption("Full campaign wording for each of these segments is in the CSV download above.")

with st.expander("Portfolio view -- all segments by churn rate, size, and revenue"):
    fig = go.Figure()
    max_hrr = float(action_plan["total_HRR"].max())
    for _, r in action_plan.iterrows():
        fig.add_trace(go.Scatter(
            x=[r["churn_rate_pct"]], y=[r["pct_of_base"]], mode="markers+text",
            marker=dict(
                size=[float(r["total_HRR"])], sizemode="area", sizeref=2.0 * max_hrr / (64 ** 2), sizemin=7,
                color=theme.intensity_color(r["intervention_intensity"]), opacity=0.85,
                line=dict(width=1.5, color=theme.COLORS["paper"]),
            ),
            text=[r["priority_group"]], textposition="top center", name=r["priority_group"], showlegend=False,
            textfont=dict(size=11, color=theme.COLORS["text"]),
            hovertemplate=(
                f"<b>{r['priority_group']}</b><br>Churn rate: {r['churn_rate_pct']:.1f}%<br>"
                f"% of base: {r['pct_of_base']:.2f}%<br>Revenue: {theme.fmt_currency(r['total_HRR'])}<extra></extra>"
            ),
        ))
    theme.chart_layout(
        fig, height=theme.CHART_HEIGHT_LARGE,
        xaxis=dict(title="Churn rate (%)", ticksuffix="%", range=[-5, 90]),
        yaxis=dict(title="% of customer base", ticksuffix="%", range=[-6, 64]),
    )
    theme.plot(fig)
    st.caption("Bubble area = total realized revenue (HRR) held by the group. Colour = recommended treatment intensity.")

theme.journey_next("pages/action_center.py", key="next_action_center")

st.write("")
caveats.render_caveats(
    ["causal", "hrr", "calibration"], risk_summary=risk_summary, value_analysis=value_analysis,
)
