import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from lib import caveats, components, data, theme

theme.apply_page_style()

risk_summary = data.safe_load(data.load_risk_summary)
action_plan = data.safe_load(data.load_action_plan)
risk_value_matrix = data.safe_load(data.load_risk_value_matrix)
temporal_results = data.safe_load(data.load_temporal_results)

tiers_by_name = {t["tier"]: t for t in risk_summary["risk_tiers"]}
thresholds = risk_summary["recommended_thresholds"]
intervention_needed = data.customers_requiring_intervention(action_plan)
opportunities = data.priority_opportunities(action_plan, top_n=1)
top_opportunity = opportunities.iloc[0]

n_scored = risk_summary["n_customers_scored"]
n_high = tiers_by_name["High"]["n_customers"]
hh = risk_value_matrix.loc["High"]
n_zone = int(hh["n_High"])
zone_churn = float(hh["churn_rate_pct_High"])
zone_avg_hrr = float(hh["avg_hrr_High"])
base_churn_pct = risk_summary["actual_churn_rate"] * 100

theme.masthead(
    "pages/overview.py", "Retention overview", "Where should KKBOX act?",
    f"{theme.fmt_count(n_scored)} KKBOX subscribers, scored for how likely they are to leave &mdash; "
    "and the small group worth saving first.",
)

# ---------------------------------------------------------------------------
# The three numbers the whole product rests on, read left to right: everyone -> those showing risk
# signals -> the few to save first.
# ---------------------------------------------------------------------------
theme.kpi_strip([
    {"label": "Customers analyzed", "value": theme.fmt_count(n_scored), "dot": theme.COLORS["neutral"],
     "note": f"{base_churn_pct:.1f}% churn rate across the base"},
    {"label": "Showing risk signals", "value": theme.fmt_count(intervention_needed), "dot": theme.COLORS["medium"],
     "note": f"{theme.fmt_count(n_high)} of them at the highest risk"},
    {"label": "Save first", "value": theme.fmt_count(n_zone), "dot": theme.COLORS["high"],
     "note": "High risk and high value", "note_color": theme.COLORS["high_text"]},
])
st.write("")

funnel_col, start_col = st.columns([1.55, 1], gap="medium")

# ---------------------------------------------------------------------------
# WHERE SHOULD KKBOX ACT? -- the scored base narrowed, step by step, to the customers worth
# individual attention. Bar widths are linear shares of the base (no scale distortion), and each
# stage is a genuine subset of the one above it.
# ---------------------------------------------------------------------------
stages = [
    {"n": n_scored, "what": "Customers analyzed", "color": theme.COLORS["neutral"]},
    {"n": intervention_needed, "what": "Showing risk signals", "color": theme.COLORS["medium"]},
    {"n": n_high, "what": "Highest risk", "color": theme.COLORS["high"]},
    {"n": n_zone, "what": "High risk + high value", "color": "#FF5A48"},
]
rows = []
for i, s in enumerate(stages):
    share = s["n"] / n_scored * 100
    share_txt = f"{share:.0f}%" if share >= 99.5 else (f"{share:.1f}%" if share >= 1 else f"{share:.2f}%")
    rows.append(
        f'<div class="row{" focus" if i == 3 else ""}" data-n="{s["n"]}" data-share="{share:.4f}">'
        f'<div class="n">{theme.fmt_count(s["n"])}</div><div>'
        f'<div class="what"><b>{s["what"]}</b><span>{share_txt} of customers</span></div>'
        f'<div class="bar"><i style="width:{share:.4f}%; background:{s["color"]};"></i></div></div></div>'
    )

with funnel_col:
    with st.container(key="rp_funnel"):
        theme.panel_head("From every customer to the few to save first", right="share of all customers")
        st.markdown(f'<div class="ri-funnel">{"".join(rows)}</div>', unsafe_allow_html=True)
        theme.insight(
            f"The last group is small &mdash; <b>{theme.fmt_count(n_zone)}</b> customers &mdash; but "
            f"<b>{zone_churn:.1f}%</b> of them churn, and each has already spent "
            f"<b>{theme.fmt_currency(zone_avg_hrr)}</b> on average. That is where personal outreach is most worth considering."
        )
        if st.button(
            f"Review the {theme.fmt_count(n_zone)} high-risk, high-value customers →",
            key="ov_zone_to_priority", type="primary",
        ):
            st.session_state["pending_filter"] = {"risk_tier": ["High"], "value_tier": ["High"]}
            st.switch_page("pages/priority_customers.py")
        with st.expander("How these groups are defined"):
            st.markdown(
                f"Every customer gets a **Model Risk Score** from the churn model. **Showing risk signals** "
                f"means a score of {thresholds['medium_risk_threshold']:.2f} or more (the Medium and High "
                f"tiers); **highest risk** means {thresholds['high_risk_threshold']:.2f} or more, where "
                f"{tiers_by_name['High']['observed_churn_rate_in_tier']:.1f}% actually churned. **High value** "
                "is the top tier of Historical Realized Revenue &mdash; money already collected, not a forecast."
            )

# ---------------------------------------------------------------------------
# Start here -- the single biggest actionable play, with the two ways forward: the customers
# themselves (P1-08: the page's portfolio signal carries into the work queue as a starting filter)
# and the assistant (P1-13: Retention Intelligence reachable from the first screen, on the very
# segment this panel names).
# ---------------------------------------------------------------------------
with start_col:
    with st.container(key="rp_start"):
        theme.panel_head("Start here", dot=theme.COLORS["cyan"], right="largest at-risk group")
        components.recommendation_block(
            eyebrow="Biggest opportunity",
            title=top_opportunity["priority_group"],
            stat_html=(
                f"<b>{theme.fmt_count(top_opportunity['n_customers'])}</b> customers &middot; "
                f"<b style='color:{theme.COLORS['high_text']};'>{top_opportunity['churn_rate_pct']:.1f}%</b> churn &middot; "
                f"<b>{theme.fmt_currency(top_opportunity['total_HRR'])}</b> revenue to date"
            ),
            objective=top_opportunity["marketing_objective"],
            intensity=top_opportunity["intervention_intensity"],
            rationale=top_opportunity["rationale"],
            size="small",
        )
        if st.button(
            f"View {top_opportunity['priority_group']} customers in Priority Customers →",
            key="view_priority_customers_overview", type="primary", width="stretch",
        ):
            st.session_state["pending_filter"] = {"segment": [top_opportunity["priority_group"]]}
            st.switch_page("pages/priority_customers.py")
        if st.button(
            f"Ask Retention Intelligence: why does {top_opportunity['priority_group']} need attention? →",
            key="hero_ask_ri", width="stretch",
        ):
            st.session_state["copilot_segment_choice"] = top_opportunity["priority_group"]
            st.session_state["cust360_search"] = ""  # a segment question must not land on an earlier customer
            st.switch_page("pages/retention_copilot.py")

theme.journey_next("pages/overview.py", key="next_overview")

st.write("")
caveats.render_caveats(
    ["temporal", "calibration", "reusability"], risk_summary=risk_summary, temporal_results=temporal_results,
)
