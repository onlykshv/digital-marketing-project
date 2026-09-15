import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plotly.graph_objects as go
import streamlit as st

from lib import caveats, components, data, theme

theme.apply_page_style()

theme.page_header(
    "ACTION CENTER",
    "What should we do?",
    "Every segment, ranked by where retention effort pays off most.",
)

action_plan = data.safe_load(data.load_action_plan)
risk_summary = data.safe_load(data.load_risk_summary)
value_analysis = data.safe_load(data.load_value_analysis)

st.download_button(
    "Download full action plan (CSV)",
    data=action_plan.to_csv(index=False).encode("utf-8"),
    file_name="marketing_action_plan.csv",
    mime="text/csv",
)

all_opportunities = data.priority_opportunities(action_plan)
top_two = all_opportunities.head(2)
secondary = all_opportunities.iloc[2:]
champions = action_plan[action_plan["priority_group"] == "Engaged Low-Risk (Champions)"].iloc[0]
stable = action_plan[action_plan["priority_group"] == "Stable / Monitor"].iloc[0]

theme.eyebrow("The intervention queue")
theme.section("What should marketing do next?", "Retention effort concentrated where churn and revenue at stake are both high.")

p1 = top_two.iloc[0]
components.recommendation_block(
    eyebrow="PRIORITY 01",
    title=p1["priority_group"],
    stat_html=(
        f"<b>{theme.fmt_count(p1['n_customers'])}</b> customers &middot; "
        f"<b style='color:{theme.COLORS['high']};'>{p1['churn_rate_pct']:.1f}%</b> churn &middot; "
        f"<b>{theme.fmt_currency(p1['total_HRR'])}</b> realized revenue"
    ),
    objective=p1["marketing_objective"],
    intensity=p1["intervention_intensity"],
    why=data.SHORT_WHY_BY_SEGMENT.get(p1["priority_group"], "Elevated model risk for this segment."),
    rationale=p1["rationale"],
    size="large",
)
if st.button(f"Ask Retention Intelligence about {p1['priority_group']} →", key="ask_ri_action_center"):
    st.session_state["copilot_segment_choice"] = p1["priority_group"]
    st.switch_page("pages/retention_copilot.py")

st.write("")
p2_col, _ = st.columns([3, 2], gap="large")
with p2_col:
    p2 = top_two.iloc[1]
    components.recommendation_block(
        eyebrow="PRIORITY 02",
        title=p2["priority_group"],
        stat_html=(
            f"<b>{theme.fmt_count(p2['n_customers'])}</b> customers &middot; "
            f"<b style='color:{theme.COLORS['high']};'>{p2['churn_rate_pct']:.1f}%</b> churn &middot; "
            f"<b>{theme.fmt_currency(p2['total_HRR'])}</b> realized revenue"
        ),
        objective=p2["marketing_objective"],
        intensity=p2["intervention_intensity"],
        why=data.SHORT_WHY_BY_SEGMENT.get(p2["priority_group"], "Elevated model risk for this segment."),
        rationale=p2["rationale"],
        size="small",
    )

st.write("")
# P1-10: this table used to render open by default, directly under the two headline priority
# cards -- a manager who already has the page's main point (Priority 01/02) had no reason to also
# parse a second full data table on first read. Same "keep the evidence accessible, don't force it
# on the default view" treatment the "Portfolio view" chart below already uses on this exact page;
# the data itself, and everything in it, is unchanged.
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

st.write("")
theme.divider()
# P2-16: this section used to open with a standalone theme.eyebrow(...) transition label
# immediately above secondary_story's own eyebrow parameter -- two uppercase small-caps labels
# stacked with almost no gap, reading as one cramped, broken two-line label rather than two
# distinct pieces of information. Overview's own use of secondary_story (the same growth-not-risk
# framing, right column) never doubles up like this -- it lets secondary_story's own eyebrow
# parameter carry the signpost alone. Removed the redundant outer label here to match that
# established, cleaner pattern -- same content, same component, one less stacked label.
components.secondary_story(
    eyebrow="GROWTH OPPORTUNITY",
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
    f"<b>Stable / Monitor:</b> {theme.fmt_count(stable['n_customers'])} customers "
    f"({stable['pct_of_base']:.0f}% of the base), {stable['churn_rate_pct']:.1f}% churn -- "
    f"{stable['marketing_objective'].rstrip('.').lower()}."
)

st.write("")
with st.expander("Portfolio view -- all segments by churn rate, size, and revenue"):
    fig = go.Figure()
    for _, r in action_plan.iterrows():
        fig.add_trace(go.Scatter(
            x=[r["churn_rate_pct"]], y=[r["pct_of_base"]], mode="markers+text",
            marker=dict(
                size=max(18, min(70, (r["total_HRR"] ** 0.5) / 90)),
                color=theme.intensity_color(r["intervention_intensity"]), opacity=0.75,
                line=dict(width=1, color="white"),
            ),
            text=[r["priority_group"]], textposition="top center", name=r["priority_group"], showlegend=False,
            hovertemplate=(
                f"<b>{r['priority_group']}</b><br>Churn rate: {r['churn_rate_pct']:.1f}%<br>"
                f"% of base: {r['pct_of_base']:.2f}%<br>Revenue: {theme.fmt_currency(r['total_HRR'])}<extra></extra>"
            ),
        ))
    theme.chart_layout(fig, height=theme.CHART_HEIGHT_LARGE, xaxis_title="Churn rate (%)", yaxis_title="% of customer base")
    st.plotly_chart(fig, width="stretch", config=theme.PLOTLY_CONFIG)
    st.caption("Bubble size = total realized revenue (HRR) held by the group.")

st.write("")
caveats.render_caveats(
    ["causal", "hrr", "calibration"], risk_summary=risk_summary, value_analysis=value_analysis,
)
